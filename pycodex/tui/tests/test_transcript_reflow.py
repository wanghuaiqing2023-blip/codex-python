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
    # Rust crate/module/test:
    # - codex-tui::transcript_reflow
    # - transcript_reflow.rs::tests::schedule_debounced_postpones_existing_reflow
    assert schedule_debounced_postpones_existing_reflow()


def test_schedule_debounced_postpones_due_existing_reflow_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::schedule_debounced_postpones_due_existing_reflow
    assert schedule_debounced_postpones_due_existing_reflow()


def test_first_observed_width_marks_reflow_baseline_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::first_observed_width_marks_reflow_baseline
    assert first_observed_width_marks_reflow_baseline()


def test_mark_reflowed_width_records_actual_rebuild_width_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::mark_reflowed_width_records_actual_rebuild_width
    assert mark_reflowed_width_records_actual_rebuild_width()


def test_reflow_needed_compares_against_actual_rebuild_width_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::reflow_needed_compares_against_actual_rebuild_width
    assert reflow_needed_compares_against_actual_rebuild_width()


def test_pending_reflow_target_prevents_repeated_reschedule_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::pending_reflow_target_prevents_repeated_reschedule
    assert pending_reflow_target_prevents_repeated_reschedule()


def test_clear_pending_reflow_allows_same_width_to_be_rescheduled_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::clear_pending_reflow_allows_same_width_to_be_rescheduled
    assert clear_pending_reflow_allows_same_width_to_be_rescheduled()


def test_mark_reflowed_width_reports_unchanged_width_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::mark_reflowed_width_reports_unchanged_width
    assert mark_reflowed_width_reports_unchanged_width()


def test_take_stream_finish_reflow_needed_drains_resize_request_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::take_stream_finish_reflow_needed_drains_resize_request
    assert take_stream_finish_reflow_needed_drains_resize_request()


def test_take_stream_finish_reflow_needed_drains_ran_during_stream_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::take_stream_finish_reflow_needed_drains_ran_during_stream
    assert take_stream_finish_reflow_needed_drains_ran_during_stream()


def test_clear_resets_stream_reflow_flags_matches_rust() -> None:
    # Rust: transcript_reflow.rs::tests::clear_resets_stream_reflow_flags
    assert clear_resets_stream_reflow_flags()


def test_schedule_immediate_sets_due_and_clears_target_width() -> None:
    # Rust source contract: TranscriptReflowState::schedule_immediate clears
    # pending_reflow_width and makes pending_is_due true at the next read.
    state = TranscriptReflowState()
    state.schedule_debounced(100)
    state.schedule_immediate()

    assert state.pending_reflow_width is None
    assert state.has_pending_reflow()
    assert state.pending_is_due()


def test_has_pending_reflow_tracks_pending_until_state() -> None:
    # Rust source contract: has_pending_reflow reflects pending_until only.
    state = TranscriptReflowState()
    assert not state.has_pending_reflow()

    state.schedule_debounced(100)
    assert state.has_pending_reflow()

    state.clear_pending_reflow()
    assert not state.has_pending_reflow()


def test_clear_stream_flags_preserves_width_and_pending_state() -> None:
    # Rust source contract: clear_stream_flags drains only stream repair flags,
    # preserving observed/reflowed widths and pending deadlines.
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
    # Rust source: TRANSCRIPT_REFLOW_DEBOUNCE = Duration::from_millis(75).
    assert TRANSCRIPT_REFLOW_DEBOUNCE == 75_000_000
