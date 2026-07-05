"""Collaboration mode protocol types ported from ``protocol/v2/collaboration_mode.rs``."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any

from pycodex.protocol import CollaborationModeMask as CoreCollaborationModeMask
from pycodex.protocol import ModeKind, ReasoningEffort
from pycodex.protocol.config_types import _UNSET as CORE_UNSET

JsonValue = Any
UNSET_REASONING_EFFORT = object()


@dataclass(frozen=True)
class CollaborationModeListParams:
    """Empty params object for the experimental collaboration mode list API."""

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "CollaborationModeListParams":
        if value is not None and not isinstance(value, Mapping):
            raise TypeError("CollaborationModeListParams mapping must be a mapping")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class CollaborationModeMask:
    name: str
    mode: ModeKind | str | None = None
    model: str | None = None
    reasoning_effort: ReasoningEffort | str | None | object = UNSET_REASONING_EFFORT

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _ensure_str(self.name, "name"))
        object.__setattr__(self, "mode", _optional_mode_kind(self.mode, "mode"))
        object.__setattr__(self, "model", _optional_str(self.model, "model"))
        object.__setattr__(
            self,
            "reasoning_effort",
            _optional_reasoning_effort_or_unset(self.reasoning_effort, "reasoning_effort"),
        )

    @classmethod
    def from_core_mask(cls, value: CoreCollaborationModeMask) -> "CollaborationModeMask":
        if not isinstance(value, CoreCollaborationModeMask):
            raise TypeError("value must be a pycodex.protocol.CollaborationModeMask")
        return cls(
            name=value.name,
            mode=value.mode,
            model=value.model,
            reasoning_effort=value.reasoning_effort,
        )

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CollaborationModeMask":
        _ensure_mapping(value, "CollaborationModeMask")
        return cls(
            name=_ensure_str(value["name"], "name"),
            mode=_optional_mode_kind(_pick(value, "mode"), "mode"),
            model=_optional_str(_pick(value, "model"), "model"),
            reasoning_effort=(
                _optional_reasoning_effort(_pick(value, "reasoning_effort"), "reasoning_effort")
                if "reasoning_effort" in value
                else UNSET_REASONING_EFFORT
            ),
        )

    def to_core_mask(self) -> CoreCollaborationModeMask:
        return CoreCollaborationModeMask(
            name=self.name,
            mode=self.mode,
            model=self.model,
            reasoning_effort=(
                CORE_UNSET
                if self.reasoning_effort is UNSET_REASONING_EFFORT
                else self.reasoning_effort
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        result: dict[str, JsonValue] = {
            "name": self.name,
            "mode": None if self.mode is None else self.mode.value,
            "model": self.model,
        }
        if self.reasoning_effort is not UNSET_REASONING_EFFORT:
            result["reasoning_effort"] = (
                None if self.reasoning_effort is None else self.reasoning_effort.value
            )
        return result

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        # Rust overrides this field name to snake_case despite the struct's camelCase default.
        return self.to_mapping()


@dataclass(frozen=True)
class CollaborationModeListResponse:
    data: tuple[CollaborationModeMask, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "data", _mask_tuple(self.data, "data"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "CollaborationModeListResponse":
        _ensure_mapping(value, "CollaborationModeListResponse")
        return cls(
            data=tuple(
                CollaborationModeMask.from_mapping(item)
                for item in _iterable(value["data"], "data")
            )
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_mapping() for item in self.data]}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {"data": [item.to_camel_mapping() for item in self.data]}


def _ensure_mapping(value: JsonValue, type_name: str) -> None:
    if not isinstance(value, Mapping):
        raise TypeError(f"{type_name} mapping must be a mapping")


def _pick(value: Mapping[str, JsonValue], name: str, default: JsonValue = None) -> JsonValue:
    return value[name] if name in value else default


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


def _optional_str(value: JsonValue, field_name: str) -> str | None:
    if value is None:
        return None
    return _ensure_str(value, field_name)


def _optional_mode_kind(value: JsonValue, field_name: str) -> ModeKind | None:
    if value is None:
        return None
    if isinstance(value, ModeKind):
        return value
    if isinstance(value, str):
        return ModeKind.parse(value)
    raise TypeError(f"{field_name} must be a ModeKind, string, or None")


def _optional_reasoning_effort(value: JsonValue, field_name: str) -> ReasoningEffort | None:
    if value is None:
        return None
    if isinstance(value, ReasoningEffort):
        return value
    if isinstance(value, str):
        return ReasoningEffort.parse(value)
    raise TypeError(f"{field_name} must be a ReasoningEffort, string, or None")


def _optional_reasoning_effort_or_unset(
    value: JsonValue,
    field_name: str,
) -> ReasoningEffort | None | object:
    if value is UNSET_REASONING_EFFORT or value is CORE_UNSET:
        return UNSET_REASONING_EFFORT
    return _optional_reasoning_effort(value, field_name)


def _iterable(value: JsonValue, field_name: str) -> Iterable[JsonValue]:
    if isinstance(value, (str, bytes)) or not isinstance(value, Iterable):
        raise TypeError(f"{field_name} must be an iterable")
    return value


def _mask_tuple(value: JsonValue, field_name: str) -> tuple[CollaborationModeMask, ...]:
    result: list[CollaborationModeMask] = []
    for item in _iterable(value, field_name):
        if isinstance(item, CollaborationModeMask):
            result.append(item)
        elif isinstance(item, CoreCollaborationModeMask):
            result.append(CollaborationModeMask.from_core_mask(item))
        elif isinstance(item, Mapping):
            result.append(CollaborationModeMask.from_mapping(item))
        else:
            raise TypeError(f"{field_name} item must be a CollaborationModeMask or mapping")
    return tuple(result)


__all__ = [
    "CollaborationModeListParams",
    "CollaborationModeListResponse",
    "CollaborationModeMask",
    "UNSET_REASONING_EFFORT",
]
