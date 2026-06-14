from __future__ import annotations

from pycodex.tui import textual_compat
from pycodex.tui.ratatui_bridge import (
    Alignment,
    Block,
    BorderType,
    Borders,
    Buffer,
    Cell,
    Clear,
    Color,
    Constraint,
    Direction,
    Layout,
    Line,
    Margin,
    Modifier,
    Paragraph,
    Rect,
    Renderable,
    Span,
    Style,
    Terminal,
    TestBackend as BridgeTestBackend,
    Text,
    Wrap,
    buffer_to_plain_text,
    buffer_to_rich_text,
    render_ref,
    render_to_buffer,
    render_to_rich_text,
)


def test_style_patch_and_modifiers_preserve_ratatui_like_semantics() -> None:
    base = Style().with_fg("cyan").bold()
    patched = base.patch(Style().with_bg(Color.rgb(1, 2, 3)).dim())

    assert patched.fg == Color.named("cyan")
    assert patched.bg == Color.rgb(1, 2, 3)
    assert patched.modifiers == frozenset({Modifier.BOLD, Modifier.DIM})


def test_span_line_text_plain_and_width_helpers() -> None:
    line = Line.from_spans([Span.raw("hi"), Span.styled("!", Style().bold())])
    text = Text.from_lines([line, "there"])

    assert line.plain == "hi!"
    assert line.width == 3
    assert text.plain == "hi!\nthere"


def test_rect_inner_saturates_like_ratatui_area_math() -> None:
    rect = Rect(2, 3, 10, 4)

    assert rect.area() == 40
    assert rect.inner(1) == Rect(3, 4, 8, 2)
    assert rect.inner(horizontal=6, vertical=3) == Rect(8, 6, 0, 0)
    assert rect.inner(horizontal=6, vertical=3).is_empty()


def test_rich_conversion_methods_exist_and_use_textual_compat_boundary() -> None:
    span = Span.styled("hello", Style().with_fg("red").bold())
    rich_text = span.to_rich_text()

    assert str(rich_text) == "hello"
    assert isinstance(rich_text, textual_compat.Text)


def test_line_and_text_conversion_preserve_plain_content_with_vendored_rich_text() -> None:
    line = Line.from_spans([Span.raw("hi"), Span.styled("!", Style().with_fg(Color.rgb(1, 2, 3)).bold())])
    text = Text.from_lines([line, "there"])

    assert isinstance(line.to_rich_text(), textual_compat.Text)
    assert isinstance(text.to_rich_text(), textual_compat.Text)
    assert str(line.to_rich_text()) == "hi!"
    assert str(text.to_rich_text()) == "hi!\nthere"


def test_buffer_set_cell_and_out_of_bounds_reads_are_safe() -> None:
    buffer = Buffer.empty(Rect(10, 20, 4, 2))
    style = Style().with_fg("green").bold()

    buffer.set_cell(11, 20, Cell("A", style))
    buffer.set_symbol(12, 20, "BC")
    buffer.set_symbol(99, 99, "x")

    assert buffer.cell(11, 20) == Cell("A", style)
    assert buffer.cell(12, 20).symbol == "B"
    assert buffer.cell(99, 99) == Cell.blank()
    assert buffer.plain_lines() == [" AB ", "    "]


def test_buffer_set_span_line_and_text_preserve_styles_and_width_limits() -> None:
    bold = Style().bold()
    dim = Style().dim()
    buffer = Buffer.empty(Rect(0, 0, 6, 3))
    line = Line.from_spans([Span.styled("hi", bold), Span.styled("there", dim)])
    text = Text.from_lines([line, "ok"])

    assert buffer.set_line(0, 0, line, max_width=4) == 4
    assert buffer.row_plain(0) == "hith  "
    assert buffer.cell(0, 0).style == bold
    assert buffer.cell(2, 0).style == dim

    assert buffer.set_text(1, 1, text, max_width=3) == 5
    assert buffer.row_plain(1) == " hit  "
    assert buffer.row_plain(2) == " ok   "


def test_renderable_protocol_writes_to_shared_buffer_model() -> None:
    class Greeting:
        def render(self, area: Rect, buffer: Buffer) -> None:
            buffer.set_line(area.x, area.y, Line.raw("hello"), max_width=area.width)

        def desired_height(self, width: int) -> int:
            return 1

    renderable = Greeting()
    buffer = Buffer.empty(Rect(2, 3, 4, 1))

    assert isinstance(renderable, Renderable)
    renderable.render(buffer.area, buffer)
    assert buffer.plain() == "hell"


