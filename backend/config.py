import json
import os
from pathlib import Path
from threading import RLock
from typing import Any

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")
SETTINGS_PATH = PROJECT_ROOT / "data" / "settings.json"

PERMITTED_APPLICATIONS = {"notepad", "calculator", "paint"}


def _split_directories(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(";") if part.strip()]


def _split_applications(raw: str) -> list[str]:
    return [part.strip().lower() for part in raw.split(",") if part.strip()]


def configured_value(name: str, default: str = "") -> str:
    value = os.getenv(name, default).strip()
    if value.lower().startswith(("replace-with-", "your-", "<")):
        return ""
    return value


class SettingsStore:
    """Non-secret app settings. API keys are read only from process environment."""

    def __init__(self) -> None:
        self._lock = RLock()
        self.allowed_directories = _split_directories(
            os.getenv("AV_ALLOWED_DIRECTORIES", "")
        )
        configured_apps = _split_applications(
            os.getenv("AV_ALLOWED_APPLICATIONS", "notepad,calculator")
        )
        self.allowed_applications = [
            app for app in configured_apps if app in PERMITTED_APPLICATIONS
        ]
        self._load_saved_settings()

    def _load_saved_settings(self) -> None:
        if not SETTINGS_PATH.is_file():
            return
        try:
            values = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
            directories = values.get("allowed_directories")
            applications = values.get("allowed_applications")
            if isinstance(directories, list) and all(
                isinstance(path, str) for path in directories
            ):
                self.allowed_directories = directories
            if isinstance(applications, list) and all(
                isinstance(app, str) for app in applications
            ):
                self.allowed_applications = [
                    app for app in applications if app in PERMITTED_APPLICATIONS
                ]
        except (OSError, ValueError, TypeError):
            # A malformed local preferences file must not stop the app from starting.
            return

    def update(self, values: dict[str, Any]) -> dict[str, list[str]]:
        directories = values.get("allowed_directories")
        applications = values.get("allowed_applications")
        if not isinstance(directories, list) or not all(
            isinstance(path, str) for path in directories
        ):
            raise ValueError("Allowed directories must be a list of folder paths.")
        if not isinstance(applications, list) or not all(
            isinstance(app, str) for app in applications
        ):
            raise ValueError("Allowed applications must be a list of application names.")
        if len(directories) > 25:
            raise ValueError("You can configure up to 25 search directories.")
        if len(applications) > len(PERMITTED_APPLICATIONS):
            raise ValueError("Choose only from the permitted application list.")

        normalized_directories: list[str] = []
        for raw_path in directories:
            path_text = raw_path.strip()
            if not path_text or len(path_text) > 2048:
                raise ValueError("Each directory must be a valid absolute folder path.")
            path = Path(path_text).expanduser()
            if not path.is_absolute() or not path.is_dir():
                raise ValueError(f"Folder does not exist or is not an absolute path: {path_text}")
            resolved = str(path.resolve(strict=True))
            if resolved not in normalized_directories:
                normalized_directories.append(resolved)

        normalized_apps: list[str] = []
        for app in applications:
            name = app.strip().lower()
            if name not in PERMITTED_APPLICATIONS:
                raise ValueError(f"{app!r} is not in the permitted application list.")
            if name not in normalized_apps:
                normalized_apps.append(name)

        with self._lock:
            SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
            temporary_path = SETTINGS_PATH.with_suffix(".tmp")
            temporary_path.write_text(
                json.dumps(
                    {
                        "allowed_directories": normalized_directories,
                        "allowed_applications": normalized_apps,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            temporary_path.replace(SETTINGS_PATH)
            self.allowed_directories = normalized_directories
            self.allowed_applications = normalized_apps
            return self.as_dict()

    def as_dict(self) -> dict[str, list[str]]:
        with self._lock:
            return {
                "allowed_directories": list(self.allowed_directories),
                "allowed_applications": list(self.allowed_applications),
            }