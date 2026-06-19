"""Remote-control protocol types ported from ``protocol/v2/remote_control.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

JsonValue = Any


class RemoteControlConnectionStatus(str, Enum):
    DISABLED = "disabled"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERRORED = "errored"

    @classmethod
    def parse(cls, value: JsonValue) -> "RemoteControlConnectionStatus":
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError("RemoteControlConnectionStatus value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid RemoteControlConnectionStatus: {raw}; expected one of: {choices}") from exc


@dataclass(frozen=True)
class RemoteControlStatusChangedNotification:
    status: RemoteControlConnectionStatus | str
    server_name: str
    installation_id: str
    environment_id: str | None = None

    def __post_init__(self) -> None:
        _normalize_remote_control_fields(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RemoteControlStatusChangedNotification":
        return cls(**_remote_control_kwargs(value, "RemoteControlStatusChangedNotification"))

    def to_enable_response(self) -> "RemoteControlEnableResponse":
        return RemoteControlEnableResponse.from_notification(self)

    def to_disable_response(self) -> "RemoteControlDisableResponse":
        return RemoteControlDisableResponse.from_notification(self)

    def to_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=False)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=True)


@dataclass(frozen=True)
class RemoteControlEnableResponse:
    status: RemoteControlConnectionStatus | str
    server_name: str
    installation_id: str
    environment_id: str | None = None

    def __post_init__(self) -> None:
        _normalize_remote_control_fields(self)

    @classmethod
    def from_notification(
        cls,
        notification: RemoteControlStatusChangedNotification,
    ) -> "RemoteControlEnableResponse":
        if not isinstance(notification, RemoteControlStatusChangedNotification):
            raise TypeError("notification must be RemoteControlStatusChangedNotification")
        return cls(
            status=notification.status,
            server_name=notification.server_name,
            installation_id=notification.installation_id,
            environment_id=notification.environment_id,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RemoteControlEnableResponse":
        return cls(**_remote_control_kwargs(value, "RemoteControlEnableResponse"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=False)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=True)


@dataclass(frozen=True)
class RemoteControlDisableResponse:
    status: RemoteControlConnectionStatus | str
    server_name: str
    installation_id: str
    environment_id: str | None = None

    def __post_init__(self) -> None:
        _normalize_remote_control_fields(self)

    @classmethod
    def from_notification(
        cls,
        notification: RemoteControlStatusChangedNotification,
    ) -> "RemoteControlDisableResponse":
        if not isinstance(notification, RemoteControlStatusChangedNotification):
            raise TypeError("notification must be RemoteControlStatusChangedNotification")
        return cls(
            status=notification.status,
            server_name=notification.server_name,
            installation_id=notification.installation_id,
            environment_id=notification.environment_id,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RemoteControlDisableResponse":
        return cls(**_remote_control_kwargs(value, "RemoteControlDisableResponse"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=False)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=True)


@dataclass(frozen=True)
class RemoteControlStatusReadResponse:
    status: RemoteControlConnectionStatus | str
    server_name: str
    installation_id: str
    environment_id: str | None = None

    def __post_init__(self) -> None:
        _normalize_remote_control_fields(self)

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "RemoteControlStatusReadResponse":
        return cls(**_remote_control_kwargs(value, "RemoteControlStatusReadResponse"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=False)

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return _remote_control_mapping(self, camel=True)


def _remote_control_kwargs(value: Mapping[str, JsonValue], type_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")
    return {
        "status": RemoteControlConnectionStatus.parse(value["status"]),
        "server_name": _ensure_str(_pick(value, "server_name", "serverName"), "server_name"),
        "installation_id": _ensure_str(_pick(value, "installation_id", "installationId"), "installation_id"),
        "environment_id": _optional_str(_pick(value, "environment_id", "environmentId"), "environment_id"),
    }


def _normalize_remote_control_fields(value: object) -> None:
    object.__setattr__(
        value,
        "status",
        RemoteControlConnectionStatus.parse(getattr(value, "status")),
    )
    object.__setattr__(value, "server_name", _ensure_str(getattr(value, "server_name"), "server_name"))
    object.__setattr__(
        value,
        "installation_id",
        _ensure_str(getattr(value, "installation_id"), "installation_id"),
    )
    object.__setattr__(
        value,
        "environment_id",
        _optional_str(getattr(value, "environment_id"), "environment_id"),
    )


def _remote_control_mapping(value: object, *, camel: bool) -> dict[str, JsonValue]:
    return {
        "status": getattr(value, "status").value,
        "serverName" if camel else "server_name": getattr(value, "server_name"),
        "installationId" if camel else "installation_id": getattr(value, "installation_id"),
        "environmentId" if camel else "environment_id": getattr(value, "environment_id"),
    }


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


__all__ = [
    "RemoteControlConnectionStatus",
    "RemoteControlDisableResponse",
    "RemoteControlEnableResponse",
    "RemoteControlStatusChangedNotification",
    "RemoteControlStatusReadResponse",
]
