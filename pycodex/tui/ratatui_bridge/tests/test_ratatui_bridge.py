from __future__ import annotations

import io

from pycodex.tui import rich_compat
from pycodex.tui import ratatui_bridge
from pycodex.tui.ratatui_bridge import (
    Alignment,
    AnsiBackend,
    Backend,
    Block,
    BorderType,
    Borders,
    Buffer,
    Cell,
    Clear,
    Color,
    Constraint,
    Direction,
    DrawCommand,
    Frame,
    Layout,
    Line,
    Margin,
    Modifier,
    Paragraph,
    Position,
    Rect,
    Renderable,
    Size,
    Span,
    Style,
    Terminal,
    FrameBufferState,
    TestBackend as BridgeTestBackend,
    Text,
    Widget,
    Wrap,
    ansi_style_sequence,
    buffer_to_plain_text,
    buffer_to_rich_text,
    draw_buffer_to_ansi,
    diff_buffers,
    full_redraw_commands,
    render_ref,
    render_to_buffer,
    render_to_rich_text,
    requires_full_redraw,
)


def test_ratatui_bridge_module_marker_is_complete_for_python_semantic_bridge() -> None:
    assert ratatui_bridge.RUST_MODULE.module == "ratatui_bridge"
    assert ratatui_bridge.RUST_MODULE.status == "complete"


def test_minimal_ratatui_core_api_is_exported() -> None:
    # Rust owner: ratatui public concepts used by codex-tui.  The Python
    # bridge must keep these minimal frame/buffer/backend concepts available
    # as one shared core for terminal product adapters.
    expected = {
        "Backend",
        "Buffer",
        "Cell",
        "Frame",
        "Rect",
        "Size",
        "Style",
        "Terminal",
        "TestBackend",
        "Widget",
        "diff_buffers",
        "requires_full_redraw",
    }

    assert expected <= set(ratatui_bridge.__all__)
    assert Cell("x").symbol == "x"
    assert Buffer.empty(Rect.from_size(Size.new(2, 1))).plain() == "  "
    assert callable(getattr(Widget, "render", None))
    assert Frame(Rect.new(0, 0, 1, 1), Buffer.empty(Rect.new(0, 0, 1, 1))).size() == Rect.new(0, 0, 1, 1)


def test_backend_protocol_exposes_draw_lifecycle() -> None:
    # Rust owner: ratatui::backend::Backend is the drawing boundary consumed by
    # ratatui::Terminal::draw.  The Python bridge keeps the same lifecycle
    # explicit so product adapters do not invent ad-hoc redraw paths.
    assert callable(getattr(Backend, "draw", None))
    assert callable(getattr(Backend, "flush", None))


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


def test_rich_conversion_methods_exist_and_use_rich_compat_boundary() -> None:
    span = Span.styled("hello", Style().with_fg("red").bold())
    rich_text = span.to_rich_text()

    assert str(rich_text) == "hello"
    assert isinstance(rich_text, rich_compat.Text)


def test_line_and_text_conversion_preserve_plain_content_with_vendored_rich_text() -> None:
    line = Line.from_spans([Span.raw("hi"), Span.styled("!", Style().with_fg(Color.rgb(1, 2, 3)).bold())])
    text = Text.from_lines([line, "there"])

    assert isinstance(line.to_rich_text(), rich_compat.Text)
    assert isinstance(text.to_rich_text(), rich_compat.Text)
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


def test_rich_adapter_converts_buffer_and_renderables_without_terminal_io() -> None:
    paragraph = Paragraph(Text.from_lines(["hello", Line.from_spans([Span.styled("ok", Style().bold())])]))
    buffer = render_to_buffer(paragraph, Rect.new(0, 0, 5, 2))

    assert buffer_to_plain_text(buffer, trim_end=True) == "hello\nok"
    rich = buffer_to_rich_text(buffer, trim_end=True)
    assert isinstance(rich, rich_compat.Text)
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


def test_terminal_draw_applies_frame_cursor_position_through_backend() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::try_draw takes the
    # cursor position from the completed Frame and applies it through the
    # backend after drawing the frame buffer.
    backend = BridgeTestBackend.new(6, 2)
    terminal = Terminal.new(backend)

    terminal.draw(lambda frame: frame.set_cursor_position((3, 1)))

    assert terminal.last_cursor_position == Position.new(3, 1)
    assert backend.cursor_position == Position.new(3, 1)
    assert backend.flush_count == 1


