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
I64_MIN = -(2**63)
I64_MAX = 2**63 - 1


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
    if raw < I64_MIN or raw > I64_MAX:
        raise ValueError(f"{key} must fit in i64")
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


def _permission_grant_scope(value: JsonValue) -> PermissionGrantScope:
    if isinstance(value, PermissionGrantScope):
        return value
    if not isinstance(value, str):
        raise TypeError("scope must be a string")
    return PermissionGrantScope(value)


@dataclass(frozen=True)
class RequestPermissionProfile:
    network: NetworkPermissions | None = None
    file_system: FileSystemPermissions | None = None

    def __post_init__(self) -> None:
        if self.network is not None and not isinstance(self.network, NetworkPermissions):
            raise TypeError("network must be NetworkPermissions")
        if self.file_system is not None and not isinstance(self.file_system, FileSystemPermissions):
            raise TypeError("file_system must be FileSystemPermissions")

    def is_empty(self) -> bool:
        return self.network is None and self.file_system is None

    @classmethod
    def from_additional_permission_profile(
        cls,
        value: AdditionalPermissionProfile,
    ) -> "RequestPermissionProfile":
        if not isinstance(value, AdditionalPermissionProfile):
            raise TypeError("value must be AdditionalPermissionProfile")
        return cls(network=value.network, file_system=value.file_system)

    def to_additional_permission_profile(self) -> AdditionalPermissionProfile:
        return AdditionalPermissionProfile(network=self.network, file_system=self.file_system)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionProfile":
        data = _mapping(value, "request permission profile")
        unknown = set(data) - {"network", "file_system"}
        if unknown:
            raise ValueError(f"unknown field: {sorted(unknown)[0]}")
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

    def __post_init__(self) -> None:
        if not isinstance(self.permissions, RequestPermissionProfile):
            raise TypeError("permissions must be RequestPermissionProfile")
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionsArgs":
        data = _mapping(value, "request permissions args")
        return cls(
            permissions=RequestPermissionProfile.from_mapping(data["permissions"]),
            reason=_optional_str(data, "reason"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {"permissions": self.permissions.to_mapping()}
        if self.reason is not None:
            data["reason"] = self.reason
        return data


@dataclass(frozen=True)
class RequestPermissionsResponse:
    permissions: RequestPermissionProfile
    scope: PermissionGrantScope | str = PermissionGrantScope.TURN
    strict_auto_review: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.permissions, RequestPermissionProfile):
            raise TypeError("permissions must be RequestPermissionProfile")
        if not isinstance(self.scope, PermissionGrantScope):
            object.__setattr__(self, "scope", _permission_grant_scope(self.scope))
        if not isinstance(self.strict_auto_review, bool):
            raise TypeError("strict_auto_review must be a bool")

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionsResponse":
        data = _mapping(value, "request permissions response")
        return cls(
            permissions=RequestPermissionProfile.from_mapping(data["permissions"]),
            scope=_permission_grant_scope(data.get("scope", PermissionGrantScope.TURN.value)),
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

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.turn_id, str):
            raise TypeError("turn_id must be a string")
        if isinstance(self.started_at_ms, bool) or not isinstance(self.started_at_ms, int):
            raise TypeError("started_at_ms must be an integer")
        if self.started_at_ms < I64_MIN or self.started_at_ms > I64_MAX:
            raise ValueError("started_at_ms must fit in i64")
        if not isinstance(self.permissions, RequestPermissionProfile):
            raise TypeError("permissions must be RequestPermissionProfile")
        if self.reason is not None and not isinstance(self.reason, str):
            raise TypeError("reason must be a string")
        if self.cwd is not None and not isinstance(self.cwd, Path):
            if not isinstance(self.cwd, str):
                raise TypeError("cwd must be a string or Path")
            object.__setattr__(self, "cwd", Path(self.cwd))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "RequestPermissionsEvent":
        data = _mapping(value, "request permissions event")
        cwd = data.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise TypeError("cwd must be a string")
        turn_id = data.get("turn_id", "")
        if not isinstance(turn_id, str):
            raise TypeError("turn_id must be a string")
        return cls(
            call_id=_required_str(data, "call_id"),
            turn_id=turn_id,
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
