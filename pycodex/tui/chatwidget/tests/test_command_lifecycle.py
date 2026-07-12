from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/command_lifecycle.rs
# Behavior contract: unified-exec process tracking, footer sync data, recent
# output chunk retention, process end removal, and terminal wait streak flushing.

from pycodex.tui.chatwidget.command_lifecycle import (
    CommandExecutionItem,
    CommandLifecycleState,
    SemanticExecCell,
    UnifiedExecInteractionCell,
    command_display_from_raw,
    command_text_from_notification,
)


def test_command_display_from_raw_strips_bash_lc_wrapper():
    assert command_display_from_raw("bash -lc 'echo hi'") == "echo hi"


def test_command_text_from_notification_extracts_command_execution_payloads():
    # Rust path: chatwidget::protocol routes ItemStarted/ItemCompleted into
    # chatwidget::command_lifecycle command execution handlers.
    event = type(
        "Event",
        (),
        {"payload": {"item": {"command": ["echo", "hello world"]}}},
    )()

    assert command_text_from_notification(event) == "echo hello world"


def test_command_text_from_notification_supports_object_payload_and_missing_command():
    # Rust path: chatwidget::protocol handles typed notification payloads.
    item = type("Item", (), {"command": "rg needle"})()
    event = type("Event", (), {"payload": type("Payload", (), {"item": item})()})()
    missing = type("Event", (), {"payload": {"item": {"kind": "FileChange"}}})()

    assert command_text_from_notification(event) == "rg needle"
    assert command_text_from_notification(missing) == ""


def test_track_unified_exec_process_begin_adds_and_updates_existing_process():
    state = CommandLifecycleState()

    state.track_unified_exec_process_begin("call-1", "proc-1", "bash -lc 'sleep 5'")
    assert [(p.key, p.call_id, p.command_display, p.recent_chunks) for p in state.unified_exec_processes] == [
        ("proc-1", "call-1", "sleep 5", [])
    ]
    assert state.footer_processes == ["sleep 5"]

    state.track_unified_exec_output_chunk("call-1", "old\n")
    state.track_unified_exec_process_begin("call-2", "proc-1", "bash -lc 'echo next'")
    assert [(p.key, p.call_id, p.command_display, p.recent_chunks) for p in state.unified_exec_processes] == [
        ("proc-1", "call-2", "echo next", [])
    ]
    assert state.footer_processes == ["echo next"]


def test_track_unified_exec_process_begin_uses_call_id_when_process_id_missing():
    state = CommandLifecycleState()

    state.track_unified_exec_process_begin("call-1", None, "echo hi")

    assert state.unified_exec_processes[0].key == "call-1"


def test_track_unified_exec_process_end_removes_by_key_and_syncs_footer_only_when_changed():
    state = CommandLifecycleState()
    state.track_unified_exec_process_begin("call-1", "proc-1", "echo one")
    state.track_unified_exec_process_begin("call-2", "proc-2", "echo two")

    assert state.track_unified_exec_process_end("call-1", "proc-1") is True
    assert [p.key for p in state.unified_exec_processes] == ["proc-2"]
    assert state.footer_processes == ["echo two"]

    assert state.track_unified_exec_process_end("missing", "missing") is False
    assert state.footer_processes == ["echo two"]


def test_track_unified_exec_output_chunk_records_last_three_non_empty_trimmed_lines():
    state = CommandLifecycleState()
    state.track_unified_exec_process_begin("call-1", "proc-1", "echo hi")

    assert state.track_unified_exec_output_chunk("missing", "ignored\n") is False
    assert state.track_unified_exec_output_chunk("call-1", b"one  \n\n two\nthree\nfour\n") is True

    assert state.unified_exec_processes[0].recent_chunks == ["two", "three", "four"]


def test_terminal_interaction_empty_stdin_creates_and_replaces_wait_streaks():
    state = CommandLifecycleState()
    state.track_unified_exec_process_begin("call-1", "proc-1", "echo one")
    state.track_unified_exec_process_begin("call-2", "proc-2", "echo two")

    assert state.on_terminal_interaction("missing", "") is None
    assert state.unified_exec_wait_streak is None

    assert state.on_terminal_interaction("proc-1", "") is None
    assert state.unified_exec_wait_streak.process_id == "proc-1"
    assert state.unified_exec_wait_streak.command_display == "echo one"

    assert state.on_terminal_interaction("proc-2", "") is None
    assert state.flushed_wait_cells == [UnifiedExecInteractionCell("echo one", "")]
    assert state.unified_exec_wait_streak.process_id == "proc-2"
    assert state.unified_exec_wait_streak.command_display == "echo two"


def test_terminal_interaction_with_stdin_flushes_matching_wait_and_returns_history_cell():
    state = CommandLifecycleState()
    state.track_unified_exec_process_begin("call-1", "proc-1", "python repl")
    state.on_terminal_interaction("proc-1", "")

    cell = state.on_terminal_interaction("proc-1", "print(1)")

    assert state.flushed_wait_cells == [UnifiedExecInteractionCell("python repl", "")]
    assert state.unified_exec_wait_streak is None
    assert cell == UnifiedExecInteractionCell("python repl", "print(1)")


def test_flush_unified_exec_wait_streak_is_noop_without_wait():
    state = CommandLifecycleState()

    assert state.flush_unified_exec_wait_streak() is None
    state.unified_exec_wait_streak = state.on_terminal_interaction("missing", "")
    assert state.flush_unified_exec_wait_streak() is None


