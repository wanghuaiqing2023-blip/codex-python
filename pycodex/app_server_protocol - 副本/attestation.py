"""Attestation protocol types ported from ``protocol/v2/attestation.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

JsonValue = Any


@dataclass(frozen=True)
class AttestationGenerateParams:
    """Empty params object for client attestation generation."""

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue] | None = None) -> "AttestationGenerateParams":
        if value is not None and not isinstance(value, Mapping):
            raise TypeError("AttestationGenerateParams mapping must be a mapping")
        return cls()

    def to_mapping(self) -> dict[str, JsonValue]:
        return {}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return {}


@dataclass(frozen=True)
class AttestationGenerateResponse:
    token: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "token", _ensure_str(self.token, "token"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "AttestationGenerateResponse":
        if not isinstance(value, Mapping):
            raise TypeError("AttestationGenerateResponse mapping must be a mapping")
        return cls(token=_ensure_str(value["token"], "token"))

    def to_mapping(self) -> dict[str, JsonValue]:
        return {"token": self.token}

    def to_camel_mapping(self) -> dict[str, JsonValue]:
        return self.to_mapping()


def _ensure_str(value: JsonValue, field_name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be a string")
    return value


__all__ = [
    "AttestationGenerateParams",
    "AttestationGenerateResponse",
]
