"""Port of Rust ``codex-cloud-tasks/src/cli.rs`` value contracts."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def parse_attempts(input_value: str) -> int:
    try:
        value = int(input_value)
    except ValueError as exc:
        raise ValueError("attempts must be an integer between 1 and 4") from exc
    if 1 <= value <= 4:
        return value
    raise ValueError("attempts must be between 1 and 4")


def parse_limit(input_value: str) -> int:
    try:
        value = int(input_value)
    except ValueError as exc:
        raise ValueError("limit must be an integer between 1 and 20") from exc
    if 1 <= value <= 20:
        return value
    raise ValueError("limit must be between 1 and 20")


@dataclass(frozen=True)
class ExecCommand:
    query: str | None
    environment: str
    attempts: int = 1
    branch: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "attempts", parse_attempts(str(self.attempts)))


@dataclass(frozen=True)
class StatusCommand:
    task_id: str


@dataclass(frozen=True)
class ListCommand:
    environment: str | None = None
    limit: int = 20
    cursor: str | None = None
    json: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "limit", parse_limit(str(self.limit)))


@dataclass(frozen=True)
class ApplyCommand:
    task_id: str
    attempt: int | None = None

    def __post_init__(self) -> None:
        if self.attempt is not None:
            object.__setattr__(self, "attempt", parse_attempts(str(self.attempt)))


@dataclass(frozen=True)
class DiffCommand:
    task_id: str
    attempt: int | None = None

    def __post_init__(self) -> None:
        if self.attempt is not None:
            object.__setattr__(self, "attempt", parse_attempts(str(self.attempt)))


@dataclass(frozen=True)
class Command:
    kind: str
    value: Any

    @classmethod
    def exec(cls, value: ExecCommand) -> "Command":
        return cls("exec", value)

    @classmethod
    def status(cls, value: StatusCommand) -> "Command":
        return cls("status", value)

    @classmethod
    def list(cls, value: ListCommand) -> "Command":
        return cls("list", value)

    @classmethod
    def apply(cls, value: ApplyCommand) -> "Command":
        return cls("apply", value)

    @classmethod
    def diff(cls, value: DiffCommand) -> "Command":
        return cls("diff", value)


@dataclass(frozen=True)
class Cli:
    config_overrides: Any = field(default_factory=list)
    command: Command | None = None


__all__ = [
    "ApplyCommand",
    "Cli",
    "Command",
    "DiffCommand",
    "ExecCommand",
    "ListCommand",
    "StatusCommand",
    "parse_attempts",
    "parse_limit",
]
