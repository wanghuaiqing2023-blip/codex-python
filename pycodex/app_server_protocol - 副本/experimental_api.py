"""Experimental API helpers ported from ``experimental_api.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

JsonValue = Any


@runtime_checkable
class ExperimentalApi(Protocol):
    """Protocol for values that can report experimental API usage."""

    def experimental_reason(self) -> str | None:
        """Return the experimental reason identifier, or ``None``."""


@dataclass(frozen=True)
class ExperimentalField:
    type_name: str
    field_name: str
    reason: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "type_name", _ensure_str(self.type_name, "type_name"))
        object.__setattr__(self, "field_name", _ensure_str(self.field_name, "field_name"))
        object.__setattr__(self, "reason", _ensure_str(self.reason, "reason"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExperimentalField":
        data = _mapping(value, "ExperimentalField")
        return cls(
            type_name=_ensure_str(_pick(data, "type_name", "typeName"), "type_name"),
            field_name=_ensure_str(_pick(data, "field_name", "fieldName"), "field_name"),
            reason=_ensure_str(data["reason"], "reason"),
        )

    def to_mapping(self) -> dict[str, str]:
        return {"type_name": self.type_name, "field_name": self.field_name, "reason": self.reason}

    def to_camel_mapping(self) -> dict[str, str]:
        return {"typeName": self.type_name, "fieldName": self.field_name, "reason": self.reason}


_EXPERIMENTAL_FIELDS: list[ExperimentalField] = []


def register_experimental_field(type_name: str, field_name: str, reason: str) -> ExperimentalField:
    field = ExperimentalField(type_name=type_name, field_name=field_name, reason=reason)
    _EXPERIMENTAL_FIELDS.append(field)
    return field


def experimental_fields() -> list[ExperimentalField]:
    return list(_EXPERIMENTAL_FIELDS)


def clear_experimental_fields() -> None:
    _EXPERIMENTAL_FIELDS.clear()


def experimental_required_message(reason: str) -> str:
    return f"{_ensure_str(reason, 'reason')} requires experimentalApi capability"


def experimental_reason(value: JsonValue) -> str | None:
    """Mirror Rust's blanket impls for option/list/map-like containers."""

    if value is None:
        return None
    if isinstance(value, ExperimentalApi):
        return value.experimental_reason()
    if isinstance(value, Mapping):
        for item in value.values():
            reason = experimental_reason(item)
            if reason is not None:
                return reason
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            reason = experimental_reason(item)
            if reason is not None:
                return reason
        return None
    return None


@dataclass(frozen=True)
class ExperimentalReason:
    """Simple value helper for tests and protocol shims."""

    reason: str | None = None

    def experimental_reason(self) -> str | None:
        return self.reason


def _mapping(value: JsonValue, type_name: str) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} must be a mapping")
    return value


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


__all__ = [
    "ExperimentalApi",
    "ExperimentalField",
    "ExperimentalReason",
    "clear_experimental_fields",
    "experimental_fields",
    "experimental_reason",
    "experimental_required_message",
    "register_experimental_field",
]
