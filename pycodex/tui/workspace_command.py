"""Workspace command runner boundary for Rust ``codex-tui::workspace_command``."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Protocol, TypeAlias

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="workspace_command", source="codex/codex-rs/tui/src/workspace_command.rs")


class WorkspaceCommandExecutor(Protocol):
    async def run(self, command: "WorkspaceCommand") -> "WorkspaceCommandOutput":
        ...


WorkspaceCommandRunner: TypeAlias = WorkspaceCommandExecutor


@dataclass(frozen=True)
class WorkspaceCommand:
    """Describes a bounded non-interactive workspace command."""

    argv: list[str]
    cwd_path: Path | None = None
    env_overrides: dict[str, str | None] = field(default_factory=dict)
    timeout_seconds: float = 5.0
    output_bytes_cap: int = 64 * 1024
    disable_output_cap_flag: bool = False

    @classmethod
    def new(cls, argv: Any) -> "WorkspaceCommand":
        return cls(argv=[str(item) for item in argv])

    def cwd(self, cwd: str | Path) -> "WorkspaceCommand":
        return replace(self, cwd_path=Path(cwd))

    def env(self, key: str, value: str) -> "WorkspaceCommand":
        env_overrides = dict(self.env_overrides)
        env_overrides[str(key)] = str(value)
        return replace(self, env_overrides=env_overrides)

    def remove_env(self, key: str) -> "WorkspaceCommand":
        env_overrides = dict(self.env_overrides)
        env_overrides[str(key)] = None
        return replace(self, env_overrides=env_overrides)

    def timeout(self, timeout: float) -> "WorkspaceCommand":
        return replace(self, timeout_seconds=float(timeout))

    def disable_output_cap(self) -> "WorkspaceCommand":
        return replace(self, disable_output_cap_flag=True)


@dataclass(frozen=True)
class WorkspaceCommandOutput:
    exit_code: int
    stdout: str
    stderr: str

    def success(self) -> bool:
        return self.exit_code == 0


@dataclass(frozen=True)
class WorkspaceCommandError(Exception):
    message: str

    @classmethod
    def new(cls, message: Any) -> "WorkspaceCommandError":
        return cls(str(message))

    def __str__(self) -> str:
        return self.message


def fmt(error: WorkspaceCommandError) -> str:
    return str(error)


def run(runner: WorkspaceCommandExecutor, command: WorkspaceCommand) -> Any:
    return runner.run(command)


@dataclass
class AppServerWorkspaceCommandRunner:
    """Runner that forwards requests to an app-server request handle."""

    request_handle: Any

    @classmethod
    def new(cls, request_handle: Any) -> "AppServerWorkspaceCommandRunner":
        return cls(request_handle=request_handle)

    async def run(self, command: WorkspaceCommand) -> WorkspaceCommandOutput:
        request = self._build_request(command)
        try:
            response = self.request_handle.request_typed(request)
            if asyncio.iscoroutine(response):
                response = await response
        except Exception as exc:
            raise WorkspaceCommandError.new(exc) from None

        try:
            exit_code = response["exit_code"] if isinstance(response, dict) else response.exit_code
            stdout = response["stdout"] if isinstance(response, dict) else response.stdout
            stderr = response["stderr"] if isinstance(response, dict) else response.stderr
        except Exception as exc:
            raise WorkspaceCommandError.new(exc) from None

        return WorkspaceCommandOutput(exit_code=int(exit_code), stdout=str(stdout), stderr=str(stderr))

    @staticmethod
    def _build_request(command: WorkspaceCommand) -> dict[str, Any]:
        timeout_ms = int(command.timeout_seconds * 1000)
        if timeout_ms > 9_223_372_036_854_775_807:
            timeout_ms = 9_223_372_036_854_775_807
        return {
            "type": "OneOffCommandExec",
            "request_id": f"workspace-command-{uuid.uuid4()}",
            "params": {
                "command": list(command.argv),
                "process_id": None,
                "tty": False,
                "stream_stdin": False,
                "stream_stdout_stderr": False,
                "output_bytes_cap": None if command.disable_output_cap_flag else command.output_bytes_cap,
                "disable_output_cap": command.disable_output_cap_flag,
                "disable_timeout": False,
                "timeout_ms": timeout_ms,
                "cwd": command.cwd_path,
                "env": dict(command.env_overrides) if command.env_overrides else None,
                "size": None,
                "sandbox_policy": None,
                "permission_profile": None,
            },
        }


__all__ = [
    "AppServerWorkspaceCommandRunner",
    "RUST_MODULE",
    "WorkspaceCommand",
    "WorkspaceCommandError",
    "WorkspaceCommandExecutor",
    "WorkspaceCommandOutput",
    "WorkspaceCommandRunner",
    "fmt",
    "run",
]
