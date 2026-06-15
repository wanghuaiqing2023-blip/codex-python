from __future__ import annotations

from pycodex.tui.custom_terminal import (
    BEL,
    ESC,
    Buffer,
    CaptureBackend,
    Position,
    Rect,
    Size,
    Terminal,
    diff_buffers,
    diff_buffers_clear_to_end_starts_after_wide_char,
    diff_buffers_does_not_emit_clear_to_end_for_full_width_row,
    display_width,
    reset_cursor_style_emits_default_user_shape,
    terminal_draw_applies_requested_cursor_style,
)


def test_display_width_ignores_osc_sequences() -> None:
    assert display_width("abc") == 3
    assert display_width(f"{ESC}]8;;https://example.com{BEL}link{ESC}]8;;{BEL}") == 4
    assert display_width(f"中{ESC}]9;payload{BEL}文") == 4

def test_diff_buffers_does_not_emit_clear_to_end_for_full_width_row() -> None:
    diff_buffers_does_not_emit_clear_to_end_for_full_width_row()


def test_diff_buffers_clear_to_end_starts_after_wide_char() -> None:
    diff_buffers_clear_to_end_starts_after_wide_char()


def test_terminal_draw_applies_requested_cursor_style() -> None:
    terminal_draw_applies_requested_cursor_style()


def test_reset_cursor_style_emits_default_user_shape() -> None:
    reset_cursor_style_emits_default_user_shape()


def test_terminal_visible_history_rows_are_capped_by_viewport_top() -> None:
    terminal = Terminal.with_screen_size_and_cursor_position(CaptureBackend.new(10, 5), Size(10, 5), Position(0, 3))
    terminal.set_viewport_area(Rect.new(0, 3, 10, 2))

    terminal.note_history_rows_inserted(10)

    assert terminal.visible_history_rows() == 3


def test_clear_scrollback_and_visible_screen_ansi_resets_state() -> None:
    terminal = Terminal.with_options(CaptureBackend.new(10, 5))
    terminal.set_viewport_area(Rect.new(0, 1, 10, 4))
    terminal.note_history_rows_inserted(1)

    terminal.clear_scrollback_and_visible_screen_ansi()

    assert "\x1b[r\x1b[0m\x1b[H\x1b[2J\x1b[3J\x1b[H" in terminal.backend().output()
    assert terminal.visible_history_rows() == 0
    assert terminal.last_known_cursor_pos == Position(0, 0)


def test_clear_empty_viewport_is_noop() -> None:
    terminal = Terminal.with_options(CaptureBackend.new(10, 5))

    terminal.clear()

    assert terminal.backend().output() == ""
    assert terminal.backend().cursor == Position(0, 0)


def test_diff_buffers_skips_clear_to_end_when_row_nonblank_extends_to_end() -> None:
    area = Rect.new(0, 0, 2, 1)
    previous = Buffer.empty(area)
    current = Buffer.empty(area)
    current.cell_mut((0, 0)).set_symbol("A")  # type: ignore[union-attr]
    current.cell_mut((1, 0)).set_symbol("B")  # type: ignore[union-attr]

    commands = diff_buffers(previous, current)

    assert not [command for command in commands if command.kind == "ClearToEnd"]
