"""Transcript scrollback resize-reflow scheduling state.

Rust counterpart: ``codex-rs/tui/src/transcript_reflow.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from time import monotonic_ns
from typing import Any

from ._porting import RustTuiModule


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="transcript_reflow",
    source="codex/codex-rs/tui/src/transcript_reflow.rs",
    status="complete",
)

# Rust: Duration::from_millis(75). Python stores nanoseconds so callers can use
# deterministic monotonic clock stand-ins in tests.
TRANSCRIPT_REFLOW_DEBOUNCE = 75_000_000


@dataclass(frozen=True)
class TranscriptWidthChange:
    changed: bool
    initialized: bool


@dataclass
class TranscriptReflowState:
    last_observed_width: int | None = None
    last_reflow_width: int | None = None
    pending_reflow_width: int | None = None
    _pending_until: int | None = None
    ran_during_stream: bool = False
    resize_requested_during_stream: bool = False

    def clear(self) -> None:
        self.last_observed_width = None
        self.last_reflow_width = None
        self.pending_reflow_width = None
        self._pending_until = None
        self.ran_during_stream = False
        self.resize_requested_during_stream = False

    def note_width(self, width: int) -> TranscriptWidthChange:
        width = int(width)
        previous_width = self.last_observed_width
        self.last_observed_width = width
        if previous_width is None:
            self.last_reflow_width = width
        return TranscriptWidthChange(
            changed=previous_width is not None and previous_width != width,
            initialized=previous_width is None,
        )

    def reflow_needed_for_width(self, width: int) -> bool:
        width = int(width)
        return self.last_reflow_width != width and self.pending_reflow_width != width

    def schedule_debounced(self, target_width: int | None = None) -> bool:
        if target_width is not None:
            self.pending_reflow_width = int(target_width)
        self._pending_until = monotonic_ns() + TRANSCRIPT_REFLOW_DEBOUNCE
        return False

    def schedule_immediate(self) -> None:
        self.pending_reflow_width = None
        self._pending_until = monotonic_ns()

    def set_due_for_test(self) -> None:
        self._pending_until = monotonic_ns() - 1

    def pending_is_due(self, now: int | None = None) -> bool:
        if self._pending_until is None:
            return False
        return (monotonic_ns() if now is None else int(now)) >= self._pending_until

    def pending_until(self) -> int | None:
        return self._pending_until

    def has_pending_reflow(self) -> bool:
        return self._pending_until is not None

    def clear_pending_reflow(self) -> None:
        self._pending_until = None
        self.pending_reflow_width = None

    def mark_reflowed_width(self, width: int) -> bool:
        width = int(width)
        previous = self.last_reflow_width
        self.last_reflow_width = width
        return previous != width

    def mark_ran_during_stream(self) -> None:
        self.ran_during_stream = True

    def mark_resize_requested_during_stream(self) -> None:
        self.resize_requested_during_stream = True

    def take_stream_finish_reflow_needed(self) -> bool:
        needed = self.ran_during_stream or self.resize_requested_during_stream
        self.ran_during_stream = False
        self.resize_requested_during_stream = False
        return needed

    def clear_stream_flags(self) -> None:
        self.ran_during_stream = False
        self.resize_requested_during_stream = False


def schedule_debounced_postpones_existing_reflow() -> bool:
    state = TranscriptReflowState()
    if state.schedule_debounced(None):
        return False
    first_deadline = state.pending_until()
    if first_deadline is None:
        return False
    if state.schedule_debounced(None):
        return False
    second_deadline = state.pending_until()
    return second_deadline is not None and second_deadline >= first_deadline


def schedule_debounced_postpones_due_existing_reflow() -> bool:
    state = TranscriptReflowState()
    state.set_due_for_test()
    before_reschedule = monotonic_ns()
    if state.schedule_debounced(None):
        return False
    pending = state.pending_until()
    return pending is not None and pending > before_reschedule


def first_observed_width_marks_reflow_baseline() -> bool:
    state = TranscriptReflowState()
    width = state.note_width(80)
    return (
        width.initialized
        and not width.changed
        and state.last_observed_width == 80
        and state.last_reflow_width == 80
        and not state.reflow_needed_for_width(80)
    )


def mark_reflowed_width_records_actual_rebuild_width() -> bool:
    state = TranscriptReflowState()
    state.note_width(80)
    changed = state.mark_reflowed_width(100)
    return (
        changed
        and state.last_observed_width == 80
        and state.last_reflow_width == 100
    )


def reflow_needed_compares_against_actual_rebuild_width() -> bool:
    state = TranscriptReflowState()
    state.note_width(80)
    state.mark_reflowed_width(90)
    state.note_width(100)
    return state.reflow_needed_for_width(100)


def pending_reflow_target_prevents_repeated_reschedule() -> bool:
    state = TranscriptReflowState()
    state.note_width(80)
    needed_before = state.reflow_needed_for_width(100)
    state.schedule_debounced(100)
    return needed_before and not state.reflow_needed_for_width(100)


def clear_pending_reflow_allows_same_width_to_be_rescheduled() -> bool:
    state = TranscriptReflowState()
    state.note_width(80)
    state.schedule_debounced(100)
    state.clear_pending_reflow()
    return state.reflow_needed_for_width(100)


def mark_reflowed_width_reports_unchanged_width() -> bool:
    state = TranscriptReflowState()
    return (
        state.mark_reflowed_width(100)
        and not state.mark_reflowed_width(100)
        and state.last_reflow_width == 100
    )


def take_stream_finish_reflow_needed_drains_resize_request() -> bool:
    state = TranscriptReflowState()
    state.mark_resize_requested_during_stream()
    return state.take_stream_finish_reflow_needed() and not state.take_stream_finish_reflow_needed()


def take_stream_finish_reflow_needed_drains_ran_during_stream() -> bool:
    state = TranscriptReflowState()
    state.mark_ran_during_stream()
    return state.take_stream_finish_reflow_needed() and not state.take_stream_finish_reflow_needed()


def clear_resets_stream_reflow_flags() -> bool:
    state = TranscriptReflowState()
    state.mark_ran_during_stream()
    state.mark_resize_requested_during_stream()
    state.clear()
    return not state.take_stream_finish_reflow_needed()


__all__ = [
    "RUST_MODULE",
    "TRANSCRIPT_REFLOW_DEBOUNCE",
    "TranscriptReflowState",
    "TranscriptWidthChange",
    "clear_pending_reflow_allows_same_width_to_be_rescheduled",
    "clear_resets_stream_reflow_flags",
    "first_observed_width_marks_reflow_baseline",
    "mark_reflowed_width_records_actual_rebuild_width",
    "mark_reflowed_width_reports_unchanged_width",
    "pending_reflow_target_prevents_repeated_reschedule",
    "reflow_needed_compares_against_actual_rebuild_width",
    "schedule_debounced_postpones_due_existing_reflow",
    "schedule_debounced_postpones_existing_reflow",
    "take_stream_finish_reflow_needed_drains_ran_during_stream",
    "take_stream_finish_reflow_needed_drains_resize_request",
]
