"""Environment protocol types ported from ``protocol/v2/environment.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class EnvironmentAddParams:
    environment_id: str
    exec_server_url: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "environment_id", _ensure_str(self.environment_id, "environment_id"))
        object.__setattr__(self, "exec_server_url", _ensure_str(self.exec_server_url, "exec_server_url"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "EnvironmentAddParams":
        if not isinstance(value, Mapping):
            raise TypeError("EnvironmentAddParams mapping must be a mapping")
        return cls(
            environment_id=_ensure_str(
                _pick(value, "environment_id", "environmentId"),
                "environment_id",
            ),
            exec_server_url=_ensure_str(
                _pick(value, "exec_server_url", "execServerUrl"),
                "exec_server_url",
            ),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        return {
            "environment_id": self.environment_id,
            "exec_server_url": self.exec_server_url,
        }

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {
            "environmentId": self.environment_id,
            "execServerUrl": self.exec_server_url,
        }


@dataclass(frozen=True)
class EnvironmentAddResponse:
    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "EnvironmentAddResponse":
        if value is not None and not isinstance(value, Mapping):
            raise TypeError("EnvironmentAddResponse mapping must be a mapping")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


def _pick(value: Mapping[str, JsonValue], *names: str) -> JsonValue:
    for name in names:
        if name in value:
            return value[name]
    raise KeyError(names[0])


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


__all__ = [
    "EnvironmentAddParams",
    "EnvironmentAddResponse",
]
