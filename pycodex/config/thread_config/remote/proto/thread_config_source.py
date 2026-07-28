"""Oneof payload variants for ``ThreadConfigSource``."""

from __future__ import annotations

from dataclasses import dataclass

from . import SessionThreadConfig, UserThreadConfig


@dataclass(frozen=True)
class Source:
    kind: str
    value: SessionThreadConfig | UserThreadConfig

    @classmethod
    def session(cls, value: SessionThreadConfig) -> "Source":
        return cls("session", value)

    @classmethod
    def user(cls, value: UserThreadConfig) -> "Source":
        return cls("user", value)


__all__ = ["Source"]
