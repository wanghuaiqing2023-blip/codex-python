# Parity source: codex-rs/tui/src/test_backend.rs

from pycodex.tui.test_backend import (
    Cell,
    ClearType,
    Position,
    Size,
    VT100Backend,
    append_lines,
    clear_region,
    draw,
    fmt,
    get_cursor_position,
    hide_cursor,
    scroll_region_down,
    scroll_region_up,
    set_cursor_position,
    show_cursor,
    size,
    window_size,
    write,
)


def test_new_size_window_size_and_display_contents():
    backend = VT100Backend.new(4, 2)

    assert size(backend) == Size(width=4, height=2)
    assert window_size(backend).columns_rows == Size(width=4, height=2)
    assert window_size(backend).pixels == Size(width=640, height=480)
    assert fmt(backend) == "    \n    "


def test_write_updates_screen_and_cursor_position():
    backend = VT100Backend.new(4, 2)

    assert write(backend, "abc") == 3

    assert fmt(backend) == "abc \n    "
    assert get_cursor_position(backend) == Position(3, 0)


def test_draw_writes_cell_content_at_coordinates():
    backend = VT100Backend.new(4, 2)

    draw(backend, [(1, 0, Cell("X")), (3, 1, "Y")])

    assert fmt(backend) == " X  \n   Y"


def test_cursor_visibility_and_position_controls():
    backend = VT100Backend.new(4, 2)

    hide_cursor(backend)
    assert backend.cursor_visible is False
    show_cursor(backend)
    assert backend.cursor_visible is True
    set_cursor_position(backend, Position(2, 1))
    assert get_cursor_position(backend) == Position(2, 1)


def test_clear_region_until_new_line_and_current_line():
    backend = VT100Backend.new(5, 2)
    write(backend, "abcde12345")
    set_cursor_position(backend, (2, 0))

    clear_region(backend, ClearType.UNTIL_NEW_LINE)
    assert fmt(backend).split("\n")[0] == "ab   "

    set_cursor_position(backend, (0, 1))
    clear_region(backend, ClearType.CURRENT_LINE)
    assert fmt(backend).split("\n")[1] == "     "


def test_clear_region_all_after_and_before_cursor():
    backend = VT100Backend.new(5, 3)
    write(backend, "abcde12345vwxyz")

    set_cursor_position(backend, (2, 1))
    clear_region(backend, ClearType.AFTER_CURSOR)
    assert fmt(backend) == "abcde\n12   \n     "

    clear_region(backend, ClearType.ALL)
    assert fmt(backend) == "     \n     \n     "
    assert get_cursor_position(backend) == Position(0, 0)

    write(backend, "abcde12345vwxyz")
    set_cursor_position(backend, (2, 1))
    clear_region(backend, ClearType.BEFORE_CURSOR)
    assert fmt(backend) == "     \n   45\nvwxyz"


def test_append_lines_keeps_terminal_height():
    backend = VT100Backend.new(3, 2)
    write(backend, "abc\ndef")

    append_lines(backend, 1)

    assert fmt(backend) == "def\n   "


def test_scroll_region_up_and_down():
    backend = VT100Backend.new(3, 3)
    write(backend, "aaa\nbbb\nccc")

    scroll_region_up(backend, range(0, 3), 1)
    assert fmt(backend) == "bbb\nccc\n   "

    scroll_region_down(backend, (0, 3), 1)
    assert fmt(backend) == "   \nbbb\nccc"
