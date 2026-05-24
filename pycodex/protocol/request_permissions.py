"""Request-permissions protocol helpers.

Ported from ``codex/codex-rs/protocol/src/request_permissions.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from .models import AdditionalPermissionProfile, FileSystemPermissions, NetworkPermissions

JsonValue = Any


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_bool(value: dict[str, JsonValue], key: str) -> bool:
    raw = value.get(key)
    if not isinstance(raw, bool):
        raise TypeError(f"{key} must be a bool")
    return raw


def _required_int(value: dict[str, JsonValue], key: str) -> int:
    raw = value.get(key)
    if isinstance(raw, bool) or not isinstance(raw, int):
        raise TypeError(f"{key} must be an integer")
    return raw


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


class PermissionGrantScope(str, Enum):
    TURN = "turn"
    SESSION = "session"

    @classmethod
    def default(cls) -> "PermissionGrantScope":
        return cls.TURN


@dataclass(frozen=True)
class RequestPermissionProfile:
    network: NetworkPermissions | None = None
    file_system: FileSystemPermissions | None = None

    def is_empty(self) -> bool:
        return self.network is None and self.file_system is None

    @classmethod
    def from_additional_permission_profile(
        cls,
        value: AdditionalPermissionProfile,
    ) -> "RequestPermissionProfile":
        return cls(network=value.network, file_system=value.file_system)

    def to_additional_permission_profile(self) -> AdditionalPermissionProfile:
        return AdditionalPermissionProfile(network=self.network, file_system=self.file_system)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionProfile":
        data = _mapping(value, "request permission profile")
        return cls(
            network=NetworkPermissions.from_mapping(data["network"]) if data.get("network") is not None else None,
            file_system=FileSystemPermissions.from_mapping(data["file_system"]) if data.get("file_system") is not None else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {}
        if self.network is not None:
            data["network"] = self.network.to_mapping()
        if self.file_system is not None:
            data["file_system"] = self.file_system.to_mapping()
        return data


@dataclass(frozen=True)
class RequestPermissionsArgs:
    permissions: RequestPermissionProfile
    reason: str | None = None


@dataclass(frozen=True)
class RequestPermissionsResponse:
    permissions: RequestPermissionProfile
    scope: PermissionGrantScope | str = PermissionGrantScope.TURN
    strict_auto_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.scope, PermissionGrantScope):
            object.__setattr__(self, "scope", PermissionGrantScope(str(self.scope)))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionsResponse":
        data = _mapping(value, "request permissions response")
        return cls(
            permissions=RequestPermissionProfile.from_mapping(data["permissions"]),
            scope=PermissionGrantScope(str(data.get("scope", PermissionGrantScope.TURN.value))),
            strict_auto_review=_required_bool(data, "strict_auto_review") if "strict_auto_review" in data else False,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "permissions": self.permissions.to_mapping(),
            "scope": self.scope.value,
        }
        if self.strict_auto_review:
            data["strict_auto_review"] = True
        return data


@dataclass(frozen=True)
class RequestPermissionsEvent:
    call_id: str
    started_at_ms: int
    permissions: RequestPermissionProfile
    turn_id: str = ""
    reason: str | None = None
    cwd: Path | None = None

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionsEvent":
        data = _mapping(value, "request permissions event")
        cwd = data.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise TypeError("cwd must be a string")
        return cls(
            call_id=_required_str(data, "call_id"),
            turn_id=str(data.get("turn_id", "")),
            started_at_ms=_required_int(data, "started_at_ms"),
            reason=_optional_str(data, "reason"),
            permissions=RequestPermissionProfile.from_mapping(data["permissions"]),
            cwd=Path(cwd) if isinstance(cwd, str) else None,
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "call_id": self.call_id,
            "turn_id": self.turn_id,
            "started_at_ms": self.started_at_ms,
            "permissions": self.permissions.to_mapping(),
        }
        if self.reason is not None:
            data["reason"] = self.reason
        if self.cwd is not None:
            data["cwd"] = str(self.cwd)
        return data
