from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.rendering import (
    BottomPaneComposerReserveRenderable,
    Rect,
    RenderLog,
    TranscriptAreaRenderable,
    cursor_pos,
    cursor_style,
    desired_height,
    render,
)


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
