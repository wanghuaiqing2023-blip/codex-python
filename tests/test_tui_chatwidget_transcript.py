from __future__ import annotations

from pycodex.tui.chatwidget.transcript import (
    MAX_AGENT_COPY_HISTORY,
    U64_MAX,
    TranscriptState,
    active_cell_revision_wraps,
    copy_history_tracks_latest_visible_turn,
)


def test_active_cell_revision_wraps_like_rust_wrapping_add() -> None:
    state = TranscriptState(active_cell_revision=U64_MAX)

    state.bump_active_cell_revision()

    assert state.active_cell_revision == 0
    assert active_cell_revision_wraps() == 0


def test_copy_history_tracks_latest_visible_turn_after_rollback() -> None:
    state = TranscriptState()
    state.record_visible_user_turn()
    state.record_agent_markdown("first")
    state.record_visible_user_turn()
    state.record_agent_markdown("second")

    state.truncate_copy_history_to_user_turn_count(1)

    assert state.last_agent_markdown == "first"
    assert not state.copy_history_evicted_by_rollback
    assert copy_history_tracks_latest_visible_turn() == "first"


def test_record_agent_markdown_replaces_same_visible_turn_and_caps_history() -> None:
    state = TranscriptState()

    state.record_agent_markdown("draft")
    state.record_agent_markdown("final")

    assert len(state.agent_turn_markdowns) == 1
    assert state.agent_turn_markdowns[0].markdown == "final"
    assert state.last_agent_markdown == "final"
    assert state.saw_copy_source_this_turn

    for index in range(MAX_AGENT_COPY_HISTORY + 2):
        state.record_visible_user_turn()
        state.record_agent_markdown(f"m{index}")

    assert len(state.agent_turn_markdowns) == MAX_AGENT_COPY_HISTORY
    assert state.agent_turn_markdowns[0].markdown == "m2"


def test_reset_copy_history_clears_copy_state() -> None:
    state = TranscriptState()
    state.record_visible_user_turn()
    state.record_agent_markdown("answer")

    state.reset_copy_history()

    assert state.last_agent_markdown is None
    assert state.agent_turn_markdowns == []
    assert state.visible_user_turn_count == 0
    assert not state.copy_history_evicted_by_rollback
    assert not state.saw_copy_source_this_turn


def test_truncate_copy_history_marks_evicted_when_all_history_removed() -> None:
    state = TranscriptState()
    state.record_visible_user_turn()
    state.record_agent_markdown("answer")

    state.truncate_copy_history_to_user_turn_count(0)

    assert state.visible_user_turn_count == 0
    assert state.last_agent_markdown is None
    assert state.copy_history_evicted_by_rollback
    assert not state.saw_copy_source_this_turn


def test_reset_turn_flags_preserves_separator_and_plan_progress_like_rust() -> None:
    state = TranscriptState(
        saw_copy_source_this_turn=True,
        saw_plan_update_this_turn=True,
        saw_plan_item_this_turn=True,
        had_work_activity=True,
        latest_proposed_plan_markdown="plan",
        plan_delta_buffer="delta",
        plan_item_active=True,
        needs_final_message_separator=True,
        last_plan_progress=(1, 2),
    )

    state.reset_turn_flags()

    assert not state.saw_copy_source_this_turn
    assert not state.saw_plan_update_this_turn
    assert not state.saw_plan_item_this_turn
    assert not state.had_work_activity
    assert state.latest_proposed_plan_markdown is None
    assert state.plan_delta_buffer == ""
    assert not state.plan_item_active
    assert state.needs_final_message_separator is True
    assert state.last_plan_progress == (1, 2)