def test_handle_command_execution_started_groups_active_exec_calls_and_suppresses_duplicate_waits():
    state = CommandLifecycleState()

    state.handle_command_execution_started_now(CommandExecutionItem("call-1", "echo one", "user_shell"))
    state.handle_command_execution_started_now(CommandExecutionItem("call-2", "echo two", "user_shell"))

    assert state.status_indicator_visible is True
    assert state.active_exec_cell is not None
    assert [call.call_id for call in state.active_exec_cell.calls] == ["call-2"]
    assert [call.call_id for call in state.history_cells[0].calls] == ["call-1"]
    assert set(state.running_commands) == {"call-1", "call-2"}

    state.handle_command_execution_started_now(CommandExecutionItem("wait-1", "bash -lc 'sleep 1'", "unified_exec_interaction"))
    state.handle_command_execution_started_now(CommandExecutionItem("wait-2", "bash -lc 'sleep 1'", "unified_exec_interaction"))

    assert "wait-2" in state.suppressed_exec_calls
    assert "wait-1" in state.running_commands


def test_output_delta_updates_recent_chunks_and_active_exec_cell_revision():
    state = CommandLifecycleState()
    state.track_unified_exec_process_begin("call-1", "proc-1", "echo one")
    state.handle_command_execution_started_now(CommandExecutionItem("call-1", "echo one", "user_shell"))

    assert state.on_exec_command_output_delta("call-1", "first\nsecond\n") is True

    assert state.unified_exec_processes[0].recent_chunks == ["first", "second"]
    assert state.active_exec_cell is not None
    assert state.active_exec_cell.calls[0].output is not None
    assert state.active_exec_cell.calls[0].output.aggregated_output == "first\nsecond\n"
    assert state.active_cell_revision == 2
    assert state.redraw_requested is True


def test_completion_flushes_tracked_active_cell_and_marks_user_shell_work():
    state = CommandLifecycleState()
    state.handle_command_execution_started_now(CommandExecutionItem("call-1", "echo one", "user_shell"))

    state.handle_command_execution_completed_now(
        CommandExecutionItem("call-1", "echo fallback", "user_shell", aggregated_output="done", exit_code=7, duration_ms=12)
    )

    assert state.active_exec_cell is None
    assert len(state.history_cells) == 1
    cell = state.history_cells[0]
    assert isinstance(cell, SemanticExecCell)
    assert cell.calls[0].command == ["echo", "one"]
    assert cell.calls[0].output is not None
    assert cell.calls[0].output.exit_code == 7
    assert cell.calls[0].output.aggregated_output == "done"
    assert cell.calls[0].duration == 0.012
    assert state.had_work_activity is True
    assert state.queued_input_sent is True


def test_completion_for_unknown_call_preserves_unrelated_active_exec_as_orphan_history():
    state = CommandLifecycleState()
    state.handle_command_execution_started_now(CommandExecutionItem("active", "sleep 10", "user_shell"))

    state.handle_command_execution_completed_now(
        CommandExecutionItem("orphan", "echo done", "unified_exec_startup", aggregated_output="done")
    )

    assert state.active_exec_cell is not None
    assert [call.call_id for call in state.active_exec_cell.calls] == ["active"]
    assert len(state.history_cells) == 1
    orphan = state.history_cells[0]
    assert isinstance(orphan, SemanticExecCell)
    assert orphan.calls[0].call_id == "orphan"
    assert orphan.calls[0].output is not None
    assert orphan.calls[0].output.formatted_output == "done"


def test_unified_exec_interaction_completion_hides_output_and_suppressed_call_is_dropped():
    state = CommandLifecycleState()
    state.handle_command_execution_started_now(CommandExecutionItem("wait-1", "bash -lc 'sleep 1'", "unified_exec_interaction"))
    state.handle_command_execution_completed_now(
        CommandExecutionItem("wait-1", "bash -lc 'sleep 1'", "unified_exec_interaction", aggregated_output="hidden")
    )

    cell = state.history_cells[0]
    assert isinstance(cell, SemanticExecCell)
    assert cell.calls[0].output is not None
    assert cell.calls[0].output.formatted_output == ""
    assert cell.calls[0].output.aggregated_output == ""

    state.handle_command_execution_started_now(CommandExecutionItem("wait-2", "bash -lc 'sleep 1'", "unified_exec_interaction"))
    state.handle_command_execution_completed_now(
        CommandExecutionItem("wait-2", "bash -lc 'sleep 1'", "unified_exec_interaction", aggregated_output="ignored")
    )

    assert len(state.history_cells) == 1
    assert "wait-2" not in state.suppressed_exec_calls


def test_public_started_and_completed_wrappers_track_unified_processes_and_wait_flushes():
    state = CommandLifecycleState()

    state.on_command_execution_started(CommandExecutionItem("call-1", "bash -lc 'echo hi'", "unified_exec_startup", process_id="proc-1", command_actions=[{"type": "exec"}]))
    state.on_terminal_interaction("proc-1", "")
    state.on_command_execution_completed(CommandExecutionItem("call-1", "echo hi", "unified_exec_startup", process_id="proc-1"))

    assert state.unified_exec_processes == []
    assert state.footer_processes == []
    assert state.flushed_wait_cells == [UnifiedExecInteractionCell("echo hi", "")]
