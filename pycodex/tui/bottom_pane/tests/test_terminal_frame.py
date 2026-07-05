import os

from pycodex.tui.bottom_pane.selection_popup_common import TerminalPopupLine
from pycodex.tui.bottom_pane.terminal_frame import (
    TerminalBottomPaneFrameWrite,
    TerminalBottomPaneState,
    bottom_pane_footprint_transition,
    bottom_pane_rows_for_size,
    composer_line_text,
    history_bottom_row,
    terminal_bottom_pane_frame,
    terminal_bottom_pane_frame_buffer,
    terminal_bottom_pane_frame_cursor_position,
    terminal_bottom_pane_frame_minimum_row_widths,
)
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface
from pycodex.tui.ratatui_bridge import Color as RatatuiColor
from pycodex.tui.ratatui_bridge import Position as RatatuiPosition
from pycodex.tui.ratatui_bridge import Rect as RatatuiRect


def test_terminal_frame_rows_reserve_idle_status_and_history_footprints() -> None:
    # Rust owner: codex-tui::chatwidget::rendering and app::resize_reflow
    # determine the live bottom-pane footprint that bounds scrollback history.
    size = os.terminal_size((80, 24))

    assert bottom_pane_rows_for_size(size, live_status_active=False) == [21, 22, 23, 24]
    assert bottom_pane_rows_for_size(size, live_status_active=True) == [19, 20, 21, 22, 23, 24]
    assert history_bottom_row(size, live_status_active=False) == 20
    assert history_bottom_row(size, live_status_active=True) == 18


def test_terminal_frame_tracks_live_status_footprint_transitions() -> None:
    # Rust owner: codex-tui::app::resize_reflow consumes bottom-pane footprint
    # changes so transcript history can be replayed without disappearing.
    size = os.terminal_size((80, 24))
    inactive = TerminalLiveStatusSurface.inactive()
    active = TerminalLiveStatusSurface.active_status("\u2022 Working")

    grow = bottom_pane_footprint_transition(size, inactive, active)
    shrink = bottom_pane_footprint_transition(size, active, inactive)

    assert grow.old_rows == (21, 22, 23, 24)
    assert grow.new_rows == (19, 20, 21, 22, 23, 24)
    assert grow.changed
    assert shrink.changed


def test_terminal_frame_builds_popup_layout_from_owner_projections() -> None:
    # Rust owners: bottom_pane::chat_composer owns composer placement, footer
    # owns footer projection, and status_surfaces owns live-status projection.
    size = os.terminal_size((72, 12))

    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(
                TerminalPopupLine("/model choose", True),
                TerminalPopupLine("/memories configure", False),
            ),
        ),
    )

    assert frame.clear_rows == (9, 10, 11, 12)
    assert frame.writes == (
        TerminalBottomPaneFrameWrite(9, 1, "\u203a /m"),
        TerminalBottomPaneFrameWrite(10, 1, "/model choose", True),
        TerminalBottomPaneFrameWrite(11, 1, "/memories configure", False),
        TerminalBottomPaneFrameWrite(12, 1, "gpt-test high"),
    )
    assert frame.cursor_column == len(composer_line_text("/m")) + 1


def test_terminal_frame_projects_popup_layout_to_ratatui_buffer() -> None:
    # Rust owners: chatwidget::rendering owns the bottom-pane frame, and
    # custom_terminal consumes the ratatui Buffer for redraw.  The projection
    # must remain side-effect free and outside terminal_surface.
    size = os.terminal_size((32, 12))
    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(
                TerminalPopupLine("/model choose", True),
                TerminalPopupLine("/memories configure", False),
            ),
        ),
    )

    buffer = terminal_bottom_pane_frame_buffer(size, frame)

    assert buffer.area == RatatuiRect.new(0, 8, 32, 4)
    assert buffer.plain_lines() == [
        "\u203a /m" + " " * 28,
        "/model choose" + " " * 19,
        "/memories configure" + " " * 13,
        "gpt-test high" + " " * 19,
    ]
    assert buffer.cell(0, 9).style.fg == RatatuiColor.LightBlue
    assert buffer.cell(0, 10).style.fg is None


def test_terminal_frame_projects_live_status_composer_and_footer_to_buffer() -> None:
    # Rust owners: chatwidget::status_surfaces owns live status projection,
    # bottom_pane::chat_composer owns composer projection, footer owns passive
    # footer projection, and chatwidget::rendering/custom_terminal consume the
    # final frame Buffer.
    size = os.terminal_size((40, 12))
    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(
            draft="hello",
            footer_text="gpt-test high \u00b7 ~\\repo",
            live_status_text="\u2022 Working",
        ),
    )

    buffer = terminal_bottom_pane_frame_buffer(size, frame)

    assert frame.clear_rows == (7, 8, 9, 10, 11, 12)
    assert buffer.area == RatatuiRect.new(0, 6, 40, 6)
    assert buffer.plain_lines() == [
        "\u2022 Working" + " " * 31,
        " " * 40,
        " " * 40,
        "\u203a hello" + " " * 33,
        " " * 40,
        "gpt-test high \u00b7 ~\\repo" + " " * 18,
    ]
    assert all(buffer.cell(0, y).style.fg is None for y in range(buffer.area.y, buffer.area.bottom()))


def test_terminal_frame_projects_cjk_composer_draft_in_terminal_cells() -> None:
    # Rust owners: bottom_pane::chat_composer owns composer text projection and
    # custom_terminal consumes ratatui cells. Wide CJK chars must occupy two
    # terminal cells so the second char is not skipped by diff rendering.
    size = os.terminal_size((40, 12))
    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(draft="你好", footer_text="gpt-test high"),
    )

    buffer = terminal_bottom_pane_frame_buffer(size, frame)
    composer_y = frame.cursor_row - 1

    assert buffer.cell(2, composer_y).symbol == "你"
    assert buffer.cell(3, composer_y).skip is True
    assert buffer.cell(4, composer_y).symbol == "好"
    assert buffer.cell(5, composer_y).skip is True
    assert terminal_bottom_pane_frame_cursor_position(frame) == RatatuiPosition.new(6, composer_y)
    assert terminal_bottom_pane_frame_minimum_row_widths(frame)[composer_y] == 6


def test_terminal_frame_projects_minimum_row_widths_for_backend_redraw() -> None:
    # Rust owners: chatwidget::rendering owns frame writes, while
    # custom_terminal consumes minimum visible row widths for full redraw.
    frame = terminal_bottom_pane_frame(
        os.terminal_size((32, 12)),
        TerminalBottomPaneState(draft="", footer_text="gpt-test high"),
    )

    assert terminal_bottom_pane_frame_minimum_row_widths(frame) == {
        9: 2,
        11: len("gpt-test high"),
    }


def test_terminal_frame_projects_cursor_position_for_backend_draw() -> None:
    # Rust owners: chatwidget::rendering owns composer cursor placement and
    # custom_terminal consumes the zero-based frame cursor during draw.
    frame = terminal_bottom_pane_frame(
        os.terminal_size((32, 12)),
        TerminalBottomPaneState(draft="/m", footer_text="gpt-test high"),
    )

    assert terminal_bottom_pane_frame_cursor_position(frame) == RatatuiPosition.new(
        len(composer_line_text("/m")),
        9,
    )
