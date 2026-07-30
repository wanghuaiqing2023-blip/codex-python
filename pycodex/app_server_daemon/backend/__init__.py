from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from .pid import PidBackend
from .pid import read_stderr_log_tail


class BackendKind(str, Enum):
    PID = "pid"


@dataclass(frozen=True)
class BackendPaths:
    codex_bin: Path
    pid_file: Path
    update_pid_file: Path
    remote_control_enabled: bool


def pid_backend(paths: BackendPaths) -> PidBackend:
    return PidBackend.new(
        paths.codex_bin,
        paths.pid_file,
        paths.remote_control_enabled,
    )


def pid_update_loop_backend(paths: BackendPaths) -> PidBackend:
    return PidBackend.new_update_loop(paths.codex_bin, paths.update_pid_file)


async def append_stderr_log_tail_context(pid_file: Path, context: str) -> str:
    try:
        tail = await read_stderr_log_tail(pid_file)
    except Exception as exc:
        return context + f"\n\nFailed to read managed app-server stderr log: {exc}"
    if tail is None:
        return context
    return tail.append_to_context(context)


__all__ = [
    "BackendKind",
    "BackendPaths",
    "PidBackend",
    "append_stderr_log_tail_context",
    "pid_backend",
    "pid_update_loop_backend",
]
