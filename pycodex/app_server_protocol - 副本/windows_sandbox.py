"""Windows sandbox protocol types ported from ``protocol/v2/windows_sandbox.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

JsonValue = Any


class _StringEnum(str, Enum):
    @classmethod
    def parse(cls, value: JsonValue):
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError(f"{cls.__name__} value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid {cls.__name__}: {raw}; expected one of: {choices}") from exc


class WindowsSandboxSetupMode(_StringEnum):
    ELEVATED = "elevated"
    UNELEVATED = "unelevated"


class WindowsSandboxReadiness(_StringEnum):
    READY = "ready"
    NOT_CONFIGURED = "notConfigured"
    UPDATE_REQUIRED = "updateRequired"


@dataclass(frozen=True)
class WindowsWorldWritableWarningNotification:
    sample_paths: tuple[str, ...]
    extra_count: int
    failed_scan: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "sample_paths", _string_tuple(self.sample_paths, "sample_paths"))
        object.__setattr__(self, "extra_count", _usize(self.extra_count, "extra_count"))
        object.__setattr__(self, "failed_scan", _ensure_bool(self.failed_scan, "failed_scan"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WindowsWorldWritableWarningNotification":
        _ensure_mapping(value, "WindowsWorldWritableWarningNotification")
        return cls(
            sample_paths=_string_tuple(_pick(value, "sample_paths", "samplePaths"), "sample_paths"),
            extra_count=_usize(_pick(value, "extra_count", "extraCount"), "extra_count"),
            failed_scan=_ensure_bool(_pick(value, "failed_scan", "failedScan"), "failed_scan"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "sample_paths": list(self.sample_paths),
            "extra_count": self.extra_count,
            "failed_scan": self.failed_scan,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "samplePaths": list(self.sample_paths),
            "extraCount": self.extra_count,
            "failedScan": self.failed_scan,
        }


@dataclass(frozen=True)
class WindowsSandboxSetupStartParams:
    mode: WindowsSandboxSetupMode | str
    cwd: Path | str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", WindowsSandboxSetupMode.parse(self.mode))
        object.__setattr__(self, "cwd", _optional_absolute_path(self.cwd, "cwd"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WindowsSandboxSetupStartParams":
        _ensure_mapping(value, "WindowsSandboxSetupStartParams")
        return cls(
            mode=WindowsSandboxSetupMode.parse(value["mode"]),
            cwd=_optional_absolute_path(_pick(value, "cwd"), "cwd"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"mode": self.mode.value, "cwd": None if self.cwd is None else str(self.cwd)}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class WindowsSandboxSetupStartResponse:
    started: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "started", _ensure_bool(self.started, "started"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WindowsSandboxSetupStartResponse":
        _ensure_mapping(value, "WindowsSandboxSetupStartResponse")
        return cls(started=_ensure_bool(value["started"], "started"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"started": self.started}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class WindowsSandboxReadinessResponse:
    status: WindowsSandboxReadiness | str

    def __post_init__(self) -> None:
        object.__setattr__(self, "status", WindowsSandboxReadiness.parse(self.status))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WindowsSandboxReadinessResponse":
        _ensure_mapping(value, "WindowsSandboxReadinessResponse")
        return cls(status=WindowsSandboxReadiness.parse(value["status"]))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"status": self.status.value}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class WindowsSandboxSetupCompletedNotification:
    mode: WindowsSandboxSetupMode | str
    success: bool
    error: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "mode", WindowsSandboxSetupMode.parse(self.mode))
        object.__setattr__(self, "success", _ensure_bool(self.success, "success"))
        object.__setattr__(self, "error", _optional_str(self.error, "error"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "WindowsSandboxSetupCompletedNotification":
        _ensure_mapping(value, "WindowsSandboxSetupCompletedNotification")
        return cls(
            mode=WindowsSandboxSetupMode.parse(value["mode"]),
            success=_ensure_bool(value["success"], "success"),
            error=_optional_str(_pick(value, "error"), "error"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "mode": self.mode.value,
            "success": self.success,
            "error": self.error,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], *names: str, default: JsonValue = None) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    return default


def _ensure_bool(value: JsonValue, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"{field_name} must be a bool")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _usize(value: JsonValue, field_name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise TypeError(f"{field_name} must be a non-negative integer")
    return value


def _string_tuple(value: JsonValue, field_name: str) -> tuple[str, ...]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable of strings")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} item must be a string")
        result.append(item)
    return tuple(result)


def _optional_absolute_path(value: JsonValue, field_name: str) -> Path | None:
    if value is None:
        return None
    if isinstance(value, Path):
        path = value
    elif isinstance(value, str):
        path = Path(value)
    else:
        raise TypeError(f"{field_name} must be a path string, Path, or None")
    if not path.is_absolute():
        raise ValueError(f"{field_name} must be an absolute path")
    return path


__all__ = [
    "WindowsSandboxReadiness",
    "WindowsSandboxReadinessResponse",
    "WindowsSandboxSetupCompletedNotification",
    "WindowsSandboxSetupMode",
    "WindowsSandboxSetupStartParams",
    "WindowsSandboxSetupStartResponse",
    "WindowsWorldWritableWarningNotification",
]
