"""Python interface for Rust ``codex-shell-escalation``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from time import monotonic
from typing import Any


ESCALATE_SOCKET_ENV_VAR = "CODEX_ESCALATE_SOCKET"


class EscalationExecution(str, Enum):
    UNSANDBOXED = "unsandboxed"
    TURN_DEFAULT = "turn_default"
    PERMISSIONS = "permissions"


@dataclass(frozen=True)
class EscalationDecision:
    kind: str
    execution: EscalationExecution | Any | None = None
    reason: str | None = None

    @classmethod
    def run(cls) -> "EscalationDecision":
        return cls("run")

    @classmethod
    def escalate(cls, execution: EscalationExecution | Any) -> "EscalationDecision":
        return cls("escalate", execution=execution)

    @classmethod
    def deny(cls, reason: str | None = None) -> "EscalationDecision":
        return cls("deny", reason=reason)


class EscalateAction(str, Enum):
    RUN = "run"
    ESCALATE = "escalate"
    DENY = "deny"


@dataclass(frozen=True)
class EscalationPermissions:
    value: Any


@dataclass(frozen=True)
class ResolvedPermissionProfile:
    value: Any


@dataclass(frozen=True)
class ExecParams:
    file: Path
    argv: list[str]
    workdir: Path
    env: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExecResult:
    exit_code: int


@dataclass(frozen=True)
class PreparedExec:
    params: ExecParams


class Stopwatch:
    def __init__(self) -> None:
        self.started_at = monotonic()

    def elapsed(self) -> float:
        return monotonic() - self.started_at


class EscalationPolicy:
    async def determine_action(self, file: Path, argv: list[str], workdir: Path) -> EscalationDecision:
        return EscalationDecision.run()


class ShellCommandExecutor:
    async def exec(self, params: ExecParams) -> ExecResult:
        raise NotImplementedError("codex-shell-escalation command execution is not ported")


class EscalationSession:
    pass


class EscalateServer:
    pass


def main_execve_wrapper(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-shell-escalation execve wrapper is not ported")


def run_shell_escalation_execve_wrapper(*args: Any, **kwargs: Any) -> None:
    raise NotImplementedError("codex-shell-escalation execve wrapper is not ported")