def test_layout_constraints_split_area_with_rust_like_remainder_rules() -> None:
    layout = Layout(
        Direction.VERTICAL,
        [
            Constraint.Length(2),
            Constraint.Percentage(25),
            Constraint.Fill(1),
            Constraint.Fill(2),
        ],
        margin=Margin.new(1, 1),
    )

    assert layout.split(Rect.new(10, 20, 8, 10)) == [
        Rect.new(11, 21, 6, 2),
        Rect.new(11, 23, 6, 2),
        Rect.new(11, 25, 6, 1),
        Rect.new(11, 26, 6, 3),
    ]

    assert Layout.horizontal([Constraint.Ratio(1, 2), Constraint.Fill(1)]).areas(Rect.new(0, 0, 9, 3)) == (
        Rect.new(0, 0, 4, 3),
        Rect.new(4, 0, 5, 3),
    )


def test_block_borders_support_side_flags_inner_area_and_unicode_border_types() -> None:
    buffer = Buffer.empty(Rect.new(0, 0, 8, 4))
    block = (
        Block.default()
        .borders_(Borders.TOP | Borders.LEFT | Borders.RIGHT)
        .border_type_(BorderType.Rounded)
        .title_("T")
    )

    block.render(buffer.area, buffer)

    assert block.inner(buffer.area) == Rect.new(1, 1, 6, 3)
    assert buffer.row_plain(0) == "╭T─────╮"
    assert buffer.row_plain(1) == "│      │"
    assert buffer.row_plain(3) == "│      │"


def test_paragraph_wrap_alignment_scroll_and_clear_render_to_buffer() -> None:
    paragraph = (
        Paragraph.raw("abcdefgh\nxy")
        .wrap_(Wrap(trim=True))
        .alignment_(Alignment.CENTER)
        .scroll_(1, 0)
    )
    buffer = Buffer.empty(Rect.new(0, 0, 6, 3))
    buffer.fill(buffer.area, Cell("."))

    paragraph.render(buffer.area, buffer)

    assert buffer.plain_lines() == ["..gh..", "..xy..", "......"]

    Clear().render(Rect.new(1, 0, 3, 2), buffer)
    assert buffer.plain_lines() == [".   ..", ".   ..", "......"]


def test_textual_adapter_converts_buffer_and_renderables_without_terminal_io() -> None:
    paragraph = Paragraph(Text.from_lines(["hello", Line.from_spans([Span.styled("ok", Style().bold())])]))
    buffer = render_to_buffer(paragraph, Rect.new(0, 0, 5, 2))

    assert buffer_to_plain_text(buffer, trim_end=True) == "hello\nok"
    rich = buffer_to_rich_text(buffer, trim_end=True)
    assert isinstance(rich, textual_compat.Text)
    assert str(rich) == "hello\nok"
    assert str(render_to_rich_text(paragraph, Rect.new(0, 0, 5, 2), trim_end=True)) == "hello\nok"


def test_widget_ref_helper_prefers_render_ref_and_falls_back_to_render() -> None:
    class RefWidget:
        def render_ref(self, area: Rect, buffer: Buffer) -> None:
            buffer.set_line(area.x, area.y, Line.raw("ref"), max_width=area.width)

    class PlainWidget:
        def render(self, area: Rect, buffer: Buffer) -> None:
            buffer.set_line(area.x, area.y, Line.raw("plain"), max_width=area.width)

    buffer = Buffer.empty(Rect.new(0, 0, 5, 2))
    render_ref(RefWidget(), Rect.new(0, 0, 5, 1), buffer)
    render_ref(PlainWidget(), Rect.new(0, 1, 5, 1), buffer)

    assert buffer.plain_lines() == ["ref  ", "plain"]


def test_terminal_draw_uses_test_backend_buffer_and_flushes_once() -> None:
    backend = BridgeTestBackend.new(6, 2)
    terminal = Terminal.new(backend)

    def draw(frame):
        frame.render_widget(Paragraph.raw("hello"), Rect.new(0, 0, 6, 1))
        frame.render_widget_ref(Paragraph.raw("world"), Rect.new(0, 1, 6, 1))
        return frame.size()

    assert terminal.draw(draw) == Rect.new(0, 0, 6, 2)
    assert backend.flush_count == 1
    assert backend.buffer().plain_lines() == ["hello ", "world "]


def test_layout_clips_when_fixed_constraints_exceed_available_space() -> None:
    layout = Layout.vertical([Constraint.Length(4), Constraint.Length(4), Constraint.Fill(1)])

    assert layout.split(Rect.new(0, 0, 3, 6)) == [
        Rect.new(0, 0, 3, 4),
        Rect.new(0, 4, 3, 2),
        Rect.new(0, 6, 3, 0),
    ]


