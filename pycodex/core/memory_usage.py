"""Telemetry helpers for memory-file reads.

Ported from ``codex/codex-rs/core/src/memory_usage.rs`` plus the small
``codex_memories_read::usage`` classifier that file depends on.
"""

from __future__ import annotations

import json
import shlex
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol

from pycodex.core.shell import Shell, default_user_shell
from pycodex.core.shell_handler import ShellCommandToolCallParams
from pycodex.core.tool_registry import ToolInvocation, flat_tool_name
from pycodex.core.unified_exec_handler import ExecCommandArgs, UnifiedExecShellMode, get_command

JsonValue = Any
MEMORIES_USAGE_METRIC = "codex.memories.usage"


class MemoriesUsageKind(str, Enum):
    MEMORY_MD = "memory_md"
    MEMORY_SUMMARY = "memory_summary"
    RAW_MEMORIES = "raw_memories"
    ROLLOUT_SUMMARIES = "rollout_summaries"
    SKILLS = "skills"

    def as_tag(self) -> str:
        return self.value


@dataclass(frozen=True)
class ShellCommandForInvocation:
    command: tuple[str, ...]
    cwd: Path

    def __post_init__(self) -> None:
        if isinstance(self.command, str) or not isinstance(self.command, tuple):
            object.__setattr__(self, "command", tuple(self.command))
        if not all(isinstance(token, str) for token in self.command):
            raise TypeError("command must contain strings")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))


class CounterTelemetry(Protocol):
    def counter(self, metric: str, inc: int, tags: Sequence[tuple[str, str]]) -> object:
        ...


def emit_metric_for_tool_read(
    invocation: ToolInvocation,
    success: bool,
    telemetry: CounterTelemetry,
    *,
    session_shell: Shell | None = None,
    allow_login_shell: bool = False,
    unified_exec_shell_mode: UnifiedExecShellMode | None = None,
    resolve_path: Callable[[str | None], Path] | None = None,
) -> tuple[MemoriesUsageKind, ...]:
    if not isinstance(success, bool):
        raise TypeError("success must be a bool")
    command = shell_command_for_invocation(
        invocation,
        session_shell=session_shell,
        allow_login_shell=allow_login_shell,
        unified_exec_shell_mode=unified_exec_shell_mode,
        resolve_path=resolve_path,
    )
    if command is None:
        return ()

    kinds = memory_usage_kinds_from_command(command.command)
    if not kinds:
        return ()
    tool_name = flat_tool_name(invocation.tool_name)
    success_tag = "true" if success else "false"
    for kind in kinds:
        telemetry.counter(
            MEMORIES_USAGE_METRIC,
            1,
            (
                ("kind", kind.as_tag()),
                ("tool", tool_name),
                ("success", success_tag),
            ),
        )
    return kinds


def shell_command_for_invocation(
    invocation: ToolInvocation,
    *,
    session_shell: Shell | None = None,
    allow_login_shell: bool = False,
    unified_exec_shell_mode: UnifiedExecShellMode | None = None,
    resolve_path: Callable[[str | None], Path] | None = None,
) -> ShellCommandForInvocation | None:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if not isinstance(allow_login_shell, bool):
        raise TypeError("allow_login_shell must be a bool")
    if invocation.payload.type != "function":
        return None
    arguments = invocation.payload.arguments or ""
    if session_shell is None:
        session_shell = default_user_shell()
    if not isinstance(session_shell, Shell):
        raise TypeError("session_shell must be Shell")
    if unified_exec_shell_mode is None:
        unified_exec_shell_mode = UnifiedExecShellMode.direct()
    if not isinstance(unified_exec_shell_mode, UnifiedExecShellMode):
        raise TypeError("unified_exec_shell_mode must be UnifiedExecShellMode")
    path_resolver = resolve_path or _default_resolve_path

    namespace = invocation.tool_name.namespace
    name = invocation.tool_name.name
    if namespace is None and name == "shell_command":
        params = _parse_shell_command(arguments)
        if params is None:
            return None
        cwd = path_resolver(params.workdir)
        if not allow_login_shell and params.login is True:
            return ShellCommandForInvocation((), cwd)
        use_login_shell = params.login if params.login is not None else allow_login_shell
        return ShellCommandForInvocation(tuple(session_shell.derive_exec_args(params.command, use_login_shell)), cwd)

    if namespace is None and name == "exec_command":
        params = _parse_exec_command(arguments)
        if params is None:
            return None
        try:
            command = get_command(
                params,
                session_shell,
                unified_exec_shell_mode,
                allow_login_shell,
            )
        except (TypeError, ValueError):
            return None
        return ShellCommandForInvocation(tuple(command.command), path_resolver(params.workdir))

    return None


