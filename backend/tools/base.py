from dataclasses import dataclass
from typing import Any, Callable

from backend.permissions.manager import PermissionLevel


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict[str, Any]
    permission: PermissionLevel
    handler: Callable[[dict[str, Any]], str]
    validator: Callable[[dict[str, Any]], dict[str, Any]] | None = None

    def execute(self, arguments: dict[str, Any]) -> str:
        return self.handler(arguments)

    def validate_arguments(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.validator is None:
            return arguments
        return self.validator(arguments)

    def openai_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
                "strict": True,
            },
        }