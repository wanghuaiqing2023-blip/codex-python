"""Parity tests for Rust ``codex-tui::render::renderable``.

Rust source: ``codex/codex-rs/tui/src/render/renderable.rs``.
"""

from dataclasses import dataclass

from pycodex.tui.render.renderable import (
    Buffer,
    ColumnRenderable,
    DEFAULT_CURSOR_STYLE,
    FlexRenderable,
    InsetRenderable,
    Insets,
    ParagraphRenderable,
    Rect,
    RowRenderable,
    desired_height,
    from_,
    inset,
)
from pycodex.tui.ratatui_bridge import Line
from pycodex.tui.ratatui_bridge import Paragraph
from pycodex.tui.ratatui_bridge import Span
from pycodex.tui.ratatui_bridge import Style
from pycodex.tui.ratatui_bridge import Text
from pycodex.tui.ratatui_bridge import Wrap


@dataclass
class FakeRenderable:
    height: int
    name: str
    cursor: tuple[int, int] | None = None
    style: str = "FakeCursor"

    def render(self, area: Rect, buf: Buffer) -> None:
        if not area.is_empty():
            buf.set_line(area.x, area.y, Line.raw(self.name), max_width=area.width)

    def desired_height(self, width: int) -> int:
        return self.height

    def cursor_pos(self, area: Rect) -> tuple[int, int] | None:
        return self.cursor

    def cursor_style(self, area: Rect) -> str:
        return self.style


def test_text_and_none_renderables_match_basic_trait_impls() -> None:
    assert desired_height(None, 80) == 0
    assert desired_height("hello", 80) == 1
    buf = Buffer.empty(Rect.new(0, 0, 12, 4))
    from_("hello").render(Rect.new(1, 2, 10, 1), buf)
    assert buf.row_plain(2) == " hello      "


def test_bridge_span_line_text_and_paragraph_are_renderable_like_ratatui_types() -> None:
    # Rust: Renderable is implemented for ratatui Span, Line, and Paragraph.
    bold = Style.default().bold()
    span = Span.styled("hi", bold)
    line = Line.from_spans([span, " there"])
    text = Text.from_lines([line, "next"])
    paragraph = Paragraph(text).wrap_(Wrap(trim=False))

    span_buf = Buffer.empty(Rect.new(0, 0, 8, 1))
    from_(span).render(Rect.new(1, 0, 7, 1), span_buf)
    assert span_buf.row_plain(0) == " hi     "
    assert span_buf.cell(1, 0).style == bold

    line_buf = Buffer.empty(Rect.new(0, 0, 10, 1))
    from_(line).render(Rect.new(0, 0, 10, 1), line_buf)
    assert line_buf.row_plain(0) == "hi there  "
    assert line_buf.cell(0, 0).style == bold

    text_item = from_(text)
    assert text_item.desired_height(4) == 3

    paragraph_item = from_(paragraph)
    assert paragraph_item.desired_height(4) == 3
    paragraph_buf = Buffer.empty(Rect.new(0, 0, 4, 3))
    paragraph_item.render(Rect.new(0, 0, 4, 3), paragraph_buf)
    assert paragraph_buf.plain_lines() == ["hi t", "here", "next"]


def test_column_renderable_stacks_children_and_forwards_cursor() -> None:
    column = ColumnRenderable.with_(
        [FakeRenderable(2, "a"), FakeRenderable(3, "b", cursor=(4, 5), style="Bar")]
    )
    assert column.desired_height(10) == 5
    buf = Buffer.empty(Rect.new(0, 0, 10, 10))
    column.render(Rect.new(0, 0, 10, 10), buf)
    assert buf.plain_lines()[:5] == ["a         ", "          ", "b         ", "          ", "          "]
    assert column.cursor_pos(Rect.new(0, 0, 10, 10)) == (4, 5)
    assert column.cursor_style(Rect.new(0, 0, 10, 10)) == "Bar"


