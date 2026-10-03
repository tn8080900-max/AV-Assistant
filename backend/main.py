import logging
import os
import platform
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from backend.agent.agent import Agent
from backend.agent.state import AgentState
from backend.config import (
    PROJECT_ROOT,
    PERMITTED_APPLICATIONS,
    SettingsStore,
    configured_value,
)
from backend.voice.elevenlabs import ElevenLabsSpeech


logging.basicConfig(
    level=logging.DEBUG if os.getenv("AV_DEBUG", "").lower() in {"1", "true", "yes"} else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("av_assistant")

settings = SettingsStore()
agent = Agent(settings)
speech = ElevenLabsSpeech()

app = FastAPI(
    title="AV Assistant Local Companion",
    description="Loopback-only agent API for the Windows desktop companion.",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5173",
        "http://localhost:5173",
        "http://127.0.0.1:4173",
        "http://localhost:4173",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["Content-Type"],
)

AGENT_API_PREFIX = "/agent-api"
MAX_AUDIO_BYTES = 16 * 1024 * 1024
FRONTEND_BUILD = PROJECT_ROOT / "artifacts" / "av-assistant" / "dist" / "public"


class AgentInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class ApprovalInput(BaseModel):
    approved: bool


class SettingsInput(BaseModel):
    allowed_directories: list[str] = Field(max_length=25)
    allowed_applications: list[str] = Field(max_length=len(PERMITTED_APPLICATIONS))


class SpeakInput(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


def _providers_ready() -> dict[str, bool]:
    return {
        "agent": bool(configured_value("OPENAI_API_KEY")),
        "speech_to_text": bool(speech.api_key),
        "text_to_speech": bool(speech.api_key and speech.voice_id),
    }


@app.get(f"{AGENT_API_PREFIX}/health")
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "computer": platform.system(),
        "providers": _providers_ready(),
        "provider_ready": _providers_ready()["agent"],
        "provider_name": "OpenAI",
    }


@app.get(f"{AGENT_API_PREFIX}/settings")
def get_settings() -> dict[str, object]:
    return {
        **settings.as_dict(),
        "available_applications": sorted(PERMITTED_APPLICATIONS),
        "providers": _providers_ready(),
        "provider_ready": _providers_ready()["agent"],
        "provider_name": "OpenAI",
    }


@app.patch(f"{AGENT_API_PREFIX}/settings")
def update_settings(request: SettingsInput) -> dict[str, object]:
    try:
        saved = settings.update(request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.info(
        "Settings updated: %d configured directories; %d permitted applications",
        len(saved["allowed_directories"]),
        len(saved["allowed_applications"]),
    )
    return {
        **saved,
        "available_applications": sorted(PERMITTED_APPLICATIONS),
        "providers": _providers_ready(),
        "provider_ready": _providers_ready()["agent"],
        "provider_name": "OpenAI",
    }


@app.post(f"{AGENT_API_PREFIX}/agent/run")
def run_agent(request: AgentInput) -> dict[str, object]:
    if not configured_value("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=503,
            detail="Add OPENAI_API_KEY to the local .env file to enable the AI agent.",
        )
    try:
        reply = agent.run(request.message)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Agent request failed: %s", type(exc).__name__)
        detail = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else "The agent request failed. Check the local application log."
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    return _serialize_reply(reply)


@app.post(f"{AGENT_API_PREFIX}/approvals/{{request_id}}")
def respond_to_approval(request_id: str, request: ApprovalInput) -> dict[str, object]:
    try:
        reply = agent.resolve_approval(request_id, request.approved)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        logger.error("Permission resolution failed: %s", type(exc).__name__)
        detail = (
            str(exc)
            if isinstance(exc, RuntimeError)
            else "The approved action could not be completed."
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    return _serialize_reply(reply)


@app.delete(f"{AGENT_API_PREFIX}/session")
def clear_session() -> dict[str, str]:
    agent.clear_session()
    return {"status": "cleared"}


@app.post(f"{AGENT_API_PREFIX}/voice/transcribe")
def transcribe_voice(file: UploadFile = File(...)) -> dict[str, str]:
    if not speech.api_key:
        raise HTTPException(
            status_code=503,
            detail="Add ELEVENLABS_API_KEY to the local .env file to enable speech recognition.",
        )
    content_type = (file.content_type or "").lower()
    if not content_type.startswith("audio/"):
        raise HTTPException(status_code=415, detail="Choose an audio recording.")
    data = file.file.read(MAX_AUDIO_BYTES + 1)
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="The recording must be smaller than 16 MB.")
    try:
        transcript = speech.transcribe(
            data,
            Path(file.filename or "recording.webm").name,
            content_type,
        )
    except Exception as exc:
        logger.warning("Speech recognition request failed: %s", type(exc).__name__)
        detail = str(exc) if isinstance(exc, RuntimeError) else "Speech recognition failed. Try recording again."
        raise HTTPException(status_code=502, detail=detail) from exc
    logger.info("Speech recognized (%d characters)", len(transcript))
    return {"transcript": transcript}


@app.post(f"{AGENT_API_PREFIX}/voice/speak")
def speak_text(request: SpeakInput) -> Response:
    if not speech.api_key or not speech.voice_id:
        raise HTTPException(
            status_code=503,
            detail="Add ELEVENLABS_API_KEY and ELEVENLABS_VOICE_ID to the local .env file to enable speech playback.",
        )
    try:
        audio_bytes, content_type = speech.synthesize(request.text)
    except Exception as exc:
        logger.warning("Text-to-speech request failed: %s", type(exc).__name__)
        detail = str(exc) if isinstance(exc, RuntimeError) else "Speech playback could not be generated."
        raise HTTPException(status_code=502, detail=detail) from exc
    return Response(content=audio_bytes, media_type=content_type)


def _serialize_reply(reply: dict[str, object]) -> dict[str, object]:
    state = reply.get("state", AgentState.IDLE)
    events = reply.get("events", [])
    pending = reply.get("pending_approval")
    return {
        "response": reply.get("answer") or "",
        "tools": [
            {
                "name": event.get("tool", "Local tool"),
                "status": event.get("status", "completed"),
                "result": event.get("result", event.get("summary", "")),
            }
            for event in events
            if isinstance(event, dict)
        ]
        if isinstance(events, list)
        else [],
        "pending_confirmation": pending,
        "state": state.value if isinstance(state, AgentState) else str(state),
    }


if FRONTEND_BUILD.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_BUILD, html=True), name="frontend")
else:
    @app.get("/", include_in_schema=False)
    def frontend_not_built() -> dict[str, str]:
        return {
            "message": "Frontend files are missing. Run start.bat or build the AV Assistant web package."
        }