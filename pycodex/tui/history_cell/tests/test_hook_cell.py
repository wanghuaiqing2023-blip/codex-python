"""Parity tests for codex-rs/tui/src/history_cell/hook_cell.rs."""

from pycodex.tui.history_cell.hook_cell import (
    HOOK_RUN_REVEAL_DELAY,
    HookCell,
    HookEventName,
    HookOutputEntry,
    HookOutputEntryKind,
    HookRunStatus,
    HookRunSummary,
    hook_completed_bullet,
    hook_event_label,
    hook_output_prefix,
    new_active_hook_cell,
    new_completed_hook_cell,
)


def texts(lines):
    return ["".join(span.content for span in line.spans) for line in lines]


def hook_run_summary(id_: str = "hook-1", **kwargs):
    return HookRunSummary(
        id=id_,
        event_name=kwargs.get("event_name", HookEventName.PostToolUse),
        status=kwargs.get("status", HookRunStatus.Running),
        status_message=kwargs.get("status_message", "checking output policy"),
        entries=tuple(kwargs.get("entries", ())),
    )


def test_pending_hook_does_not_render_or_animate_transcript() -> None:
    cell = new_active_hook_cell(hook_run_summary(), animations_enabled=True)

    assert cell.should_render() is False
    assert cell.transcript_animation_tick() is None
    assert texts(cell.display_lines(80)) == []


def test_visible_hook_animates_only_when_animations_enabled() -> None:
    animated = new_active_hook_cell(hook_run_summary(), animations_enabled=True)
    animated.reveal_running_runs_now_for_test()
    animated.advance_time()

    static = new_active_hook_cell(hook_run_summary(), animations_enabled=False)
    static.reveal_running_runs_now_for_test()
    static.advance_time()

    assert animated.transcript_animation_tick() == 0
    assert static.transcript_animation_tick() is None
    assert texts(static.display_lines(80)) == [
        "Running PostToolUse hook: checking output policy"
    ]


def test_duplicate_start_refreshes_existing_run_instead_of_adding_row() -> None:
    cell = HookCell.new_active(hook_run_summary("hook-1"), False)
    cell.start_run(hook_run_summary("hook-1", status_message="new status"))

    assert len(cell.runs) == 1
    assert cell.runs[0].status_message == "new status"


def test_quiet_success_removed_if_never_visible_and_lingers_if_visible() -> None:
    cell = HookCell.new_active(hook_run_summary("hook-1"), False)
    assert cell.complete_run(hook_run_summary("hook-1", status=HookRunStatus.Completed, entries=())) is True
    assert cell.is_empty() is True

    visible = HookCell.new_active(hook_run_summary("hook-2"), False)
    visible.reveal_running_runs_now_for_test()
    visible.advance_time()
    assert visible.complete_run(hook_run_summary("hook-2", status=HookRunStatus.Completed, entries=())) is True
    assert visible.should_render() is True
    visible.expire_quiet_runs_now_for_test()
    assert visible.advance_time() is True
    assert visible.is_empty() is True


def test_completed_failure_persists_and_can_be_taken() -> None:
    cell = HookCell.new_active(hook_run_summary("hook-1"), False)
    completed = hook_run_summary(
        "hook-1",
        status=HookRunStatus.Failed,
        entries=[HookOutputEntry(HookOutputEntryKind.Error, "nope")],
    )

    assert cell.complete_run(completed) is True
    assert cell.should_flush() is True
    persistent = cell.take_completed_persistent_runs()

    assert persistent is not None
    assert cell.is_empty() is True
    assert texts(persistent.display_lines(80)) == [
        "* PostToolUse hook (failed)",
        "  error: nope",
    ]


def test_completed_quiet_success_replay_is_ignored() -> None:
    cell = new_completed_hook_cell(
        hook_run_summary("hook-1", status=HookRunStatus.Completed, entries=()),
        animations_enabled=False,
    )

    assert cell.is_empty() is True


def test_running_hooks_are_grouped_when_adjacent_with_same_key() -> None:
    cell = HookCell.new_active(hook_run_summary("hook-1"), False)
    cell.start_run(hook_run_summary("hook-2"))
    cell.reveal_running_runs_now_for_test()
    cell.advance_time()

    assert texts(cell.display_lines(80)) == [
        "Running 2 PostToolUse hooks: checking output policy"
    ]


def test_hook_helpers_match_rust_labels_and_prefixes() -> None:
    warning = [HookOutputEntry(HookOutputEntryKind.Warning, "heads up")]
    bullet = hook_completed_bullet(HookRunStatus.Completed, warning)

    assert bullet.content == "*"
    assert bullet.style == "bold"
    assert hook_output_prefix(HookOutputEntryKind.Context) == "hook context: "
    assert hook_event_label(HookEventName.PermissionRequest) == "PermissionRequest"
    assert HOOK_RUN_REVEAL_DELAY == 0.300