def test_terminal_draw_requires_backend_draw_boundary() -> None:
    # Rust owner: ratatui::Terminal draws through ratatui::backend::Backend.
    # Python must not preserve an adapter-local fallback that mutates a backend
    # buffer directly and bypasses the shared draw lifecycle.
    class BufferOnlyBackend:
        def __init__(self) -> None:
            self._buffer = Buffer.empty(Rect.new(0, 0, 2, 1))

        def size(self) -> Size:
            return Size.new(2, 1)

        def window_size(self):
            return None

        def buffer(self) -> Buffer:
            return self._buffer

        def flush(self) -> None:
            pass

    terminal = Terminal.new(BufferOnlyBackend())  # type: ignore[arg-type]

    try:
        terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("x"), frame.area))
    except AttributeError as exc:
        assert "draw" in str(exc)
    else:
        raise AssertionError("Terminal.draw must require backend.draw")


def test_bridge_buffer_clone_reset_and_resize_support_terminal_lifecycle() -> None:
    buffer = Buffer.empty(Rect.new(0, 0, 4, 1))
    buffer.set_line(0, 0, Line.raw("old"), max_width=4)

    cloned = buffer.clone()
    buffer.reset()
    buffer.resize(Rect.new(0, 0, 2, 2))

    assert cloned.plain() == "old "
    assert buffer.plain_lines() == ["  ", "  "]


def test_bridge_diff_buffers_emits_changed_cells_and_row_clear() -> None:
    previous = Buffer.empty(Rect.new(0, 0, 6, 1))
    current = Buffer.empty(Rect.new(0, 0, 6, 1))
    previous.set_line(0, 0, Line.raw("abcdef"), max_width=6)
    current.set_line(0, 0, Line.raw("ab"), max_width=6)

    commands = diff_buffers(previous, current)

    assert any(command.kind == "clear_to_end" and command.x == 2 and command.y == 0 for command in commands)
    assert not any(command.kind == "put" and command.x == 0 for command in commands)


def test_bridge_diff_buffers_does_not_clear_full_width_nonblank_row() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::flush computes frame
    # diffs through ratatui Buffer cells. The Python bridge owns this core so
    # custom_terminal adapters do not keep their own buffer-diff test model.
    previous = Buffer.empty(Rect.new(0, 0, 2, 1))
    current = Buffer.empty(Rect.new(0, 0, 2, 1))
    current.set_line(0, 0, Line.raw("AB"), max_width=2)

    commands = diff_buffers(previous, current)

    assert DrawCommand.put(0, 0, Cell("A")) in commands
    assert DrawCommand.put(1, 0, Cell("B")) in commands
    assert not any(command.kind == "clear_to_end" for command in commands)


def test_bridge_diff_buffers_clear_to_end_starts_after_wide_char() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::flush. Wide symbols
    # occupy ratatui cell columns, so clearing after shortened CJK text must
    # start after the remaining wide cell.
    previous = Buffer.empty(Rect.new(0, 0, 10, 1))
    current = Buffer.empty(Rect.new(0, 0, 10, 1))
    previous.set_line(0, 0, Line.raw("\u4e2d\u6587"), max_width=10)
    current.set_line(0, 0, Line.raw("\u4e2d"), max_width=10)

    commands = diff_buffers(previous, current)

    assert any(command.kind == "clear_to_end" and command.x == 2 and command.y == 0 for command in commands)


def test_bridge_full_redraw_commands_preserve_minimum_row_widths() -> None:
    # Rust owner: codex-tui::custom_terminal owns full frame redraw when the
    # viewport changes.  Python's hybrid terminal adapter passes row-width
    # hints for visible prompt spacing, but command generation remains here.
    buffer = Buffer.empty(Rect.new(0, 0, 6, 2))
    buffer.set_line(0, 0, Line.raw("› "), max_width=6)
    buffer.set_line(0, 1, Line.raw("x"), max_width=6)

    commands = full_redraw_commands(buffer, minimum_row_widths={0: 2})

    assert DrawCommand.put(0, 0, Cell("›")) in commands
    assert DrawCommand.put(1, 0, Cell(" ")) in commands
    assert DrawCommand.clear_to_end(2, 0) in commands
    assert DrawCommand.put(0, 1, Cell("x")) in commands
    assert DrawCommand.clear_to_end(1, 1) in commands


