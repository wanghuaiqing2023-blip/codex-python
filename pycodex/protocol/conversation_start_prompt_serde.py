"""Double-option serialization for realtime conversation prompts.

Ported from the private
``codex-protocol::protocol::conversation_start_prompt_serde`` module.
"""

from __future__ import annotations

from typing import Any


PROMPT_UNSET = object()


def deserialize(mapping: dict[str, Any], key: str = "prompt") -> str | None | object:
    if key not in mapping:
        return PROMPT_UNSET
    value = mapping[key]
    if value is not None and not isinstance(value, str):
        raise TypeError(f"{key} must be a string or null")
    return value


def serialize(
    target: dict[str, Any],
    value: str | None | object,
    key: str = "prompt",
) -> None:
    if value is not PROMPT_UNSET:
        target[key] = value
