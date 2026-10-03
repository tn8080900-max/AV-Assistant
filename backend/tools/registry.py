from typing import Any

from backend.config import SettingsStore
from backend.permissions.manager import PermissionLevel
from backend.tools.applications import launch_application
from backend.tools.base import Tool
from backend.tools.browser import open_website
from backend.tools.calculator import calculate
from backend.tools.file_search import search_files, validate_deletion_target
from backend.tools.time_tool import get_current_time


def build_tool_registry(settings: SettingsStore) -> dict[str, Tool]:
    tools = [
        Tool(
            name="get_current_time",
            description="Get the current local time on the user's computer.",
            parameters={"type": "object", "properties": {}, "required": [], "additionalProperties": False},
            permission=PermissionLevel.SAFE,
            handler=lambda _: get_current_time({}),
        ),
        Tool(
            name="calculator",
            description="Evaluate a basic arithmetic expression using the calculator.",
            parameters={
                "type": "object",
                "properties": {"expression": {"type": "string", "maxLength": 200}},
                "required": ["expression"],
                "additionalProperties": False,
            },
            permission=PermissionLevel.SAFE,
            handler=lambda args: calculate(_string_arg(args, "expression")),
        ),
        Tool(
            name="open_website",
            description="Open an http or https URL in the user's default browser.",
            parameters={
                "type": "object",
                "properties": {"url": {"type": "string", "maxLength": 2048}},
                "required": ["url"],
                "additionalProperties": False,
            },
            permission=PermissionLevel.SAFE,
            handler=lambda args: open_website(_string_arg(args, "url")),
        ),
        Tool(
            name="search_files",
            description="Search filenames only inside the user's configured directories. Never reads file contents.",
            parameters={
                "type": "object",
                "properties": {"query": {"type": "string", "maxLength": 200}},
                "required": ["query"],
                "additionalProperties": False,
            },
            permission=PermissionLevel.SAFE,
            handler=lambda args: _format_search(
                search_files(_string_arg(args, "query"), settings.allowed_directories)
            ),
        ),
        Tool(
            name="delete_file",
            description="Delete one file inside a user-configured directory. This always requires the user's explicit approval before execution.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string", "maxLength": 2048}},
                "required": ["path"],
                "additionalProperties": False,
            },
            permission=PermissionLevel.REQUIRES_CONFIRMATION,
            handler=lambda args: _delete_file(_string_arg(args, "path"), settings),
            validator=lambda args: _validate_delete(args, settings),
        ),
    ]

    if settings.allowed_applications:
        tools.append(
            Tool(
                name="open_application",
                description=(
                    "Launch a permitted Windows application. "
                    f"Allowed names: {', '.join(settings.allowed_applications)}."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "application": {
                            "type": "string",
                            "enum": settings.allowed_applications,
                        }
                    },
                    "required": ["application"],
                    "additionalProperties": False,
                },
                permission=PermissionLevel.SAFE,
                handler=lambda args: launch_application(
                    _string_arg(args, "application"), settings.allowed_applications
                ),
            )
        )
    return {tool.name: tool for tool in tools}


def _string_arg(args: dict[str, Any], key: str) -> str:
    value = args.get(key)
    if not isinstance(value, str):
        raise ValueError(f"Expected {key} to be text.")
    return value


def _format_search(results: list[str]) -> str:
    if not results:
        return "No matching filenames found in the configured directories."
    return "Matching files:\n" + "\n".join(results)


def _delete_file(path: str, settings: SettingsStore) -> str:
    target = validate_deletion_target(path, settings.allowed_directories)
    target.unlink()
    return f"Deleted {target.name}."


def _validate_delete(
    arguments: dict[str, Any], settings: SettingsStore
) -> dict[str, Any]:
    target = validate_deletion_target(
        _string_arg(arguments, "path"), settings.allowed_directories
    )
    return {"path": str(target)}