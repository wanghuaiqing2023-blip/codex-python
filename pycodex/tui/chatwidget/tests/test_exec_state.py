"""Parity tests for codex-rs/tui/src/chatwidget/exec_state.rs."""

from pycodex.protocol import CommandExecutionSource
from pycodex.protocol.parse_command import ParsedCommand
from pycodex.tui.chatwidget.exec_state import (
    RunningCommand,
    UnifiedExecProcessSummary,
    UnifiedExecWaitState,
    UnifiedExecWaitStreak,
    command_execution_command_and_parsed,
    is_standard_tool_call,
    is_unified_exec_source,
)


class FakeCommandAction:
    def __init__(self, parsed):
        self.parsed = parsed

    def into_core(self):
        return self.parsed


def test_wait_state_detects_duplicate_command_display_exactly():
    state = UnifiedExecWaitState.new("cargo test")

    assert state.is_duplicate("cargo test") is True
    assert state.is_duplicate("cargo check") is False


def test_wait_streak_filters_empty_initial_command_display():
    streak = UnifiedExecWaitStreak.new("process-1", "")

    assert streak.process_id == "process-1"
    assert streak.command_display is None

    streak.update_command_display("npm test")
    assert streak.command_display == "npm test"


def test_wait_streak_does_not_replace_existing_command_display():
    streak = UnifiedExecWaitStreak.new("process-1", "cargo test")

    streak.update_command_display("npm test")

    assert streak.command_display == "cargo test"


def test_is_unified_exec_source_matches_only_unified_sources():
    assert is_unified_exec_source(CommandExecutionSource.UNIFIED_EXEC_STARTUP) is True
    assert is_unified_exec_source(CommandExecutionSource.UNIFIED_EXEC_INTERACTION) is True
    assert is_unified_exec_source(CommandExecutionSource.AGENT) is False
    assert is_unified_exec_source("userShell") is False


def test_is_standard_tool_call_requires_non_empty_and_no_unknown_commands():
    assert is_standard_tool_call([]) is False
    assert is_standard_tool_call([ParsedCommand.read("cat a.txt", "a.txt", "a.txt")]) is True
    assert is_standard_tool_call([ParsedCommand.unknown("mystery")]) is False
    assert is_standard_tool_call(
        [
            {"type": "list_files", "cmd": "ls"},
            {"type": "search", "cmd": "rg needle", "query": "needle"},
        ]
    ) is True


def test_command_execution_command_and_parsed_splits_command_and_converts_actions():
    command, parsed = command_execution_command_and_parsed(
        "rg needle src",
        [
            FakeCommandAction(ParsedCommand.search("rg needle src", query="needle", path="src")),
            {"type": "list_files", "cmd": "ls src", "path": "src"},
        ],
    )

    assert command == ["rg", "needle", "src"]
    assert parsed == [
        ParsedCommand.search("rg needle src", query="needle", path="src"),
        ParsedCommand.list_files("ls src", path="src"),
    ]


def test_command_action_protocol_mappings_convert_into_core_parsed_commands_matches_rust():
    # Rust owner: app-server-protocol::CommandAction::into_core, consumed by
    # codex-tui::chatwidget::exec_state.
    _command, parsed = command_execution_command_and_parsed(
        "wrapped command",
        [
            {"type": "read", "command": "cat a.txt", "name": "a.txt", "path": "C:/repo/a.txt"},
            {"type": "listFiles", "command": "ls src", "path": "src"},
            {"type": "search", "command": "rg needle", "query": "needle", "path": "src"},
            {"type": "unknown", "command": "custom"},
        ],
    )

    assert parsed == [
        ParsedCommand.read("cat a.txt", "a.txt", "C:/repo/a.txt"),
        ParsedCommand.list_files("ls src", "src"),
        ParsedCommand.search("rg needle", "needle", "src"),
        ParsedCommand.unknown("custom"),
    ]


def test_running_command_and_process_summary_are_plain_bookkeeping_state():
    parsed = [ParsedCommand.list_files("ls")]
    running = RunningCommand(command=["ls"], parsed_cmd=parsed, source=CommandExecutionSource.AGENT)
    summary = UnifiedExecProcessSummary(
        key="process-key",
        call_id="call-1",
        command_display="ls",
        recent_chunks=["one", "two"],
    )

    assert running.command == ["ls"]
    assert running.parsed_cmd is parsed
    assert running.source == CommandExecutionSource.AGENT
    assert summary.recent_chunks == ["one", "two"]
