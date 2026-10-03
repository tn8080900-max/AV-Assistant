import os
from pathlib import Path


MAX_RESULTS = 30
MAX_VISITED = 12_000
MAX_DEPTH = 8
EXCLUDED_DIRECTORIES = {
    ".git",
    ".ssh",
    ".aws",
    ".azure",
    ".gnupg",
    "appdata",
    "node_modules",
    "__pycache__",
    "system volume information",
    "$recycle.bin",
    "windows",
    "program files",
    "program files (x86)",
}
SENSITIVE_NAME_PARTS = (
    ".env",
    "credential",
    "password",
    "secret",
    "token",
    "cookie",
    "private key",
    "id_rsa",
)


def is_sensitive_name(name: str) -> bool:
    lowered = name.lower()
    return lowered.startswith(".") or any(part in lowered for part in SENSITIVE_NAME_PARTS)


def is_inside_configured_directory(candidate: Path, directories: list[str]) -> bool:
    try:
        resolved = candidate.resolve(strict=True)
    except OSError:
        return False
    for raw_root in directories:
        try:
            root = Path(raw_root).resolve(strict=True)
            resolved.relative_to(root)
            return True
        except (OSError, ValueError):
            continue
    return False


def search_files(query: str, directories: list[str]) -> list[str]:
    needle = query.strip().casefold()
    if not needle or len(needle) > 200:
        raise ValueError("Enter a filename search under 200 characters.")
    if not directories:
        raise ValueError("No search directories are configured yet. Add one in Settings.")

    results: list[str] = []
    visited = 0
    for raw_root in directories:
        root = Path(raw_root).expanduser().resolve(strict=True)
        if not root.is_dir():
            continue
        for current, subdirectories, files in os.walk(root, followlinks=False):
            depth = len(Path(current).relative_to(root).parts)
            subdirectories[:] = [
                name
                for name in subdirectories
                if name.casefold() not in EXCLUDED_DIRECTORIES
                and not name.startswith(".")
                and not (Path(current) / name).is_symlink()
            ]
            if depth >= MAX_DEPTH:
                subdirectories.clear()
            for filename in files:
                visited += 1
                if visited > MAX_VISITED:
                    return results
                if is_sensitive_name(filename) or needle not in filename.casefold():
                    continue
                full_path = Path(current) / filename
                if full_path.is_symlink() or not is_inside_configured_directory(full_path, directories):
                    continue
                results.append(str(full_path))
                if len(results) >= MAX_RESULTS:
                    return results
    return results


def validate_deletion_target(raw_path: str, directories: list[str]) -> Path:
    candidate_text = raw_path.strip()
    if not candidate_text or len(candidate_text) > 2048:
        raise ValueError("A valid file path is required.")
    candidate = Path(candidate_text).expanduser()
    if not candidate.is_absolute():
        raise ValueError("The file path must be absolute.")
    if is_sensitive_name(candidate.name):
        raise ValueError("Files that may contain credentials or private data cannot be deleted by the agent.")
    if any(
        part.startswith(".") or part.casefold() in EXCLUDED_DIRECTORIES
        for part in candidate.parts[:-1]
    ):
        raise ValueError("Files in hidden, credential, or system folders cannot be deleted by the agent.")
    if not is_inside_configured_directory(candidate, directories):
        raise ValueError("That file is outside the directories you configured.")
    resolved = candidate.resolve(strict=True)
    if resolved.is_symlink() or not resolved.is_file():
        raise ValueError("Only existing regular files can be deleted.")
    return resolved