def test_layout_min_constraints_share_remaining_space_and_zero_area_is_safe() -> None:
    layout = Layout.vertical([Constraint.Min(1), Constraint.Min(1), Constraint.Length(1)])

    assert layout.split(Rect.new(0, 0, 4, 8)) == [
        Rect.new(0, 0, 4, 4),
        Rect.new(0, 4, 4, 3),
        Rect.new(0, 7, 4, 1),
    ]
    assert layout.split(Rect.new(0, 0, 0, 0)) == [
        Rect.new(0, 0, 0, 0),
        Rect.new(0, 0, 0, 0),
        Rect.new(0, 0, 0, 0),
    ]


def test_buffer_fill_and_style_are_clipped_to_intersection_with_nonzero_origin() -> None:
    buffer = Buffer.empty(Rect.new(5, 7, 4, 3))
    red = Style.default().with_fg(Color.Red)
    blue = Style.default().with_fg(Color.Blue)

    buffer.fill(Rect.new(3, 6, 4, 3), Cell("x", red))
    buffer.set_style(Rect.new(6, 8, 10, 10), blue)

    assert buffer.plain_lines() == ["xx  ", "xx  ", "    "]
    assert buffer.cell(5, 7).style == red
    assert buffer.cell(6, 8).style == blue
    assert buffer.cell(8, 9).style == blue
    assert buffer.cell(5, 9) == Cell.blank()


def test_buffer_indexing_matches_cell_access_and_ignores_out_of_bounds_writes() -> None:
    buffer = Buffer.empty(Rect.new(2, 2, 2, 2))
    buffer[3, 3] = Cell("z")
    buffer[100, 100] = Cell("q")

    assert buffer[3, 3].symbol == "z"
    assert buffer[100, 100] == Cell.blank()
    assert buffer.plain_lines() == ["  ", " z"]


def test_paragraph_preserves_multispan_styles_with_horizontal_scroll() -> None:
    bold = Style.default().bold()
    dim = Style.default().dim()
    paragraph = Paragraph(Text.from_lines([Line.from_spans([Span.styled("abc", bold), Span.styled("def", dim)])])).scroll_(0, 2)
    buffer = Buffer.empty(Rect.new(0, 0, 3, 1))

    paragraph.render(buffer.area, buffer)

    assert buffer.plain() == "cde"
    assert buffer.cell(0, 0).style == bold
    assert buffer.cell(1, 0).style == dim
    assert buffer.cell(2, 0).style == dim


def test_paragraph_no_wrap_truncates_to_width_and_respects_height_limit() -> None:
    paragraph = Paragraph.raw("abcdef\nsecond")
    buffer = Buffer.empty(Rect.new(0, 0, 4, 1))

    paragraph.render(buffer.area, buffer)

    assert buffer.plain() == "abcd"


def test_paragraph_with_block_renders_inside_inner_area() -> None:
    paragraph = Paragraph.raw("body").block_(Block.default().bordered().title_("X"))
    buffer = Buffer.empty(Rect.new(0, 0, 8, 3))

    paragraph.render(buffer.area, buffer)

    assert buffer.row_plain(0) == "┌X─────┐"
    assert buffer.row_plain(1) == "│body  │"
    assert buffer.row_plain(2) == "└──────┘"


def test_block_handles_tiny_areas_and_truncates_title() -> None:
    one = Buffer.empty(Rect.new(0, 0, 1, 1))
    Block.default().bordered().title_("long").render(one.area, one)
    assert one.plain() == "┘"

    narrow = Buffer.empty(Rect.new(0, 0, 4, 2))
    Block.default().bordered().title_("long-title").render(narrow.area, narrow)
    assert narrow.row_plain(0) == "┌lo┐"


def test_adapter_region_conversion_trims_right_edges_without_mutating_buffer() -> None:
    buffer = Buffer.empty(Rect.new(10, 10, 5, 2))
    buffer.set_line(10, 10, Line.raw("ab"), max_width=5)
    buffer.set_line(10, 11, Line.raw("cd"), max_width=5)

    assert buffer_to_plain_text(buffer, Rect.new(10, 10, 3, 2), trim_end=True) == "ab\ncd"
    assert str(buffer_to_rich_text(buffer, Rect.new(10, 10, 3, 2), trim_end=True)) == "ab\ncd"
    assert buffer.plain_lines() == ["ab   ", "cd   "]


def test_crossterm_terminal_side_effects_are_explicitly_not_implemented() -> None:
    from pycodex.tui.ratatui_bridge.crossterm import disable_raw_mode, enable_raw_mode, execute

    for action in (enable_raw_mode, disable_raw_mode):
        try:
            action()
        except NotImplementedError as exc:
            assert "Textual" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("raw terminal side effect unexpectedly implemented")

    try:
        execute("clear")
    except NotImplementedError as exc:
        assert "Textual" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("terminal execute side effect unexpectedly implemented")
