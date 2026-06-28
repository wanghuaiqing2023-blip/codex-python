"""Bridge-backed terminal projection helpers for Rust-shaped TUI tests.

Rust ``codex-tui`` renders user-facing cells through Ratatui widgets into a
terminal backend.  Python's product TTY surface is Textual-backed now, but a
few porting tests still need a small semantic projection boundary for
cell-addressable rows before bytes reach a ``TextIO`` stream.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from os import terminal_size
from typing import TextIO

from ._porting import RustTuiModule
from .ratatui_bridge import Paragraph, Rect, Text, render_to_buffer

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="terminal_projection",
    source="codex/codex-rs/tui/src/tui.rs",
    status="partial",
)


def terminal_width(default: int = 100) -> int:
    return max(shutil.get_terminal_size((default, 30)).columns, 1)


def terminal_size_default() -> terminal_size:
    return shutil.get_terminal_size((100, 30))


def render_plain_lines(lines: Iterable[object], *, width: int | None = None) -> list[str]:
    """Render plain rows through the Ratatui bridge buffer.

    The input is already a semantic TUI projection, so this helper does not add
    wrapping or styling.  It clips to the current terminal width using the same
    cell-addressable buffer model that the Ratatui bridge exposes to ported
    widgets.
    """

    rows = [str(line) for line in lines]
    if not rows:
        return []
    target_width = max(int(width if width is not None else terminal_width()), 1)
    area = Rect.new(0, 0, target_width, len(rows))
    buffer = render_to_buffer(Paragraph(Text.from_lines(rows)), area)
    return [line.rstrip() for line in buffer.plain_lines()]


def render_plain_segment(text: object, *, width: int | None = None) -> str:
    """Render one streaming text segment through the bridge without newline IO."""

    value = str(text)
    if not value:
        return ""
    max_width = max(int(width if width is not None else terminal_width()), 1)
    target_width = max(1, min(len(value), max_width))
    area = Rect.new(0, 0, target_width, 1)
    buffer = render_to_buffer(Paragraph.raw(value), area)
    return buffer.row_plain(0)


def write_plain_lines(
    writer: TextIO,
    lines: Iterable[object],
    *,
    width: int | None = None,
    prefix: str = "",
    suffix: str = "",
) -> list[str]:
    rendered = render_plain_lines(lines, width=width)
    for line in rendered:
        writer.write(f"{prefix}{line}{suffix}\n")
    return rendered


def write_styled_lines(
    writer: TextIO,
    lines: Iterable[object],
    *,
    width: int | None = None,
    prefix: str = "",
    suffix: str = "",
) -> list[str]:
    """Render plain content through the bridge, then apply edge styling."""

    return write_plain_lines(writer, lines, width=width, prefix=prefix, suffix=suffix)


__all__ = [
    "RUST_MODULE",
    "render_plain_lines",
    "render_plain_segment",
    "terminal_size_default",
    "terminal_width",
    "write_plain_lines",
    "write_styled_lines",
]
