from typing import Protocol


class SpeechToText(Protocol):
    def transcribe(self, audio: bytes, filename: str, content_type: str) -> str: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str) -> tuple[bytes, str]: ...