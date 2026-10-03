import os
from urllib.parse import quote

import httpx

from backend.config import configured_value


class ElevenLabsSpeech:
    def __init__(self) -> None:
        self.api_key = configured_value("ELEVENLABS_API_KEY")
        self.voice_id = configured_value("ELEVENLABS_VOICE_ID")
        self.stt_model = configured_value("ELEVENLABS_STT_MODEL_ID", "scribe_v1")
        self.tts_model = configured_value(
            "ELEVENLABS_TTS_MODEL_ID", "eleven_multilingual_v2"
        )
        self.base_url = "https://api.elevenlabs.io/v1"

    def transcribe(self, audio: bytes, filename: str, content_type: str) -> str:
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured in the local .env file.")
        response = httpx.post(
            f"{self.base_url}/speech-to-text",
            headers={"xi-api-key": self.api_key},
            data={"model_id": self.stt_model, "tag_audio_events": "false"},
            files={"file": (filename, audio, content_type)},
            timeout=90,
        )
        _raise_for_provider_status(response.status_code)
        payload = response.json()
        transcript = payload.get("text")
        if not isinstance(transcript, str) or not transcript.strip():
            raise RuntimeError("Speech recognition did not return any text.")
        return transcript.strip()[:4000]

    def synthesize(self, text: str) -> tuple[bytes, str]:
        if not self.api_key:
            raise RuntimeError("ELEVENLABS_API_KEY is not configured in the local .env file.")
        if not self.voice_id:
            raise RuntimeError("ELEVENLABS_VOICE_ID is not configured in the local .env file.")
        response = httpx.post(
            f"{self.base_url}/text-to-speech/{quote(self.voice_id, safe='')}",
            headers={
                "xi-api-key": self.api_key,
                "Content-Type": "application/json",
                "Accept": "audio/mpeg",
            },
            json={
                "text": text[:4000],
                "model_id": self.tts_model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
            },
            params={"output_format": "mp3_44100_128"},
            timeout=90,
        )
        _raise_for_provider_status(response.status_code)
        if not response.content:
            raise RuntimeError("Text-to-speech returned empty audio.")
        return response.content, "audio/mpeg"


def _raise_for_provider_status(status_code: int) -> None:
    if status_code == 401:
        raise RuntimeError("The speech provider rejected its API key. Check ELEVENLABS_API_KEY.")
    if status_code == 429:
        raise RuntimeError("The speech provider is rate-limiting requests. Try again shortly.")
    if status_code >= 400:
        raise RuntimeError(f"The speech provider returned HTTP {status_code}.")