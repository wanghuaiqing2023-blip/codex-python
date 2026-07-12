from __future__ import annotations

# Rust source: codex/codex-rs/tui/src/exec_cell/model.rs
from pycodex.tui.exec_cell.model import CommandOutput, ExecCall, ExecCell, UNIFIED_EXEC_INTERACTION, USER_SHELL


def exploring_call(call_id: str = "call-1", parsed: list[object] | None = None) -> ExecCall:
    return ExecCall(
        call_id=call_id,
        command=["rg", "needle"],
        parsed=parsed or ["Search"],
        source="Tool",
        start_time=10.0,
    )


def test_exec_call_source_helpers_match_rust_variants() -> None:
    # Rust: ExecCall::is_user_shell_command and is_unified_exec_interaction.
    assert ExecCall("a", [], [], source=USER_SHELL).is_user_shell_command() is True
    assert ExecCall("a", [], [], source="Tool").is_user_shell_command() is False
    assert ExecCall("a", [], [], source=UNIFIED_EXEC_INTERACTION).is_unified_exec_interaction() is True


def test_exploring_cell_accepts_only_related_non_user_read_list_search_calls() -> None:
    # Rust: with_added_call appends only when both current cell and new call are exploring calls.
    cell = ExecCell.new(exploring_call("first", ["Read", {"kind": "ListFiles"}]), animations_enabled=True)
    added = cell.with_added_call("second", ["ls"], [{"Search": {}}], "Tool", interaction_input="more")

    assert added is not None
    assert [call.call_id for call in added.iter_calls()] == ["first", "second"]
    assert added.animations_enabled() is True
    assert added.calls[1].interaction_input == "more"
    assert cell.with_added_call("third", ["bash"], ["Search"], USER_SHELL) is None
    assert ExecCell.new(ExecCall("plain", ["echo"], [], source="Tool"), False).with_added_call("x", [], ["Read"], "Tool") is None


def test_complete_call_matches_most_recent_call_id_and_reports_miss() -> None:
    # Rust: complete_call searches calls in reverse and returns false on routing mismatch.
    older = exploring_call("dup")
    newer = exploring_call("dup")
    cell = ExecCell([older, newer], False)
    output = CommandOutput(exit_code=0, aggregated_output="ok", formatted_output="ok")

    assert cell.complete_call("missing", output, 1.5) is False
    assert cell.complete_call("dup", output, 2.0) is True
    assert older.output is None
    assert newer.output == output
    assert newer.duration == 2.0
    assert newer.start_time is None


def test_should_flush_only_for_completed_non_exploring_cells() -> None:
    # Rust: should_flush excludes exploring groups even when finished.
    non_exploring = ExecCell.new(ExecCall("u", ["echo"], [], source=USER_SHELL), False)
    assert non_exploring.should_flush() is False
    non_exploring.complete_call("u", CommandOutput(), 0.1)
    assert non_exploring.should_flush() is True

    exploring = ExecCell.new(exploring_call(), False)
    exploring.complete_call("call-1", CommandOutput(), 0.1)
    assert exploring.should_flush() is False


def test_mark_failed_finishes_only_pending_calls() -> None:
    # Rust: mark_failed gives unfinished calls exit_code 1 and leaves completed calls untouched.
    completed_output = CommandOutput(exit_code=0, aggregated_output="done", formatted_output="done")
    completed = ExecCall("done", [], [], output=completed_output, source="Tool", start_time=None)
    pending = ExecCall("pending", [], [], output=None, source="Tool", start_time=0.0)
    cell = ExecCell([completed, pending], False)

    cell.mark_failed()

    assert completed.output is completed_output
    assert pending.output == CommandOutput(exit_code=1, aggregated_output="", formatted_output="")
    assert pending.start_time is None
    assert pending.duration is not None


def test_active_state_and_active_start_time_match_first_pending_call() -> None:
    # Rust: active_start_time returns the first unfinished call start time.
    cell = ExecCell([
        ExecCall("done", [], [], output=CommandOutput(), source="Tool", start_time=None),
        ExecCall("pending", [], [], output=None, source="Tool", start_time=42.0),
    ])

    assert cell.is_active() is True
    assert cell.active_start_time() == 42.0
    cell.complete_call("pending", CommandOutput(), 0.2)
    assert cell.is_active() is False
    assert cell.active_start_time() is None


def test_append_output_rejects_empty_or_missing_and_creates_default_output() -> None:
    # Rust: append_output rejects empty chunks, reverse-matches call_id, and appends to aggregated output.
    older = exploring_call("dup")
    newer = exploring_call("dup")
    cell = ExecCell([older, newer], False)

    assert cell.append_output("dup", "") is False
    assert cell.append_output("missing", "x") is False
    assert cell.append_output("dup", "hello") is True
    assert older.output is None
    assert newer.output == CommandOutput(exit_code=0, aggregated_output="hello", formatted_output="")
    assert cell.append_output("dup", " world") is True
    assert newer.output is not None
    assert newer.output.aggregated_output == "hello world"
