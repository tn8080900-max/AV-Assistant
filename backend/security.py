import re


_SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(
        r"(?i)\b(api[_ -]?key|password|passwd|secret|token|authorization)"
        r"(\s*[:=]\s*)((?:bearer\s+)?[^\s,;]+)"
    ),
    re.compile(r"(?i)([?&](?:api[_-]?key|token|access_token|password)=)[^&#\s]+"),
)


def redact_secrets(value: str) -> str:
    redacted = value
    for pattern in _SECRET_PATTERNS:
        if pattern.groups == 3:
            redacted = pattern.sub(r"\1\2[REDACTED]", redacted)
        elif pattern.groups == 1:
            redacted = pattern.sub(r"\1[REDACTED]", redacted)
        else:
            redacted = pattern.sub("[REDACTED]", redacted)
    return redacted[:1000]