def test_bridge_buffer_places_wide_chars_in_terminal_cells() -> None:
    # Rust owner: ratatui::buffer::Buffer stores wide symbols in terminal cell
    # coordinates and marks trailing cells as skipped. The Python bridge must
    # do the same or later CJK characters are skipped by ANSI diff rendering.
    buffer = Buffer.empty(Rect.new(0, 0, 8, 1))
    buffer.set_line(0, 0, Line.raw("你好"), max_width=8)

    assert buffer.cell(0, 0) == Cell("你")
    assert buffer.cell(1, 0).skip is True
    assert buffer.cell(2, 0) == Cell("好")
    assert buffer.cell(3, 0).skip is True
    assert buffer.to_plain_text(trim_end=True) == "你好"

    commands = full_redraw_commands(buffer)
    assert DrawCommand.put(0, 0, Cell("你")) in commands
    assert DrawCommand.put(2, 0, Cell("好")) in commands
    assert not any(command.kind == "put" and command.x in {1, 3} for command in commands)
    assert DrawCommand.clear_to_end(4, 0) in commands


def test_draw_buffer_to_ansi_positions_wide_chars_by_terminal_columns() -> None:
    # Rust owner: codex-tui::custom_terminal delegates ratatui cell positions to
    # the backend. Wide chars must be emitted at their terminal columns, not at
    # Python string indexes.
    buffer = Buffer.empty(Rect.new(0, 0, 8, 1))
    buffer.set_line(0, 0, Line.raw("你好"), max_width=8)
    writer = io.StringIO()

    draw_buffer_to_ansi(writer, buffer)

    assert "\x1b[1;1H你" in writer.getvalue()
    assert "\x1b[1;3H好" in writer.getvalue()


def test_frame_buffer_state_clones_and_invalidates_previous_buffer() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal stores a previous
    # buffer and resets it after external clears so the next draw is full.
    state = FrameBufferState()
    buffer = Buffer.empty(Rect.new(0, 0, 4, 1))
    buffer.set_line(0, 0, Line.raw("old"), max_width=4)

    state.update(buffer)
    buffer.set_line(0, 0, Line.raw("new"), max_width=4)

    assert state.previous is not None
    assert state.previous.plain() == "old "

    state.reset()

    assert state.previous is None


def test_requires_full_redraw_centralizes_previous_buffer_compatibility() -> None:
    # Rust owner: codex-tui::custom_terminal owns the previous/current buffer
    # compatibility check that decides whether a draw may use a diff.
    current = Buffer.empty(Rect.new(0, 0, 4, 1))
    same_area_previous = Buffer.empty(Rect.new(0, 0, 4, 1))
    resized_previous = Buffer.empty(Rect.new(0, 0, 5, 1))

    assert requires_full_redraw(None, current) is True
    assert requires_full_redraw(resized_previous, current) is True
    assert requires_full_redraw(same_area_previous, current) is False


def test_draw_buffer_to_ansi_uses_full_redraw_then_same_area_diff() -> None:
    # Rust owner: codex-tui::custom_terminal selects full redraw when no
    # previous buffer exists and same-area diffs when a previous frame exists.
    previous = Buffer.empty(Rect.new(0, 0, 6, 1))
    previous.set_line(0, 0, Line.raw("abcdef"), max_width=6)
    current = Buffer.empty(Rect.new(0, 0, 6, 1))
    current.set_line(0, 0, Line.raw("ab"), max_width=6)

    full_writer = io.StringIO()
    draw_buffer_to_ansi(full_writer, current, minimum_row_widths={0: 3})

    diff_writer = io.StringIO()
    draw_buffer_to_ansi(diff_writer, current, previous=previous)

    assert "\x1b[1;1Hab " in full_writer.getvalue()
    assert "\x1b[1;4H\x1b[0K" in full_writer.getvalue()
    assert "\x1b[1;1Ha" not in diff_writer.getvalue()
    assert diff_writer.getvalue() == "\x1b[1;3H\x1b[0K"


def test_draw_buffer_to_ansi_can_handoff_cursor_position() -> None:
    # Rust owner: codex-tui::custom_terminal moves the backend cursor from the
    # completed frame after drawing the buffer.  Python hybrid adapters pass
    # that cursor through this bridge helper instead of moving it locally.
    current = Buffer.empty(Rect.new(0, 0, 6, 2))
    current.set_line(0, 0, Line.raw("hi"), max_width=6)
    writer = io.StringIO()

    draw_buffer_to_ansi(writer, current, cursor_position=Position.new(3, 1))

    assert writer.getvalue().endswith("\x1b[2;4H")


