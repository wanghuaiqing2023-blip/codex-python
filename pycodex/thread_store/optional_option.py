"""Rust ``codex-thread-store::types::optional_option`` owner."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class _ClearField:
    pass


_CLEAR_FIELD = _ClearField()
ClearableField = Any


def clear_field() -> _ClearField:
    """Represent Rust ``Some(None)`` for a clearable metadata field."""

    return _CLEAR_FIELD


def is_clear_field(value: Any) -> bool:
    return isinstance(value, _ClearField)


def deserialize(value: Mapping[str, Any], key: str, *, parser: Any = None) -> Any:
    """Deserialize a present null separately from an omitted field."""

    if key not in value:
        return None
    raw = value[key]
    if raw is None:
        return clear_field()
    return parser(raw) if parser is not None else raw


def serialize(output: dict[str, Any], key: str, value: Any) -> None:
    """Serialize an optional-option field using Rust's omission semantics."""

    if value is None:
        return
    if is_clear_field(value):
        output[key] = None
        return
    output[key] = getattr(value, "value", value)
