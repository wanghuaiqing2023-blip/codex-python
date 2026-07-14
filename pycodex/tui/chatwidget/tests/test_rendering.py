from __future__ import annotations

import os
from types import SimpleNamespace

from pycodex.tui.bottom_pane.chat_composer import terminal_composer_line_text
from pycodex.tui.bottom_pane.selection_popup_common import TerminalPopupLine
from pycodex.tui.bottom_pane.terminal_action import TerminalBottomPaneState
from pycodex.tui.chatwidget.rendering import (
    BottomPaneComposerReserveRenderable,
    Rect,
    RenderLog,
    TerminalBottomPaneFrame,
    TerminalBottomPaneFrameWrite,
    TranscriptAreaRenderable,
    cursor_pos,
    cursor_style,
    desired_height,
    render,
    terminal_bottom_pane_frame,
    terminal_bottom_pane_frame_buffer,
)
from pycodex.tui.ratatui_bridge import Color as RatatuiColor


class Cell:
    def __init__(self, lines=("a", "b", "c"), height=3, should=True) -> None:
        self.lines = lines
        self.height = height
        self.should = should

    def display_lines(self, width: int):
        return [f"{line}:{width}" for line in self.lines]

    def desired_height(self, width: int) -> int:
        return self.height + width * 0

    def should_render(self) -> bool:
        return self.should


class BottomPane:
    def __init__(self) -> None:
        self.calls = []

    def render_with_composer_right_reserve(self, area, log, reserve):
        self.calls.append(("render", area, reserve))
        log.append("bottom", {"area": area, "reserve": reserve})

    def desired_height_with_composer_right_reserve(self, width, reserve):
        self.calls.append(("height", width, reserve))
        return 2

    def cursor_pos_with_composer_right_reserve(self, area, reserve):
        return (area.x + reserve, area.y)

    def cursor_style_with_composer_right_reserve(self, area, reserve):
        return "bar"


class Widget:
    def __init__(self) -> None:
        self.transcript = SimpleNamespace(active_cell=Cell())
        self.active_hook_cell = None
        self.bottom_pane = BottomPane()
        self.last_rendered_width = None

    def ambient_pet_wrap_reserved_cols(self) -> int:
        return 4


def test_transcript_area_child_area_saturates_width_height_and_adds_top() -> None:
    # Rust owner: codex-tui::chatwidget::rendering owns transcript-area
    # composition and bottom-pane reservation behavior for chatwidget render.
    renderable = TranscriptAreaRenderable(Cell(), top=1, right=4)

    assert renderable.child_area(Rect(2, 3, 10, 5)) == Rect(2, 4, 6, 4)
    assert renderable.child_area(Rect(0, 0, 2, 0)) == Rect(0, 1, 1, 0)


def test_transcript_area_render_scrolls_to_bottom_when_lines_overflow() -> None:
    log = RenderLog()
    renderable = TranscriptAreaRenderable(Cell(lines=("a", "b", "c", "d")), top=1, right=0)

    renderable.render(Rect(0, 0, 10, 3), log)

    assert log.entries[0][0] == "clear"
    assert log.entries[1][0] == "transcript"
    assert log.entries[1][1]["area"] == Rect(0, 1, 10, 2)
    assert log.entries[1][1]["scroll"] == (2, 0)


def test_bottom_pane_composer_reserve_delegates_render_height_cursor_and_style() -> None:
    bottom = BottomPane()
    renderable = BottomPaneComposerReserveRenderable(bottom, right_reserve=3)
    log = RenderLog()
    area = Rect(1, 2, 8, 4)

    renderable.render(area, log)

    assert bottom.calls == [("render", area, 3)]
    assert renderable.desired_height(20) == 2
    assert bottom.calls[-1] == ("height", 20, 3)
    assert renderable.cursor_pos(area) == (4, 2)
    assert renderable.cursor_style(area) == "bar"


def test_terminal_bottom_pane_frame_buffer_projects_frame_writes_into_cells() -> None:
    # Rust owner: codex-tui::chatwidget::rendering owns rendering content into
    # the ratatui buffer; custom_terminal consumes the resulting live viewport.
    frame = TerminalBottomPaneFrame(
        clear_rows=(9, 10),
        writes=(
            TerminalBottomPaneFrameWrite(9, 1, "> prompt"),
            TerminalBottomPaneFrameWrite(10, 1, "/model choose", True),
        ),
        cursor_row=9,
        cursor_column=9,
    )

    buffer = terminal_bottom_pane_frame_buffer(os.terminal_size((32, 12)), frame)

    assert buffer.area == Rect(0, 8, 32, 2)
    assert buffer.row_plain(8) == "> prompt" + " " * 24
    assert buffer.row_plain(9) == "/model choose" + " " * 19
    assert buffer.cell(0, 9).style.fg == RatatuiColor.LightBlue


