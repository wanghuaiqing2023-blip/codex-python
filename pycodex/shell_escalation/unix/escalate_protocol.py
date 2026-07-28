"""Unix shell-escalation wire records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.protocol.approvals import EscalationPermissions

ESCALATE_SOCKET_ENV_VAR = "CODEX_ESCALATE_SOCKET"
EXEC_WRAPPER_ENV_VAR = "EXEC_WRAPPER"


class EscalationExecution(str, Enum):
    UNSANDBOXED = "unsandboxed"
    TURN_DEFAULT = "turn_default"
    PERMISSIONS = "permissions"


@dataclass(frozen=True)
class EscalationDecision:
    kind: str
    execution: EscalationExecution | EscalationPermissions | None = None
    reason: str | None = None

    @classmethod
    def run(cls) -> "EscalationDecision":
        return cls("run")

    @classmethod
    def escalate(
        cls,
        execution: EscalationExecution | EscalationPermissions,
    ) -> "EscalationDecision":
        return cls("escalate", execution=execution)

    @classmethod
    def deny(cls, reason: str | None = None) -> "EscalationDecision":
        return cls("deny", reason=reason)


@dataclass(frozen=True)
class EscalateAction:
    type: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {"run", "escalate", "deny"}:
            raise ValueError(f"unknown escalate action type: {self.type}")
        if self.type == "deny":
            if self.reason is not None and not isinstance(self.reason, str):
                raise TypeError("reason must be a string or None")
        elif self.reason is not None:
            raise ValueError(f"{self.type} action must not include reason")

    @classmethod
    def run(cls) -> "EscalateAction":
        return cls("run")

    @classmethod
    def escalate(cls) -> "EscalateAction":
        return cls("escalate")

    @classmethod
    def deny(cls, reason: str | None = None) -> "EscalateAction":
        return cls("deny", reason)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EscalateAction":
        if not isinstance(value, Mapping):
            raise TypeError("escalate action must be a mapping")
        action_type = value.get("type")
        if action_type == "run":
            return cls.run()
        if action_type == "escalate":
            return cls.escalate()
        if action_type == "deny":
            return cls.deny(value.get("reason"))
        raise ValueError(f"unknown escalate action type: {action_type!r}")

    def to_mapping(self) -> dict[str, str | None]:
        if self.type == "deny":
            return {"type": "deny", "reason": self.reason}
        return {"type": self.type}


@dataclass(frozen=True)
class EscalateRequest:
    file: Path
    argv: tuple[str, ...]
    workdir: Path
    env: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.file, Path):
            object.__setattr__(self, "file", Path(self.file))
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, "argv", tuple(self.argv))
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, "workdir", Path(self.workdir))
        if not isinstance(self.env, dict):
            object.__setattr__(self, "env", dict(self.env))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EscalateRequest":
        if not isinstance(value, Mapping):
            raise TypeError("escalate request must be a mapping")
        return cls(
            Path(value["file"]),
            tuple(value.get("argv", ())),
            Path(value["workdir"]),
            dict(value.get("env", {})),
        )

    def to_mapping(self) -> dict[str, Any]:
        return {
            "file": self.file.as_posix(),
            "argv": list(self.argv),
            "workdir": self.workdir.as_posix(),
            "env": dict(self.env),
        }


@dataclass(frozen=True)
class EscalateResponse:
    action: EscalateAction

    def __post_init__(self) -> None:
        if not isinstance(self.action, EscalateAction):
            object.__setattr__(
                self,
                "action",
                EscalateAction.from_mapping(self.action),  # type: ignore[arg-type]
            )

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "EscalateResponse":
        if not isinstance(value, Mapping):
            raise TypeError("escalate response must be a mapping")
        return cls(EscalateAction.from_mapping(value["action"]))

    def to_mapping(self) -> dict[str, Any]:
        return {"action": self.action.to_mapping()}


@dataclass(frozen=True)
class SuperExecMessage:
    fds: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.fds, tuple):
            object.__setattr__(self, "fds", tuple(self.fds))
        if any(isinstance(fd, bool) or not isinstance(fd, int) for fd in self.fds):
            raise TypeError("fds must contain integer file descriptors")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SuperExecMessage":
        return cls(tuple(value.get("fds", ())))

    def to_mapping(self) -> dict[str, Any]:
        return {"fds": list(self.fds)}


@dataclass(frozen=True)
class SuperExecResult:
    exit_code: int

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be an integer")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SuperExecResult":
        return cls(value["exit_code"])

    def to_mapping(self) -> dict[str, int]:
        return {"exit_code": self.exit_code}


__all__ = [
    "ESCALATE_SOCKET_ENV_VAR",
    "EXEC_WRAPPER_ENV_VAR",
    "EscalateAction",
    "EscalateRequest",
    "EscalateResponse",
    "EscalationDecision",
    "EscalationExecution",
    "SuperExecMessage",
    "SuperExecResult",
]
