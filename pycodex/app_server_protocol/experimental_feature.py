"""Experimental feature protocol types ported from ``protocol/v2/experimental_feature.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

JsonValue = Any


class ExperimentalFeatureStage(str, Enum):
    BETA = "beta"
    UNDER_DEVELOPMENT = "underDevelopment"
    STABLE = "stable"
    DEPRECATED = "deprecated"
    REMOVED = "removed"

    @classmethod
    def parse(cls, value: JsonValue) -> "ExperimentalFeatureStage":
        raw = getattr(value, "value", value)
        if not isinstance(raw, str):
            raise TypeError("ExperimentalFeatureStage value must be a string")
        try:
            return cls(raw)
        except ValueError as exc:
            choices = ", ".join(member.value for member in cls)
            raise ValueError(f"invalid ExperimentalFeatureStage: {raw}; expected one of: {choices}") from exc


@dataclass(frozen=True)
class ExperimentalFeatureListParams:
    cursor: str | None = None
    limit: int | None = None
    thread_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "cursor", _optional_str(self.cursor, "cursor"))
        object.__setattr__(self, "limit", _optional_u32(self.limit, "limit"))
        object.__setattr__(self, "thread_id", _optional_str(self.thread_id, "thread_id"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ExperimentalFeatureListParams":
        if value is None:
            return cls()
        _ensure_mapping(value, "ExperimentalFeatureListParams")
        return cls(
            cursor=_optional_str(_pick(value, "cursor"), "cursor"),
            limit=_optional_u32(_pick(value, "limit"), "limit"),
            thread_id=_optional_str(_pick(value, "thread_id", "threadId"), "thread_id"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"cursor": self.cursor, "limit": self.limit, "thread_id": self.thread_id}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"cursor": self.cursor, "limit": self.limit, "threadId": self.thread_id}


@dataclass(frozen=True)
class ExperimentalFeature:
    name: str
    stage: ExperimentalFeatureStage | str
    display_name: str | None = None
    description: str | None = None
    announcement: str | None = None
    enabled: bool = False
    default_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "stage", ExperimentalFeatureStage.parse(self.stage))
        object.__setattr__(self, "display_name", _optional_str(self.display_name, "display_name"))
        object.__setattr__(self, "description", _optional_str(self.description, "description"))
        object.__setattr__(self, "announcement", _optional_str(self.announcement, "announcement"))
        object.__setattr__(self, "enabled", _ensure_bool(self.enabled, "enabled"))
        object.__setattr__(self, "default_enabled", _ensure_bool(self.default_enabled, "default_enabled"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExperimentalFeature":
        _ensure_mapping(value, "ExperimentalFeature")
        return cls(
            name=_ensure_str(value["name"], "name"),
            stage=ExperimentalFeatureStage.parse(value["stage"]),
            display_name=_optional_str(_pick(value, "display_name", "displayName"), "display_name"),
            description=_optional_str(_pick(value, "description"), "description"),
            announcement=_optional_str(_pick(value, "announcement"), "announcement"),
            enabled=_ensure_bool(value["enabled"], "enabled"),
            default_enabled=_ensure_bool(_pick(value, "default_enabled", "defaultEnabled"), "default_enabled"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "stage": self.stage.value,
            "display_name": self.display_name,
            "description": self.description,
            "announcement": self.announcement,
            "enabled": self.enabled,
            "default_enabled": self.default_enabled,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "stage": self.stage.value,
            "displayName": self.display_name,
            "description": self.description,
            "announcement": self.announcement,
            "enabled": self.enabled,
            "defaultEnabled": self.default_enabled,
        }


@dataclass(frozen=True)
class ExperimentalFeatureListResponse:
    data: tuple[ExperimentalFeature, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _feature_tuple(self.data, "data"))
        object.__setattr__(self, "next_cursor", _optional_str(self.next_cursor, "next_cursor"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExperimentalFeatureListResponse":
        _ensure_mapping(value, "ExperimentalFeatureListResponse")
        return cls(
            data=tuple(ExperimentalFeature.from_mapping(item) for item in _iterable(value["data"], "data")),
            next_cursor=_optional_str(_pick(value, "next_cursor", "nextCursor"), "next_cursor"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": [item.to_mapping() for item in self.data],
            "next_cursor": self.next_cursor,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "data": [item.to_camel_mapping() for item in self.data],
            "nextCursor": self.next_cursor,
        }


@dataclass(frozen=True)
class ExperimentalFeatureEnablementSetParams:
    enablement: dict[str, bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "enablement", _bool_map(self.enablement, "enablement"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "ExperimentalFeatureEnablementSetParams":
        if value is None:
            return cls()
        _ensure_mapping(value, "ExperimentalFeatureEnablementSetParams")
        return cls(enablement=_bool_map(_pick(value, "enablement", default={}), "enablement"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"enablement": dict(self.enablement)}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


@dataclass(frozen=True)
class ExperimentalFeatureEnablementSetResponse:
    enablement: dict[str, bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "enablement", _bool_map(self.enablement, "enablement"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "ExperimentalFeatureEnablementSetResponse":
        _ensure_mapping(value, "ExperimentalFeatureEnablementSetResponse")
        return cls(enablement=_bool_map(value["enablement"], "enablement"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"enablement": dict(self.enablement)}

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


def _optional_u32(value: JsonValue, field_name: str) -> int | None:
    if value is None:
        return None
    if not isinstance(value, int) or isinstance(value, bool) or value < 0 or value > 2**32 - 1:
        raise TypeError(f"{field_name} must be an unsigned 32-bit integer")
    return value


def _iterable(value: JsonValue, field_name: str) -> Iterable[JsonValue]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    return value


def _feature_tuple(value: JsonValue, field_name: str) -> tuple[ExperimentalFeature, ...]:
    result: list[ExperimentalFeature] = []
    for item in _iterable(value, field_name):
        if isinstance(item, ExperimentalFeature):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(ExperimentalFeature.from_mapping(item))
        else:
            raise TypeError(f"{field_name} item must be ExperimentalFeature or mapping")
    return tuple(result)


def _bool_map(value: JsonValue, field_name: str) -> dict[str, bool]:
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be a mapping")
    return {
        _ensure_str(key, f"{field_name} key"): _ensure_bool(item, f"{field_name} value")
        for key, item in value.items()
    }


__all__ = [
    "ExperimentalFeature",
    "ExperimentalFeatureEnablementSetParams",
    "ExperimentalFeatureEnablementSetResponse",
    "ExperimentalFeatureListParams",
    "ExperimentalFeatureListResponse",
    "ExperimentalFeatureStage",
]
