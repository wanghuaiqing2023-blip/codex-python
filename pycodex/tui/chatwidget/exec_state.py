"""Semantic port of codex-rs/tui/src/chatwidget/exec_state.rs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from pycodex.protocol import CommandExecutionSource
from pycodex.protocol.parse_command import ParsedCommand

from .._porting import RustTuiModule
from ..exec_command import split_command_string


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::exec_state",
    source="codex/codex-rs/tui/src/chatwidget/exec_state.rs",
)


@dataclass
class RunningCommand:
    command: list[str]
    parsed_cmd: list[ParsedCommand]
    source: str


@dataclass
class UnifiedExecProcessSummary:
    key: str
    call_id: str
    command_display: str
    recent_chunks: list[str] = field(default_factory=list)


@dataclass
class UnifiedExecWaitState:
    command_display: str

    @classmethod
    def new(cls, command_display: str) -> "UnifiedExecWaitState":
        return cls(command_display=str(command_display))

    def is_duplicate(self, command_display: str) -> bool:
        return self.command_display == command_display


@dataclass
class UnifiedExecWaitStreak:
    process_id: str
    command_display: str | None = None

    @classmethod
    def new(
        cls,
        process_id: str,
        command_display: str | None,
    ) -> "UnifiedExecWaitStreak":
        return cls(str(process_id), _non_empty(command_display))

    def update_command_display(self, command_display: str | None) -> None:
        if self.command_display is not None:
            return
        self.command_display = _non_empty(command_display)


def is_unified_exec_source(source: Any) -> bool:
    normalized = _normalize_source(source)
    return normalized in {
        CommandExecutionSource.UNIFIED_EXEC_STARTUP,
        CommandExecutionSource.UNIFIED_EXEC_INTERACTION,
        "unifiedExecStartup",
        "unifiedExecInteraction",
        "unified_exec_startup",
        "unified_exec_interaction",
    }


def is_standard_tool_call(parsed_cmd: Iterable[Any]) -> bool:
    parsed = [_coerce_parsed_command(item) for item in parsed_cmd]
    return bool(parsed) and all(item.type != "unknown" for item in parsed)


def command_execution_command_and_parsed(
    command: str,
    command_actions: Iterable[Any],
) -> tuple[list[str], list[ParsedCommand]]:
    return (
        split_command_string(command),
        [_command_action_into_core(action) for action in command_actions],
    )


def _non_empty(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _normalize_source(source: Any) -> str:
    if isinstance(source, str):
        return source
    value = getattr(source, "value", None)
    if value is not None:
        return str(value)
    return str(source)


def _coerce_parsed_command(value: Any) -> ParsedCommand:
    if isinstance(value, ParsedCommand):
        return value
    if isinstance(value, dict):
        if value.get("type") == "exec":
            return ParsedCommand.unknown(cmd=str(value.get("cmd", "exec")))
        return ParsedCommand.from_mapping(value)
    into_core = getattr(value, "into_core", None)
    if callable(into_core):
        return _coerce_parsed_command(into_core())
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        return ParsedCommand.from_mapping(to_mapping())
    raise TypeError("parsed command must be ParsedCommand, mapping, or expose into_core/to_mapping")


def _command_action_into_core(action: Any) -> ParsedCommand:
    if isinstance(action, dict) and "command" in action and "cmd" not in action:
        action = dict(action)
        action["cmd"] = action.pop("command")
        if action.get("type") == "listFiles":
            action["type"] = "list_files"
    return _coerce_parsed_command(action)


__all__ = [
    "RUST_MODULE",
    "RunningCommand",
    "UnifiedExecProcessSummary",
    "UnifiedExecWaitState",
    "UnifiedExecWaitStreak",
    "command_execution_command_and_parsed",
    "is_standard_tool_call",
    "is_unified_exec_source",
]
