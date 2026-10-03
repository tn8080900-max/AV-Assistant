from enum import StrEnum


class PermissionLevel(StrEnum):
    SAFE = "SAFE"
    REQUIRES_CONFIRMATION = "REQUIRES_CONFIRMATION"


def may_run_automatically(level: PermissionLevel) -> bool:
    return level == PermissionLevel.SAFE