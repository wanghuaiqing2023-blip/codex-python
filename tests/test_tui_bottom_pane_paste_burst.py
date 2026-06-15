"""Parity tests for Rust ``codex-tui::bottom_pane::paste_burst``."""

from pycodex.tui.bottom_pane.paste_burst import (
    PASTE_BURST_ACTIVE_IDLE_TIMEOUT,
    PASTE_BURST_CHAR_INTERVAL,
    PASTE_ENTER_SUPPRESS_WINDOW,
    CharDecision,
    FlushResult,
    PasteBurst,
    retro_start_index,
)


def test_ascii_first_char_is_held_then_flushes_as_typed() -> None:
    # Rust test: ascii_first_char_is_held_then_flushes_as_typed.
    burst = PasteBurst()
    t0 = 0.0

    assert burst.on_plain_char("a", t0) == CharDecision.RETAIN_FIRST_CHAR

    t1 = t0 + PasteBurst.recommended_flush_delay() + 0.001
    assert burst.flush_if_due(t1) == FlushResult.typed("a")
    assert burst.is_active() is False


def test_ascii_two_fast_chars_start_buffer_from_pending_and_flush_as_paste() -> None:
    # Rust test: ascii_two_fast_chars_start_buffer_from_pending_and_flush_as_paste.
    burst = PasteBurst()
    t0 = 0.0
    assert burst.on_plain_char("a", t0) == CharDecision.RETAIN_FIRST_CHAR

    t1 = t0 + 0.001
    assert burst.on_plain_char("b", t1) == CharDecision.BEGIN_BUFFER_FROM_PENDING
    burst.append_char_to_buffer("b", t1)

    t2 = t1 + PasteBurst.recommended_active_flush_delay() + 0.001
    assert burst.flush_if_due(t2) == FlushResult.paste("ab")


def test_flush_before_modified_input_includes_pending_first_char() -> None:
    # Rust test: flush_before_modified_input_includes_pending_first_char.
    burst = PasteBurst()
    assert burst.on_plain_char("a", 0.0) == CharDecision.RETAIN_FIRST_CHAR

    assert burst.flush_before_modified_input() == "a"
    assert burst.is_active() is False


def test_decide_begin_buffer_only_triggers_for_pastey_prefixes() -> None:
    # Rust test: decide_begin_buffer_only_triggers_for_pastey_prefixes.
    burst = PasteBurst()
    now = 0.0

    assert burst.decide_begin_buffer(now, "ab", 2) is None
    assert burst.is_active() is False

    grab = burst.decide_begin_buffer(now, "a b", 2)
    assert grab is not None
    assert grab.start_byte == 1
    assert grab.grabbed == " b"
    assert burst.is_active() is True


def test_newline_suppression_window_outlives_buffer_flush() -> None:
    # Rust test: newline_suppression_window_outlives_buffer_flush.
    burst = PasteBurst()
    t0 = 0.0
    assert burst.on_plain_char("a", t0) == CharDecision.RETAIN_FIRST_CHAR

    t1 = t0 + 0.001
    assert burst.on_plain_char("b", t1) == CharDecision.BEGIN_BUFFER_FROM_PENDING
    burst.append_char_to_buffer("b", t1)

    t2 = t1 + PasteBurst.recommended_active_flush_delay() + 0.001
    assert burst.flush_if_due(t2) == FlushResult.paste("ab")
    assert burst.is_active() is False

    assert burst.newline_should_insert_instead_of_submit(t2) is True
    t3 = t1 + PASTE_ENTER_SUPPRESS_WINDOW + 0.001
    assert burst.newline_should_insert_instead_of_submit(t3) is False


def test_retro_start_index_uses_utf8_byte_indices() -> None:
    assert retro_start_index("abc", 0) == 3
    assert retro_start_index("abc", 2) == 1
    assert retro_start_index("\u6d63\u71fcb", 2) == len("\u6d63".encode("utf-8"))


def test_flush_if_due_uses_strictly_greater_than_timeout() -> None:
    # Rust source: flush_if_due intentionally uses `>` rather than `>=`.
    burst = PasteBurst()
    assert burst.on_plain_char("a", 0.0) == CharDecision.RETAIN_FIRST_CHAR
    assert burst.flush_if_due(PASTE_BURST_CHAR_INTERVAL) == FlushResult.none()
    assert burst.flush_if_due(PASTE_BURST_CHAR_INTERVAL + 0.001) == FlushResult.typed("a")

    burst = PasteBurst()
    assert burst.on_plain_char("a", 0.0) == CharDecision.RETAIN_FIRST_CHAR
    assert burst.on_plain_char("b", 0.001) == CharDecision.BEGIN_BUFFER_FROM_PENDING
    burst.append_char_to_buffer("b", 0.001)
    assert burst.flush_if_due(0.001 + PASTE_BURST_ACTIVE_IDLE_TIMEOUT) == FlushResult.none()
    assert burst.flush_if_due(0.001 + PASTE_BURST_ACTIVE_IDLE_TIMEOUT + 0.001) == FlushResult.paste("ab")

def test_active_append_newline_try_append_and_clear_boundaries() -> None:
    burst = PasteBurst()
    now = 0.0

    assert burst.append_newline_if_active(now) is False
    burst.begin_with_retro_grabbed("hello", now)
    assert burst.try_append_char_if_active("!", now) is True
    assert burst.append_newline_if_active(now) is True
    assert burst.buffer == "hello!\n"

    burst.clear_window_after_non_char()
    assert burst.active is False
    assert burst.buffer == "hello!\n"
    assert burst.try_append_char_if_active("x", now) is True
    assert burst.buffer == "hello!\nx"

    burst.clear_after_explicit_paste()
    assert burst.is_active() is False
    assert burst.buffer == ""


def test_no_hold_path_never_retains_first_char_and_can_begin_buffer() -> None:
    # Rust source: on_plain_char_no_hold is used for non-ASCII/IME input and
    # only returns None, BeginBuffer, or BufferAppend.
    burst = PasteBurst()

    assert burst.on_plain_char_no_hold(0.000) is None
    assert burst.pending_first_char is None
    assert burst.on_plain_char_no_hold(0.001) is None
    decision = burst.on_plain_char_no_hold(0.002)

    assert decision == CharDecision.begin_buffer(2)

    burst.begin_with_retro_grabbed("abcdef abcdef abcdef", 0.002)
    assert burst.on_plain_char_no_hold(0.003) == CharDecision.BUFFER_APPEND
