"""Port of Rust ``codex-login::auth::util``.

Rust source:
- ``codex/codex-rs/login/src/auth/util.rs``
"""

from __future__ import annotations

import json


def try_parse_error_message(text: str) -> str:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = {}

    if isinstance(value, dict):
        error = value.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str):
                return message

    if text == "":
        return "Unknown error"
    return text


__all__ = [
    "try_parse_error_message",
]
