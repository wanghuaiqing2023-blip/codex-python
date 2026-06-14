from pycodex.tui.transcript_reflow import (
    TRANSCRIPT_REFLOW_DEBOUNCE,
    TranscriptReflowState,
    clear_pending_reflow_allows_same_width_to_be_rescheduled,
    clear_resets_stream_reflow_flags,
    first_observed_width_marks_reflow_baseline,
    mark_reflowed_width_records_actual_rebuild_width,
    mark_reflowed_width_reports_unchanged_width,
    pending_reflow_target_prevents_repeated_reschedule,
    reflow_needed_compares_against_actual_rebuild_width,
    schedule_debounced_postpones_due_existing_reflow,
    schedule_debounced_postpones_existing_reflow,
    take_stream_finish_reflow_needed_drains_ran_during_stream,
    take_stream_finish_reflow_needed_drains_resize_request,
)


def test_schedule_debounced_postpones_existing_reflow_matches_rust() -> None:
    # Rust: transcript_reflow.rs schedule_debounced_postpones_existing_reflow
    assert schedule_debounced_postpones_existing_reflow()


def test_schedule_debounced_postpones_due_existing_reflow_matches_rust() -> None:
    # Rust: schedule_debounced_postpones_due_existing_reflow
    assert schedule_debounced_postpones_due_existing_reflow()


def test_first_observed_width_marks_reflow_baseline_matches_rust() -> None:
    # Rust: first_observed_width_marks_reflow_baseline
    assert first_observed_width_marks_reflow_baseline()


def test_mark_reflowed_width_records_actual_rebuild_width_matches_rust() -> None:
    # Rust: mark_reflowed_width_records_actual_rebuild_width
    assert mark_reflowed_width_records_actual_rebuild_width()


def test_reflow_needed_compares_against_actual_rebuild_width_matches_rust() -> None:
    # Rust: reflow_needed_compares_against_actual_rebuild_width
    assert reflow_needed_compares_against_actual_rebuild_width()


def test_pending_reflow_target_prevents_repeated_reschedule_matches_rust() -> None:
    # Rust: pending_reflow_target_prevents_repeated_reschedule
    assert pending_reflow_target_prevents_repeated_reschedule()


def test_clear_pending_reflow_allows_same_width_to_be_rescheduled_matches_rust() -> None:
    # Rust: clear_pending_reflow_allows_same_width_to_be_rescheduled
    assert clear_pending_reflow_allows_same_width_to_be_rescheduled()


def test_mark_reflowed_width_reports_unchanged_width_matches_rust() -> None:
    # Rust: mark_reflowed_width_reports_unchanged_width
    assert mark_reflowed_width_reports_unchanged_width()


def test_take_stream_finish_reflow_needed_drains_resize_request_matches_rust() -> None:
    # Rust: take_stream_finish_reflow_needed_drains_resize_request
    assert take_stream_finish_reflow_needed_drains_resize_request()


def test_take_stream_finish_reflow_needed_drains_ran_during_stream_matches_rust() -> None:
    # Rust: take_stream_finish_reflow_needed_drains_ran_during_stream
    assert take_stream_finish_reflow_needed_drains_ran_during_stream()


def test_clear_resets_stream_reflow_flags_matches_rust() -> None:
    # Rust: clear_resets_stream_reflow_flags
    assert clear_resets_stream_reflow_flags()


def test_schedule_immediate_sets_due_and_clears_target_width() -> None:
    state = TranscriptReflowState()
    state.schedule_debounced(100)
    state.schedule_immediate()

    assert state.pending_reflow_width is None
    assert state.has_pending_reflow()
    assert state.pending_is_due()


def test_has_pending_reflow_tracks_pending_until_state() -> None:
    state = TranscriptReflowState()
    assert not state.has_pending_reflow()

    state.schedule_debounced(100)
    assert state.has_pending_reflow()

    state.clear_pending_reflow()
    assert not state.has_pending_reflow()


def test_clear_stream_flags_preserves_width_and_pending_state() -> None:
    state = TranscriptReflowState()
    state.note_width(80)
    state.schedule_debounced(100)
    state.mark_ran_during_stream()
    state.mark_resize_requested_during_stream()

    state.clear_stream_flags()

    assert state.last_observed_width == 80
    assert state.pending_reflow_width == 100
    assert state.has_pending_reflow()
    assert not state.take_stream_finish_reflow_needed()


def test_debounce_constant_matches_rust_duration() -> None:
    assert TRANSCRIPT_REFLOW_DEBOUNCE == 75_000_000
