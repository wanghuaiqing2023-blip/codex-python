"""Secret redaction helpers from Rust ``codex-secrets::sanitizer``.

Rust source:
- ``codex/codex-rs/secrets/src/sanitizer.rs``
"""

from __future__ import annotations

import re


REDACTED_SECRET = "[REDACTED_SECRET]"

OPENAI_KEY_REGEX = re.compile(r"sk-[A-Za-z0-9]{20,}")
AWS_ACCESS_KEY_ID_REGEX = re.compile(r"\bAKIA[0-9A-Z]{16}\b")
BEARER_TOKEN_REGEX = re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{16,}\b", re.IGNORECASE)
SECRET_ASSIGNMENT_REGEX = re.compile(
    r"\b(api[_-]?key|token|secret|password)\b(\s*[:=]\s*)([\"']?)[^\s\"']{8,}",
    re.IGNORECASE,
)


def redact_secrets(input: str) -> str:
    redacted = OPENAI_KEY_REGEX.sub(REDACTED_SECRET, input)
    redacted = AWS_ACCESS_KEY_ID_REGEX.sub(REDACTED_SECRET, redacted)
    redacted = BEARER_TOKEN_REGEX.sub(f"Bearer {REDACTED_SECRET}", redacted)
    redacted = SECRET_ASSIGNMENT_REGEX.sub(rf"\1\2\3{REDACTED_SECRET}", redacted)
    return redacted


__all__ = [
    "AWS_ACCESS_KEY_ID_REGEX",
    "BEARER_TOKEN_REGEX",
    "OPENAI_KEY_REGEX",
    "REDACTED_SECRET",
    "SECRET_ASSIGNMENT_REGEX",
    "redact_secrets",
]
