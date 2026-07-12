"""Behavior port for Rust ``codex-tui::exec_cell::model``."""

from __future__ import annotations

from dataclasses import dataclass, field
from time import monotonic
from typing import Any, Iterable, Iterator

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="exec_cell::model", source="codex/codex-rs/tui/src/exec_cell/model.rs")

USER_SHELL = "UserShell"
UNIFIED_EXEC_INTERACTION = "UnifiedExecInteraction"
EXPLORING_PARSED_KINDS = {"Read", "ListFiles", "Search", "read", "list_files", "listfiles", "search"}


@dataclass
class CommandOutput:
    exit_code: int = 0
    aggregated_output: str = ""
    formatted_output: str = ""


@dataclass
class ExecCall:
    call_id: str
    command: list[str]
    parsed: list[Any]
    output: CommandOutput | None = None
    source: Any = None
    start_time: float | None = None
    duration: float | None = None
    interaction_input: str | None = None

    def is_user_shell_command(self) -> bool:
        return _source_name(self.source) == USER_SHELL

    def is_unified_exec_interaction(self) -> bool:
        return _source_name(self.source) == UNIFIED_EXEC_INTERACTION


@dataclass
class ExecCell:
    calls: list[ExecCall] = field(default_factory=list)
    _animations_enabled: bool = False

    @classmethod
    def new(cls, call: ExecCall, animations_enabled: bool) -> "ExecCell":
        return cls([call], bool(animations_enabled))

    def with_added_call(
        self,
        call_id: str,
        command: Iterable[str],
        parsed: Iterable[Any],
        source: Any,
        interaction_input: str | None = None,
    ) -> "ExecCell" | None:
        call = ExecCall(
            call_id=str(call_id),
            command=[str(part) for part in command],
            parsed=list(parsed),
            output=None,
            source=source,
            start_time=monotonic(),
            duration=None,
            interaction_input=interaction_input,
        )
        if self.is_exploring_cell() and self.is_exploring_call(call):
            return ExecCell([*self.calls, call], self._animations_enabled)
        return None

    def complete_call(self, call_id: str, output: CommandOutput, duration: float) -> bool:
        for call in reversed(self.calls):
            if call.call_id == call_id:
                call.output = output
                call.duration = duration
                call.start_time = None
                return True
        return False

    def should_flush(self) -> bool:
        return not self.is_exploring_cell() and all(call.output is not None for call in self.calls)

    def mark_failed(self) -> None:
        now = monotonic()
        for call in self.calls:
            if call.output is None:
                elapsed = 0.0 if call.start_time is None else max(0.0, now - call.start_time)
                call.start_time = None
                call.duration = elapsed
                call.output = CommandOutput(exit_code=1, formatted_output="", aggregated_output="")

    def is_exploring_cell(self) -> bool:
        return all(self.is_exploring_call(call) for call in self.calls)

    def is_active(self) -> bool:
        return any(call.output is None for call in self.calls)

    def active_start_time(self) -> float | None:
        for call in self.calls:
            if call.output is None:
                return call.start_time
        return None

    def animations_enabled(self) -> bool:
        return self._animations_enabled

    def iter_calls(self) -> Iterator[ExecCall]:
        return iter(self.calls)

    def contains_call(self, call_id: str) -> bool:
        return any(call.call_id == str(call_id) for call in self.calls)

    def append_output(self, call_id: str, chunk: str) -> bool:
        if chunk == "":
            return False
        for call in reversed(self.calls):
            if call.call_id == call_id:
                if call.output is None:
                    call.output = CommandOutput()
                call.output.aggregated_output += chunk
                return True
        return False

    def display_lines(self, width: int):
        from .render import display_lines

        return list(display_lines(self, int(width)))

    def transcript_lines(self, width: int):
        from .render import transcript_lines

        return list(transcript_lines(self, int(width)))

    def raw_lines(self):
        from .render import raw_lines

        return list(raw_lines(self))

    @staticmethod
    def is_exploring_call(call: ExecCall) -> bool:
        return (
            _source_name(call.source) != USER_SHELL
            and bool(call.parsed)
            and all(_parsed_kind(parsed) in EXPLORING_PARSED_KINDS for parsed in call.parsed)
        )


def _source_name(source: Any) -> str:
    if source is None:
        return ""
    if isinstance(source, str):
        return _canonical_source_name(source)
    value = getattr(source, "value", None)
    if value is not None:
        return _canonical_source_name(str(value))
    name = getattr(source, "name", None)
    if name is not None:
        return _canonical_source_name(str(name))
    return _canonical_source_name(str(source))


def _canonical_source_name(source: str) -> str:
    normalized = str(source).replace("-", "_").lower()
    return {
        "user_shell": USER_SHELL,
        "usershell": USER_SHELL,
        "unified_exec_interaction": UNIFIED_EXEC_INTERACTION,
        "unifiedexecinteraction": UNIFIED_EXEC_INTERACTION,
    }.get(normalized, str(source))


def _parsed_kind(parsed: Any) -> str:
    if isinstance(parsed, str):
        return parsed
    if isinstance(parsed, dict):
        for key in ("kind", "type", "variant"):
            if key in parsed:
                return str(parsed[key])
        if len(parsed) == 1:
            return str(next(iter(parsed)))
    value = getattr(parsed, "kind", getattr(parsed, "type", getattr(parsed, "variant", None)))
    if value is not None:
        return str(value)
    name = getattr(parsed, "name", None)
    if name is not None:
        return str(name)
    return type(parsed).__name__


__all__ = [
    "CommandOutput",
    "EXPLORING_PARSED_KINDS",
    "ExecCall",
    "ExecCell",
    "RUST_MODULE",
    "UNIFIED_EXEC_INTERACTION",
    "USER_SHELL",
]
