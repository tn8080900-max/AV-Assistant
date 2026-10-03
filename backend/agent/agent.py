import json
import logging
import os
import uuid
from dataclasses import dataclass
from threading import RLock
from typing import Any

from openai import OpenAI

from backend.agent.memory import SessionMemory
from backend.agent.prompts import SYSTEM_PROMPT
from backend.agent.state import AgentState
from backend.config import SettingsStore, configured_value
from backend.permissions.manager import may_run_automatically
from backend.security import redact_secrets
from backend.tools.base import Tool
from backend.tools.registry import build_tool_registry

logger = logging.getLogger("av_assistant.agent")


@dataclass
class PendingApproval:
    request_id: str
    tool: Tool
    arguments: dict[str, Any]
    tool_call_id: str
    description: str


class Agent:
    def __init__(self, settings: SettingsStore) -> None:
        self.settings = settings
        self.memory = SessionMemory()
        self._pending: dict[str, PendingApproval] = {}
        self._denied_actions: set[str] = set()
        self._lock = RLock()

    @property
    def client(self) -> OpenAI:
        api_key = configured_value("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured in the local .env file.")
        return OpenAI(api_key=api_key, timeout=75, max_retries=1)

    def run(self, user_message: str) -> dict[str, Any]:
        cleaned = user_message.strip()
        if not cleaned or len(cleaned) > 4000:
            raise ValueError("Enter a request between 1 and 4,000 characters.")

        logger.info("Agent request: %s", redact_secrets(cleaned))
        self.memory.remember({"role": "user", "content": cleaned})
        events: list[dict[str, Any]] = []
        return self._continue_agent(events)

    def resolve_approval(self, request_id: str, approved: bool) -> dict[str, Any]:
        with self._lock:
            pending = self._pending.pop(request_id, None)
        if pending is None:
            raise KeyError("That permission request has expired or was already answered.")

        events: list[dict[str, Any]] = [
            {
                "tool": pending.tool.name,
                "status": "approved" if approved else "denied",
                "summary": pending.description,
            }
        ]
        logger.info(
            "Permission %s for tool=%s",
            "granted" if approved else "denied",
            pending.tool.name,
        )

        if approved:
            try:
                result = pending.tool.execute(pending.arguments)
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": pending.tool_call_id,
                        "content": result,
                    }
                )
                events[0]["result"] = result
                logger.info(
                    "Tool completed: %s result=%s",
                    pending.tool.name,
                    redact_secrets(str(result)),
                )
            except Exception as exc:
                safe_error = _safe_error(exc)
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": pending.tool_call_id,
                        "content": f"Tool failed: {safe_error}",
                    }
                )
                events[0]["status"] = "error"
                events[0]["result"] = safe_error
                logger.warning("Tool failed: %s (%s)", pending.tool.name, safe_error)
        else:
            with self._lock:
                self._denied_actions.add(
                    _action_signature(pending.tool.name, pending.arguments)
                )
            self.memory.remember(
                {
                    "role": "tool",
                    "tool_call_id": pending.tool_call_id,
                    "content": "The user denied this action. Do not attempt it again.",
                }
            )

        return self._continue_agent(events)

    def clear_session(self) -> None:
        with self._lock:
            self._pending.clear()
            self._denied_actions.clear()
        self.memory.clear()
        logger.info("Session history cleared")

    def _continue_agent(self, events: list[dict[str, Any]]) -> dict[str, Any]:
        tools = build_tool_registry(self.settings)
        for _ in range(5):
            response = self.client.chat.completions.create(
                model=configured_value("OPENAI_MODEL", "gpt-5.4-mini"),
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    *self.memory.retrieve(),
                ],
                tools=[tool.openai_definition() for tool in tools.values()],
                tool_choice="auto",
                parallel_tool_calls=False,
                max_completion_tokens=8192,
            )
            assistant_message = response.choices[0].message
            tool_calls = assistant_message.tool_calls or []
            if not tool_calls:
                answer = (assistant_message.content or "").strip()
                if not answer:
                    answer = "I wasn't able to form a response. Please try again."
                self.memory.remember({"role": "assistant", "content": answer})
                logger.info("Agent completed a response")
                return {
                    "state": AgentState.IDLE,
                    "answer": answer,
                    "events": events,
                    "pending_approval": None,
                }

            call = tool_calls[0]
            assistant_tool_call = {
                "role": "assistant",
                "content": assistant_message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {
                            "name": call.function.name,
                            "arguments": call.function.arguments,
                        },
                    }
                ],
            }
            self.memory.remember(assistant_tool_call)
            tool = tools.get(call.function.name)
            if tool is None:
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": "This tool is not registered and cannot be run.",
                    }
                )
                events.append(
                    {"tool": call.function.name, "status": "error", "result": "Tool unavailable."}
                )
                continue

            try:
                arguments = json.loads(call.function.arguments or "{}")
                if not isinstance(arguments, dict):
                    raise ValueError("Tool arguments must be a JSON object.")
            except (json.JSONDecodeError, ValueError):
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": "The tool supplied invalid parameters.",
                    }
                )
                events.append(
                    {"tool": tool.name, "status": "error", "result": "Invalid tool parameters."}
                )
                continue

            try:
                arguments = tool.validate_arguments(arguments)
            except Exception as exc:
                safe_error = _safe_error(exc)
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"Tool validation failed: {safe_error}",
                    }
                )
                events.append(
                    {"tool": tool.name, "status": "error", "result": safe_error}
                )
                logger.info("Tool parameters rejected before execution: %s", tool.name)
                continue

            with self._lock:
                was_denied = (
                    _action_signature(tool.name, arguments) in self._denied_actions
                )
            if was_denied:
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": "The user already denied this exact action. It cannot be retried in this session.",
                    }
                )
                events.append(
                    {
                        "tool": tool.name,
                        "status": "denied",
                        "result": "The user already denied this action.",
                    }
                )
                logger.info("Previously denied action was not retried: %s", tool.name)
                continue

            logger.info(
                "Agent selected tool=%s parameters=%s",
                tool.name,
                redact_secrets(json.dumps(arguments, ensure_ascii=False)),
            )
            if not may_run_automatically(tool.permission):
                request_id = str(uuid.uuid4())
                description = _approval_description(tool.name, arguments)
                pending = PendingApproval(
                    request_id=request_id,
                    tool=tool,
                    arguments=arguments,
                    tool_call_id=call.id,
                    description=description,
                )
                with self._lock:
                    self._pending[request_id] = pending
                logger.info("Permission requested for tool=%s", tool.name)
                return {
                    "state": AgentState.WAITING_FOR_PERMISSION,
                    "answer": None,
                    "events": events,
                    "pending_approval": {
                        "request_id": request_id,
                        "title": f"Allow {tool.name.replace('_', ' ')}?",
                        "details": description,
                    },
                }

            events.append({"tool": tool.name, "status": "running"})
            logger.info("Executing safe tool=%s", tool.name)
            try:
                result = tool.execute(arguments)
                self.memory.remember(
                    {"role": "tool", "tool_call_id": call.id, "content": result}
                )
                events[-1].update(status="completed", result=result)
                logger.info(
                    "Tool completed: %s result=%s",
                    tool.name,
                    redact_secrets(str(result)),
                )
            except Exception as exc:
                safe_error = _safe_error(exc)
                self.memory.remember(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": f"Tool failed: {safe_error}",
                    }
                )
                events[-1].update(status="error", result=safe_error)
                logger.warning("Tool failed: %s (%s)", tool.name, safe_error)

        return {
            "state": AgentState.ERROR,
            "answer": "I reached the tool-use limit for this request. Please try a shorter request.",
            "events": events,
            "pending_approval": None,
        }


def _approval_description(tool_name: str, arguments: dict[str, Any]) -> str:
    if tool_name == "delete_file":
        return f"Delete this file: {redact_secrets(str(arguments.get('path', '')))}"
    return f"Run {tool_name.replace('_', ' ')} with the requested details."


def _safe_error(exc: Exception) -> str:
    if isinstance(exc, ValueError):
        return str(exc)
    if isinstance(exc, RuntimeError):
        return str(exc)
    return "The action could not be completed. Check the local application log for details."


def _action_signature(tool_name: str, arguments: dict[str, Any]) -> str:
    normalized = dict(arguments)
    path = normalized.get("path")
    if isinstance(path, str):
        normalized["path"] = os.path.normcase(
            os.path.normpath(os.path.abspath(os.path.expanduser(path)))
        )
    return f"{tool_name}:{json.dumps(normalized, sort_keys=True, ensure_ascii=True)}"