def test_terminal_bottom_pane_frame_composes_owner_projections() -> None:
    # Rust owner: codex-tui::chatwidget::rendering composes bottom-pane
    # renderable content before custom_terminal projects it into terminal
    # side effects; the terminal adapter must not rebuild slash-popup rows.
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
    assert frame.cursor_row == 9
    assert frame.cursor_column == len(terminal_composer_line_text("/m")) + 1


def test_terminal_bottom_pane_frame_right_aligns_goal_footer_indicator() -> None:
    frame = terminal_bottom_pane_frame(
        os.terminal_size((48, 12)),
        TerminalBottomPaneState(
            draft="",
            footer_text="gpt-test low · ~\\repo",
            footer_right_text="Goal achieved (1m)",
        ),
    )

    footer = frame.writes[-1]
    assert footer.row == 12
    assert footer.text.startswith("gpt-test low · ~\\repo")
    assert footer.text.endswith("Goal achieved (1m)")
    assert len(footer.text) == 47


def test_terminal_bottom_pane_frame_projects_popup_rows_to_buffer() -> None:
    # Rust owner: codex-tui::chatwidget::rendering owns the side-effect-free
    # bottom-pane frame and buffer content projection. Terminal adapters should
    # never be the test owner for popup layout or selected-row styling.
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

    assert buffer.area == Rect(0, 8, 32, 4)
    assert buffer.plain_lines() == [
        "\u203a /m" + " " * 28,
        "/model choose" + " " * 19,
        "/memories configure" + " " * 13,
        "gpt-test high" + " " * 19,
    ]
    assert buffer.cell(0, 9).symbol == "/"
    assert buffer.cell(0, 9).style.fg == RatatuiColor.LightBlue
    assert buffer.cell(0, 10).style.fg is None


def test_terminal_bottom_pane_frame_renders_wrapped_composer_rows() -> None:
    # Fixed Rust owner: chatwidget::rendering composes every wrapped textarea
    # row into the frame before custom_terminal performs its diff.
    size = os.terminal_size((12, 12))

    frame = terminal_bottom_pane_frame(
        size,
        TerminalBottomPaneState(
            draft="alpha beta gamma",
            footer_text="footer",
        ),
    )

    assert frame.clear_rows == (7, 8, 9, 10, 11, 12)
    assert frame.writes == (
        TerminalBottomPaneFrameWrite(8, 1, "\u203a alpha"),
        TerminalBottomPaneFrameWrite(9, 1, "  beta"),
        TerminalBottomPaneFrameWrite(10, 1, "  gamma"),
        TerminalBottomPaneFrameWrite(12, 1, "footer"),
    )
    assert frame.cursor_row == 10
    assert frame.cursor_column == 8


def test_terminal_bottom_pane_frame_clear_rows_cover_previous_larger_popup_footprint() -> None:
    # Rust owner: codex-tui::chatwidget::rendering composes the frame rows that
    # custom_terminal later clears/draws. The surface adapter should not own
    # popup footprint shrink/grow semantics.
    frame = terminal_bottom_pane_frame(
        os.terminal_size((72, 12)),
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=(TerminalPopupLine("/model choose", True),),
        ),
        clear_popup_height=3,
    )

    assert frame.clear_rows == (8, 9, 10, 11, 12)
    assert TerminalBottomPaneFrameWrite(10, 1, "/model choose", True) in frame.writes


def test_chatwidget_render_composes_active_hook_and_bottom_and_records_width() -> None:
    widget = Widget()
    widget.active_hook_cell = Cell(lines=("hook",), height=1, should=True)

    log = render(widget, Rect(0, 0, 20, 10))

    kinds = [kind for kind, _ in log.entries]
    assert kinds.count("transcript") == 2
    assert "bottom" in kinds
    assert widget.last_rendered_width == 20


def test_desired_height_cursor_pos_and_style_delegate_to_composed_renderable() -> None:
    widget = Widget()

    assert desired_height(widget, 20) == 6
    assert cursor_pos(widget, Rect(0, 0, 20, 5)) == (4, 1)
    assert cursor_style(widget, Rect(0, 0, 20, 5)) == "bar"
