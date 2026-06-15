"""Transcript/history cell facade for Rust ``codex-tui::history_cell``.

This module owns the shared history-cell defaults from
``codex/codex-rs/tui/src/history_cell/mod.rs``. Concrete cell types live in the
child modules and remain separate module-scoped behavior contracts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple

from .._porting import RustTuiModule
from ..line_truncation import Line, Span, _display_width
from ..terminal_hyperlinks import HyperlinkLine, mark_buffer_hyperlinks, plain_hyperlink_lines, visible_lines

RUST_MODULE = RustTuiModule(crate="codex-tui", module="history_cell", source="codex/codex-rs/tui/src/history_cell/mod.rs", status="complete")

RAW_DIFF_SUMMARY_WIDTH = 10_000
RAW_TOOL_OUTPUT_WIDTH = 10_000


class HistoryRenderMode(Enum):
    RICH = "rich"
    RAW = "raw"


def raw_lines_from_source(source: str) -> List[Line]:
    if source == "":
        return []
    parts = source.split("\n")
    if source.endswith("\n"):
        parts.pop()
    return [Line.from_text(part) for part in parts]


def plain_lines(lines: Iterable[Line]) -> List[Line]:
    return [Line.from_text("".join(span.content for span in line.spans)) for line in lines]


def display_lines(cell: Any, width: int) -> List[Line]:
    method = getattr(cell, "display_lines", None)
    if not callable(method):
        raise TypeError("history cell does not provide display_lines(width)")
    return list(method(width))


def raw_lines(cell: Any) -> List[Line]:
    method = getattr(cell, "raw_lines", None)
    if not callable(method):
        raise TypeError("history cell does not provide raw_lines()")
    return list(method())


def display_hyperlink_lines(cell: Any, width: int) -> List[HyperlinkLine]:
    method = getattr(cell, "display_hyperlink_lines", None)
    if callable(method):
        return list(method(width))
    return plain_hyperlink_lines(display_lines(cell, width))


def display_lines_for_mode(cell: Any, width: int, mode: HistoryRenderMode) -> List[Line]:
    if mode is HistoryRenderMode.RICH:
        return visible_lines(_facade_display_hyperlink_lines(cell, width))
    if mode is HistoryRenderMode.RAW:
        return raw_lines(cell)
    raise ValueError(f"unsupported history render mode: {mode!r}")


def display_hyperlink_lines_for_mode(cell: Any, width: int, mode: HistoryRenderMode) -> List[HyperlinkLine]:
    if mode is HistoryRenderMode.RICH:
        return _facade_display_hyperlink_lines(cell, width)
    if mode is HistoryRenderMode.RAW:
        return plain_hyperlink_lines(raw_lines(cell))
    raise ValueError(f"unsupported history render mode: {mode!r}")


def desired_height(cell: Any, width: int) -> int:
    return desired_height_for_mode(cell, width, HistoryRenderMode.RICH)


def desired_height_for_mode(cell: Any, width: int, mode: HistoryRenderMode) -> int:
    return _wrapped_height(display_lines_for_mode(cell, width, mode), width)


def transcript_lines(cell: Any, width: int) -> List[Line]:
    method = getattr(cell, "transcript_lines", None)
    if callable(method):
        return list(method(width))
    return display_lines(cell, width)


def transcript_hyperlink_lines(cell: Any, width: int) -> List[HyperlinkLine]:
    method = getattr(cell, "transcript_hyperlink_lines", None)
    if callable(method):
        return list(method(width))
    return plain_hyperlink_lines(transcript_lines(cell, width))


def desired_transcript_height(cell: Any, width: int) -> int:
    lines = visible_lines(transcript_hyperlink_lines(cell, width))
    if len(lines) == 1 and all(span.content.isspace() for span in lines[0].spans):
        return 1
    return _wrapped_height(lines, width)


def is_stream_continuation(cell: Any) -> bool:
    method = getattr(cell, "is_stream_continuation", None)
    return bool(method()) if callable(method) else False


def transcript_animation_tick(cell: Any) -> Optional[int]:
    method = getattr(cell, "transcript_animation_tick", None)
    return method() if callable(method) else None


_facade_display_hyperlink_lines = display_hyperlink_lines


def render(cell: Any, area: Any, buf: Any) -> Any:
    """Render a history cell into a semantic buffer.

    Mirrors Rust's ``Renderable for Box<dyn HistoryCell>`` at the semantic
    boundary: compute rich hyperlink lines, clear the target area, bottom-scroll
    when rendered content is taller than the area, write visible text cells, and
    then apply terminal hyperlink metadata to the visible cells.
    """
    rect = _coerce_rect(area)
    hyperlink_lines = _facade_display_hyperlink_lines(cell, rect[2])
    rendered = _wrap_visible_lines(visible_lines(hyperlink_lines), rect[2])
    overflow = max(0, len(rendered) - rect[3]) if rect[3] else 0
    _clear_area(buf, rect)
    for row_offset, text in enumerate(rendered[overflow : overflow + rect[3]]):
        y = rect[1] + row_offset
        for column, ch in enumerate(_take_width(text, rect[2])):
            x = rect[0] + column
            _set_cell_symbol(_buffer_cell(buf, x, y), ch)
    mark_buffer_hyperlinks(buf, _semantic_rect(area, rect), hyperlink_lines, overflow)
    return buf


def _wrapped_height(lines: Iterable[Line], width: int) -> int:
    width = max(0, int(width))
    if width == 0:
        return 0
    return len(_wrap_visible_lines(lines, width))


def _wrap_visible_lines(lines: Iterable[Line], width: int) -> List[str]:
    width = max(0, int(width))
    if width == 0:
        return []
    out = []
    for line in lines:
        text = _line_text(line)
        if text == "":
            out.append("")
            continue
        current = ""
        current_width = 0
        for ch in text:
            ch_width = _display_width(ch)
            if current and current_width + ch_width > width:
                out.append(current)
                current = ""
                current_width = 0
            current += ch
            current_width += ch_width
        out.append(current)
    return out


def _take_width(text: str, width: int) -> str:
    out = []
    used = 0
    for ch in text:
        ch_width = _display_width(ch)
        if used + ch_width > width:
            break
        out.append(ch)
        used += ch_width
    return "".join(out)


def _coerce_rect(area: Any) -> Tuple[int, int, int, int]:
    if isinstance(area, tuple):
        return (int(area[0]), int(area[1]), int(area[2]), int(area[3]))
    return (
        int(getattr(area, "x")),
        int(getattr(area, "y")),
        int(getattr(area, "width")),
        int(getattr(area, "height")),
    )


def _semantic_rect(area: Any, rect: Tuple[int, int, int, int]) -> Any:
    if hasattr(area, "positions"):
        return area
    from ..terminal_hyperlinks import SemanticRect

    return SemanticRect(rect[0], rect[1], rect[2], rect[3])


def _clear_area(buf: Any, rect: Tuple[int, int, int, int]) -> None:
    x0, y0, width, height = rect
    for y in range(y0, y0 + height):
        for x in range(x0, x0 + width):
            _set_cell_symbol(_buffer_cell(buf, x, y), " ")


def _buffer_cell(buf: Any, column: int, row: int) -> Any:
    if hasattr(buf, "cells") and (column, row) not in buf.cells:
        try:
            from ..terminal_hyperlinks import SemanticCell

            buf.cells[(column, row)] = SemanticCell()
        except Exception:
            pass
    cell_method = getattr(buf, "cell", None)
    if callable(cell_method):
        return cell_method(column, row)
    if hasattr(buf, "cells"):
        return buf.cells[(column, row)]
    return buf[(column, row)]


def _set_cell_symbol(cell: Any, symbol: str) -> None:
    setter = getattr(cell, "set_symbol", None)
    if callable(setter):
        setter(symbol)
    else:
        setattr(cell, "symbol", symbol)


def _line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


_facade_exports = {
    "HistoryRenderMode": HistoryRenderMode,
    "raw_lines_from_source": raw_lines_from_source,
    "plain_lines": plain_lines,
    "display_lines": display_lines,
    "raw_lines": raw_lines,
    "display_hyperlink_lines": display_hyperlink_lines,
    "display_lines_for_mode": display_lines_for_mode,
    "display_hyperlink_lines_for_mode": display_hyperlink_lines_for_mode,
    "desired_height": desired_height,
    "desired_height_for_mode": desired_height_for_mode,
    "transcript_lines": transcript_lines,
    "transcript_hyperlink_lines": transcript_hyperlink_lines,
    "desired_transcript_height": desired_transcript_height,
    "is_stream_continuation": is_stream_continuation,
    "transcript_animation_tick": transcript_animation_tick,
    "render": render,
}


try:
    from .approvals import *  # noqa: F401,F403
    from .base import *  # noqa: F401,F403
    from .exec import *  # noqa: F401,F403
    from .hook_cell import HookCell, new_active_hook_cell, new_completed_hook_cell  # noqa: F401
    from .mcp import *  # noqa: F401,F403
    from .messages import *  # noqa: F401,F403
    from .notices import *  # noqa: F401,F403
    from .patches import *  # noqa: F401,F403
    from .plans import *  # noqa: F401,F403
    from .request_user_input import *  # noqa: F401,F403
    from .search import *  # noqa: F401,F403
    from .separators import *  # noqa: F401,F403
    from .session import *  # noqa: F401,F403
except Exception:
    # Child modules are separate porting contracts; importing this facade should
    # not hide an explicit child-module dependency failure in direct imports.
    pass

globals().update(_facade_exports)


__all__ = [name for name in globals() if not name.startswith("_")]