def test_bridge_terminal_draw_uses_previous_current_buffer_diff() -> None:
    backend = BridgeTestBackend.new(8, 1)
    terminal = Terminal.new(backend)

    terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("hello"), frame.area))
    first_draw_count = len(backend.drawn_commands)
    terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("hello"), frame.area))
    second_draw_count = len(backend.drawn_commands)
    terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("hi"), frame.area))

    assert first_draw_count > 0
    assert second_draw_count == first_draw_count
    assert len(backend.drawn_commands) > second_draw_count
    assert backend.buffer().plain() == "hi      "


def test_bridge_terminal_resize_rebuilds_viewport_and_backend_buffer() -> None:
    backend = BridgeTestBackend.new(4, 1)
    terminal = Terminal.new(backend)

    terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("abcd"), frame.area))
    backend.resize(3, 2)
    terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("xy\nz"), frame.area))

    assert terminal.viewport_area == Rect.new(0, 0, 3, 2)
    assert backend.buffer().plain_lines() == ["xy ", "z  "]


def test_ansi_backend_draw_writes_diff_commands_and_updates_semantic_buffer() -> None:
    # Rust owner: codex-tui::custom_terminal owns backend draw side effects from
    # current/previous buffer diffs.  The Python bridge keeps this as a tiny
    # ANSI primitive so product adapters can share the same draw lifecycle.
    writer = io.StringIO()
    backend = AnsiBackend.new(writer, 6, 2)
    selected = Style.default().with_fg(Color.LightBlue).bold()

    backend.draw(
        (
            DrawCommand.put(1, 0, Cell("A", selected)),
            DrawCommand.clear_to_end(2, 0),
        )
    )
    backend.flush()

    assert writer.getvalue() == "\x1b[1;2H\x1b[94;1mA\x1b[0m\x1b[1;3H\x1b[0K"
    assert backend.buffer().row_plain(0) == " A    "
    assert backend.flush_count == 1


def test_terminal_draw_can_target_ansi_backend_through_bridge_lifecycle() -> None:
    # Rust owner: codex-tui::custom_terminal Terminal::draw drives a frame,
    # computes a diff, draws it through the backend, and flushes once.
    writer = io.StringIO()
    backend = AnsiBackend.new(writer, 5, 1)
    terminal = Terminal.new(backend)

    terminal.draw(lambda frame: frame.render_widget(Paragraph.raw("hi"), frame.area))

    output = writer.getvalue()
    assert "\x1b[1;1Hhi" in output
    assert "\x1b[1;2Hi" not in output
    assert "\x1b[1;3H\x1b[0K" in output
    assert backend.buffer().plain() == "hi   "
    assert backend.flush_count == 1


def test_terminal_draw_writes_ansi_cursor_position_after_frame_draw() -> None:
    # Rust owner: codex-tui::custom_terminal::Terminal::try_draw draws the
    # frame, then moves the backend cursor using the cursor selected by Frame.
    writer = io.StringIO()
    backend = AnsiBackend.new(writer, 5, 2)
    terminal = Terminal.new(backend)

    def draw(frame: Frame) -> None:
        frame.render_widget(Paragraph.raw("hi"), Rect.new(0, 0, 5, 1))
        frame.set_cursor_position(Position.new(2, 1))

    terminal.draw(draw)

    output = writer.getvalue()
    assert "\x1b[1;1Hhi" in output
    assert output.endswith("\x1b[2;3H")
    assert backend.cursor_position == Position.new(2, 1)
    assert backend.flush_count == 1


def test_ansi_style_sequence_maps_bridge_style_to_sgr_codes() -> None:
    # Rust owner: codex-tui::custom_terminal applies cell style while drawing
    # the buffer into a terminal backend.
    style = Style.default().with_fg(Color.rgb(1, 2, 3)).with_bg(Color.Indexed(4)).underlined()

    assert ansi_style_sequence(style) == "\x1b[38;2;1;2;3;48;5;4;4m"


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
            assert "terminal runtime" in str(exc)
        else:  # pragma: no cover - defensive assertion
            raise AssertionError("raw terminal side effect unexpectedly implemented")

    try:
        execute("clear")
    except NotImplementedError as exc:
        assert "terminal runtime" in str(exc)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("terminal execute side effect unexpectedly implemented")
