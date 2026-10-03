import os
import platform
import subprocess


# Deliberately fixed executable arguments: never accept an executable or flags
# from model output.
WINDOWS_APPLICATIONS: dict[str, list[str]] = {
    "notepad": ["notepad.exe"],
    "calculator": ["calc.exe"],
    "paint": ["mspaint.exe"],
}


def launch_application(name: str, allowed_applications: list[str]) -> str:
    normalized = name.strip().lower()
    if normalized not in allowed_applications or normalized not in WINDOWS_APPLICATIONS:
        permitted = ", ".join(sorted(allowed_applications)) or "none configured"
        raise ValueError(f"{name!r} is not permitted. Allowed applications: {permitted}.")
    if platform.system() != "Windows":
        raise RuntimeError("Application launching is available only on Windows.")
    try:
        subprocess.Popen(
            WINDOWS_APPLICATIONS[normalized],
            shell=False,
            close_fds=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except OSError as exc:
        raise RuntimeError(f"Windows could not start {normalized}.") from exc
    return f"Opened {normalized}."