def memory_usage_kinds_from_command(command: Sequence[str]) -> tuple[MemoriesUsageKind, ...]:
    if isinstance(command, str) or not isinstance(command, Sequence):
        raise TypeError("command must be a sequence of strings")
    argv = tuple(command)
    if not all(isinstance(token, str) for token in argv):
        raise TypeError("command must be a sequence of strings")
    if not argv:
        return ()
    parsed = _command_tokens_for_safe_read(argv)
    if parsed is None:
        return ()
    return tuple(kind for token in parsed for kind in _memory_kind_for_path(token))


def memory_kind_for_path(path: str) -> MemoriesUsageKind | None:
    if not isinstance(path, str):
        raise TypeError("path must be a string")
    kinds = _memory_kind_for_path(path)
    return kinds[0] if kinds else None


def _parse_shell_command(arguments: str) -> ShellCommandToolCallParams | None:
    try:
        return ShellCommandToolCallParams.from_json(arguments)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _parse_exec_command(arguments: str) -> ExecCommandArgs | None:
    try:
        return ExecCommandArgs.from_json(arguments)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None


def _default_resolve_path(workdir: str | None) -> Path:
    return Path.cwd() if workdir is None else Path(workdir)


def _command_tokens_for_safe_read(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    script_tokens = _tokens_from_shell_wrapper(argv)
    if script_tokens is not None:
        argv = script_tokens
    if not argv:
        return ()
    command_name = Path(argv[0]).name.lower()
    if command_name in {"cat", "head", "tail", "less", "more", "bat", "batcat", "type", "get-content"}:
        return _non_option_tokens(argv[1:])
    if command_name in {"grep", "rg", "ag", "ack", "findstr", "select-string"}:
        return _non_option_tokens(argv[1:])
    return None


def _tokens_from_shell_wrapper(argv: tuple[str, ...]) -> tuple[str, ...] | None:
    if len(argv) < 3:
        return None
    shell_name = Path(argv[0]).name.lower()
    if shell_name not in {"sh", "bash", "zsh", "dash", "pwsh", "powershell", "cmd", "cmd.exe"}:
        return None
    for index, token in enumerate(argv[1:], start=1):
        lowered = token.lower()
        if lowered in {"-c", "/c"} or lowered.endswith("c") and lowered.startswith("-"):
            if index + 1 >= len(argv):
                return ()
            try:
                return tuple(shlex.split(argv[index + 1], posix=shell_name not in {"cmd", "cmd.exe"}))
            except ValueError:
                return ()
    return None


def _non_option_tokens(tokens: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    skip_next = False
    for token in tokens:
        if skip_next:
            skip_next = False
            continue
        if token == "--":
            result.extend(tokens[tokens.index(token) + 1 :])
            break
        if token.startswith("-"):
            if token in {"-e", "-f", "--regexp", "--file", "--glob", "-g"}:
                skip_next = True
            continue
        result.append(token)
    return tuple(result)


def _memory_kind_for_path(path: str) -> tuple[MemoriesUsageKind, ...]:
    if "memories/MEMORY.md" in path:
        return (MemoriesUsageKind.MEMORY_MD,)
    if "memories/memory_summary.md" in path:
        return (MemoriesUsageKind.MEMORY_SUMMARY,)
    if "memories/raw_memories.md" in path:
        return (MemoriesUsageKind.RAW_MEMORIES,)
    if "memories/rollout_summaries/" in path:
        return (MemoriesUsageKind.ROLLOUT_SUMMARIES,)
    if "memories/skills/" in path:
        return (MemoriesUsageKind.SKILLS,)
    return ()


__all__ = [
    "MEMORIES_USAGE_METRIC",
    "CounterTelemetry",
    "MemoriesUsageKind",
    "ShellCommandForInvocation",
    "emit_metric_for_tool_read",
    "memory_kind_for_path",
    "memory_usage_kinds_from_command",
    "shell_command_for_invocation",
]
