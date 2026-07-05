"""Notification protocol types ported from ``protocol/v2/notification.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import RequestId

JsonValue = Any


@dataclass(frozen=True)
class DeprecationNoticeNotification:
    summary: str
    details: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "summary", _ensure_str(self.summary, "summary"))
        object.__setattr__(self, "details", _optional_str(self.details, "details"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "DeprecationNoticeNotification":
        _ensure_mapping(value, "DeprecationNoticeNotification")
        return cls(
            summary=_ensure_str(value["summary"], "summary"),
            details=_optional_str(_pick(value, "details"), "details"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"summary": self.summary, "details": self.details}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class WarningNotification:
    message: str
    thread_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WarningNotification":
        _ensure_mapping(value, "WarningNotification")
        return cls(
            thread_id=_optional_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            message=_ensure_str(value["message"], "message"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "message": self.message}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "message": self.message}


@dataclass(frozen=True)
class GuardianWarningNotification:
    thread_id: str
    message: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "message", _ensure_str(self.message, "message"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GuardianWarningNotification":
        _ensure_mapping(value, "GuardianWarningNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            message=_ensure_str(value["message"], "message"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "message": self.message}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "message": self.message}


@dataclass(frozen=True)
class ErrorNotification:
    error: JsonValue
    will_retry: bool
    thread_id: str
    turn_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "error", _turn_error_value(self.error, "error"))
        object.__setattr__(self, "will_retry", _ensure_bool(self.will_retry, "will_retry"))
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "turn_id", _ensure_str(self.turn_id, "turn_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ErrorNotification":
        _ensure_mapping(value, "ErrorNotification")
        return cls(
            error=_turn_error_value(value["error"], "error"),
            will_retry=_ensure_bool(_pick(value, "will_retry", "willRetry"), "will_retry"),
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            turn_id=_ensure_str(_pick(value, "turn_id", "turnId"), "turn_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "error": _serialize_error(self.error, camel=False),
            "will_retry": self.will_retry,
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "error": _serialize_error(self.error, camel=True),
            "willRetry": self.will_retry,
            "threadId": self.thread_id,
            "turnId": self.turn_id,
        }


@dataclass(frozen=True)
class ServerRequestResolvedNotification:
    thread_id: str
    request_id: RequestId | str | int

    def __post_init__(self) -> None:
        object.__setattr__(self, "thread_id", _ensure_str(self.thread_id, "thread_id"))
        object.__setattr__(self, "request_id", RequestId.from_value(self.request_id))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ServerRequestResolvedNotification":
        _ensure_mapping(value, "ServerRequestResolvedNotification")
        return cls(
            thread_id=_ensure_str(_pick(value, "thread_id", "threadId"), "thread_id"),
            request_id=RequestId.from_value(_pick(value, "request_id", "requestId")),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"thread_id": self.thread_id, "request_id": self.request_id.to_json()}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"threadId": self.thread_id, "requestId": self.request_id.to_json()}


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _turn_error_value(value: JsonValue, field_name: str) -> JsonValue:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "to_mapping") or hasattr(value, "to_camel_mapping"):
        return value
    raise TypeError(f"{field_name} must be a TurnError-compatible mapping")


def _serialize_error(value: JsonValue, *, camel: bool) -> JsonValue:
    if camel and hasattr(value, "to_camel_mapping"):
        return value.to_camel_mapping()
    if hasattr(value, "to_mapping"):
        return value.to_mapping()
    if isinstance(value, Mapping):
        return dict(value)
    return value


__all__ = [
    "DeprecationNoticeNotification",
    "ErrorNotification",
    "GuardianWarningNotification",
    "ServerRequestResolvedNotification",
    "WarningNotification",
]