def test_column_renderable_clips_children_to_visible_area() -> None:
    # Rust: ColumnRenderable::render intersects each child area with the parent area.
    column = ColumnRenderable.with_(
        [FakeRenderable(3, "a"), FakeRenderable(3, "b")]
    )

    buf = Buffer.empty(Rect.new(0, 0, 10, 4))
    column.render(Rect.new(0, 0, 10, 4), buf)

    assert buf.plain_lines() == ["a         ", "          ", "          ", "b         "]


def test_flex_renderable_allocates_non_flex_then_flex_space() -> None:
    flex = FlexRenderable.new()
    flex.push(0, FakeRenderable(2, "fixed"))
    flex.push(1, FakeRenderable(100, "flex-a"))
    flex.push(2, FakeRenderable(100, "flex-b"))
    assert flex.allocate(Rect.new(0, 0, 10, 11)) == [
        Rect.new(0, 0, 10, 2),
        Rect.new(0, 2, 10, 3),
        Rect.new(0, 5, 10, 6),
    ]


def test_flex_renderable_gives_rounding_remainder_to_last_flex_child() -> None:
    # Rust: last flex child receives remaining free space after integer division.
    flex = FlexRenderable.new()
    flex.push(1, FakeRenderable(100, "flex-a"))
    flex.push(1, FakeRenderable(100, "flex-b"))

    assert flex.allocate(Rect.new(0, 0, 10, 5)) == [
        Rect.new(0, 0, 10, 2),
        Rect.new(0, 2, 10, 3),
    ]


def test_row_renderable_lays_out_by_width_and_reports_max_height() -> None:
    row = RowRenderable.new()
    row.push(4, FakeRenderable(2, "a"))
    row.push(10, FakeRenderable(5, "b"))
    assert row.desired_height(8) == 5
    buf = Buffer.empty(Rect.new(2, 3, 8, 9))
    row.render(Rect.new(2, 3, 8, 9), buf)
    assert buf.row_plain(3) == "a   b   "


def test_row_renderable_stops_rendering_when_width_is_exhausted() -> None:
    # Rust: RowRenderable::render breaks when the next child area is empty.
    row = RowRenderable.new()
    row.push(4, FakeRenderable(2, "a"))
    row.push(4, FakeRenderable(2, "b"))

    buf = Buffer.empty(Rect.new(0, 0, 4, 1))
    row.render(Rect.new(0, 0, 4, 1), buf)

    assert buf.plain() == "a   "


def test_row_renderable_forwards_cursor_style_from_first_cursor_child() -> None:
    row = RowRenderable.new()
    row.push(4, FakeRenderable(2, "a"))
    row.push(4, FakeRenderable(5, "b", cursor=(7, 3), style="RowCursor"))
    assert row.cursor_pos(Rect.new(0, 0, 8, 2)) == (7, 3)
    assert row.cursor_style(Rect.new(0, 0, 8, 2)) == "RowCursor"


def test_paragraph_renderable_counts_wrapped_lines_semantically() -> None:
    # Rust: Paragraph::desired_height delegates to Paragraph::line_count(width).
    paragraph = ParagraphRenderable.from_text("abcdef\nxy")
    assert paragraph.desired_height(3) == 3
    assert paragraph.desired_height(10) == 2


def test_inset_renderable_shrinks_area_and_adds_height() -> None:
    child = FakeRenderable(4, "inner", cursor=(9, 9), style="InsetCursor")
    wrapped = InsetRenderable.new(child, Insets.tlbr(1, 2, 3, 4))
    assert wrapped.desired_height(20) == 8
    buf = Buffer.empty(Rect.new(10, 20, 30, 40))
    wrapped.render(Rect.new(10, 20, 30, 40), buf)
    assert buf.row_plain(21).startswith("  inner")
    assert wrapped.cursor_style(Rect.new(10, 20, 30, 40)) == "InsetCursor"


def test_inset_helper_returns_renderable_item_and_default_cursor_style() -> None:
    item = inset("x", Insets.vh(1, 1))
    assert item.desired_height(5) == 3
    assert item.cursor_style(Rect.new(0, 0, 5, 5)) == DEFAULT_CURSOR_STYLE
