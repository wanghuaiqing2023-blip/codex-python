from __future__ import annotations

from pycodex.tui.app.session_lifecycle import (
    can_fallback_from_include_turns_error,
    closed_state_for_thread_read_error,
    is_terminal_thread_read_error,
)


def test_terminal_thread_read_error_detection_matches_not_loaded_errors() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: thread not loaded: thr_123"
    )

    assert is_terminal_thread_read_error(err)


def test_terminal_thread_read_error_detection_ignores_transient_failures() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read transport error: broken pipe"
    )

    assert not is_terminal_thread_read_error(err)


def test_closed_state_for_thread_read_error_preserves_live_state_without_cache_on_transient_error() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read transport error: broken pipe"
    )

    assert not closed_state_for_thread_read_error(err, None)
    assert closed_state_for_thread_read_error(err, True)


def test_closed_state_for_thread_read_error_marks_terminal_uncached_threads_closed() -> None:
    err = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: thread not loaded: thr_123"
    )

    assert closed_state_for_thread_read_error(err, None)


def test_include_turns_fallback_detection_handles_unmaterialized_and_ephemeral_threads() -> None:
    unmaterialized = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: thread thr_123 is not materialized yet; includeTurns is unavailable before first user message"
    )
    ephemeral = RuntimeError(
        "thread/read failed during TUI session lookup: thread/read failed: ephemeral threads do not support includeTurns"
    )
    transient = RuntimeError("thread/read transport error: broken pipe")

    assert can_fallback_from_include_turns_error(unmaterialized)
    assert can_fallback_from_include_turns_error(ephemeral)
    assert not can_fallback_from_include_turns_error(transient)
