"""Rust ratatui semantic bridge for pycodex TUI."""

from __future__ import annotations

from .._porting import RustTuiModule
from .backend import (
    AnsiBackend,
    Backend,
    CrosstermBackend,
    DrawCommand,
    Frame,
    FrameBufferState,
    Terminal,
    TestBackend,
    WindowSize,
    ansi_style_sequence,
    draw_buffer_to_ansi,
    diff_buffers,
    full_redraw_commands,
    requires_full_redraw,
)
from .buffer import Buffer, Cell
from .crossterm import Attribute, ClearType, SetAttribute, SetBackgroundColor, SetForegroundColor
from .layout import Alignment, Constraint, Direction, Layout, Margin, Offset, Position, Rect, Size
from .renderable import Renderable
from .style import Color, Modifier, Rgb, Style
from .text import Line, Span, Text
from .rich_adapter import (
    buffer_to_plain_text,
    buffer_to_rich_text,
    cell_to_rich_text,
    line_to_rich_text,
    render_to_buffer,
    render_to_rich_text,
    span_to_rich_text,
    text_to_rich_text,
)
from .widgets import (
    Block,
    BorderType,
    Borders,
    Clear,
    Paragraph,
    StatefulWidgetRef,
    Widget,
    WidgetRef,
    Wrap,
    render_ref,
    render_stateful_ref,
)

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ratatui_bridge",
    source="pycodex/tui/ratatui_bridge",
    status="complete",
)

__all__ = [
    "Alignment",
    "AnsiBackend",
    "Attribute",
    "Backend",
    "Block",
    "BorderType",
    "Borders",
    "Buffer",
    "Cell",
    "Clear",
    "ClearType",
    "Color",
    "Constraint",
    "CrosstermBackend",
    "Direction",
    "DrawCommand",
    "Frame",
    "FrameBufferState",
    "Layout",
    "Line",
    "Margin",
    "Modifier",
    "Offset",
    "Paragraph",
    "Position",
    "Rect",
    "Renderable",
    "RUST_MODULE",
    "Rgb",
    "SetAttribute",
    "SetBackgroundColor",
    "SetForegroundColor",
    "Size",
    "Span",
    "StatefulWidgetRef",
    "Style",
    "Terminal",
    "TestBackend",
    "Text",
    "Widget",
    "WidgetRef",
    "WindowSize",
    "Wrap",
    "ansi_style_sequence",
    "buffer_to_plain_text",
    "buffer_to_rich_text",
    "cell_to_rich_text",
    "draw_buffer_to_ansi",
    "diff_buffers",
    "full_redraw_commands",
    "line_to_rich_text",
    "render_ref",
    "render_stateful_ref",
    "render_to_buffer",
    "render_to_rich_text",
    "requires_full_redraw",
    "span_to_rich_text",
    "text_to_rich_text",
]
