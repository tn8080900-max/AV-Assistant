from threading import RLock
from typing import Any, Protocol


class Memory(Protocol):
    def remember(self, data: dict[str, Any]) -> None: ...

    def retrieve(self, query: str | None = None) -> list[dict[str, Any]]: ...


class SessionMemory:
    """In-memory conversation history. Nothing is written to disk."""

    def __init__(self, max_messages: int = 40) -> None:
        self._messages: list[dict[str, Any]] = []
        self._max_messages = max_messages
        self._lock = RLock()

    def remember(self, data: dict[str, Any]) -> None:
        with self._lock:
            self._messages.append(data)
            if len(self._messages) > self._max_messages:
                remove_count = len(self._messages) - self._max_messages
                while (
                    remove_count < len(self._messages)
                    and self._messages[remove_count].get("role") != "user"
                ):
                    remove_count += 1
                self._messages = self._messages[remove_count:]

    def retrieve(self, query: str | None = None) -> list[dict[str, Any]]:
        del query
        with self._lock:
            return [message.copy() for message in self._messages]

    def clear(self) -> None:
        with self._lock:
            self._messages.clear()