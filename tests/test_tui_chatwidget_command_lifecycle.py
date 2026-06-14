from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/command_lifecycle.rs
# Behavior contract: unified-exec process tracking, footer sync data, recent
# output chunk retention, process end removal, and terminal wait streak flushing.

from pycodex.tui.chatwidget.command_lifecycle import CommandLifecycleState, UnifiedExecInteractionCell, command_display_from_raw


def test_command_display_from_raw_strips_bash_lc_wrapper():
    assert command_display_from_raw("bash -lc 'echo hi'") == "echo hi"


def test_track_unified_exec_process_begin_adds_and_updates_existing_process():
    state = CommandLifecycleState()

    state.track_unified_exec_process_begin("call-1", "proc-1", "bash -lc 'sleep 5'")
    assert [(p.key, p.call_id, p.command_display, p.recent_chunks) for p in state.unified_exec_processes] == [
        ("proc-1", "call-1", "sleep 5", [])
    ]
    assert state.footer_processes == ["sleep 5"]

    state.track_unified_exec_output_chunk("call-1", "old
")
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

    assert state.track_unified_exec_output_chunk("missing", "ignored
") is False
    assert state.track_unified_exec_output_chunk("call-1", b"one  

 two
three
four
") is True

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
