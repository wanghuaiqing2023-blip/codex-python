"""Rust ratatui semantic bridge for pycodex TUI."""

from __future__ import annotations

from .backend import Backend, CrosstermBackend, Frame, Terminal, TestBackend, WindowSize
from .buffer import Buffer, Cell
from .crossterm import Attribute, ClearType, SetAttribute, SetBackgroundColor, SetForegroundColor
from .layout import Alignment, Constraint, Direction, Layout, Margin, Offset, Position, Rect, Size
from .renderable import Renderable
from .style import Color, Modifier, Rgb, Style
from .text import Line, Span, Text
from .textual_adapter import (
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

__all__ = [
    "Alignment",
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
    "Frame",
    "Layout",
    "Line",
    "Margin",
    "Modifier",
    "Offset",
    "Paragraph",
    "Position",
    "Rect",
    "Renderable",
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
    "buffer_to_plain_text",
    "buffer_to_rich_text",
    "cell_to_rich_text",
    "line_to_rich_text",
    "render_ref",
    "render_stateful_ref",
    "render_to_buffer",
    "render_to_rich_text",
    "span_to_rich_text",
    "text_to_rich_text",
]
