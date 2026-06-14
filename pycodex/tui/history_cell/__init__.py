"""Transcript/history cell facade for Rust ``codex-tui::history_cell``.

This module owns the shared history-cell defaults from
``codex/codex-rs/tui/src/history_cell/mod.rs``. Concrete cell types live in the
child modules and remain separate module-scoped behavior contracts.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Iterable, Protocol, runtime_checkable

from .._porting import RustTuiModule, not_ported
from ..line_truncation import Line, Span, _display_width
from ..terminal_hyperlinks import HyperlinkLine, plain_hyperlink_lines, visible_lines

RUST_MODULE = RustTuiModule(crate="codex-tui", module="history_cell", source="codex/codex-rs/tui/src/history_cell/mod.rs")

RAW_DIFF_SUMMARY_WIDTH = 10_000
RAW_TOOL_OUTPUT_WIDTH = 10_000


class HistoryRenderMode(Enum):
    RICH = "rich"
    RAW = "raw"


@runtime_checkable
class HistoryCell(Protocol):
    def display_lines(self, width: int) -> list[Line]: ...
    def raw_lines(self) -> list[Line]: ...


def raw_lines_from_source(source: str) -> list[Line]:
    if source == "":
        return []
    parts = source.split("\n")
    if source.endswith("\n"):
        parts.pop()
    return [Line.from_text(part) for part in parts]


def plain_lines(lines: Iterable[Line]) -> list[Line]:
    return [Line.from_text("".join(span.content for span in line.spans)) for line in lines]


def display_lines(cell: Any, width: int) -> list[Line]:
    method = getattr(cell, "display_lines", None)
    if not callable(method):
        raise TypeError("history cell does not provide display_lines(width)")
    return list(method(width))


def raw_lines(cell: Any) -> list[Line]:
    method = getattr(cell, "raw_lines", None)
    if not callable(method):
        raise TypeError("history cell does not provide raw_lines()")
    return list(method())


def display_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    method = getattr(cell, "display_hyperlink_lines", None)
    if callable(method):
        return list(method(width))
    return plain_hyperlink_lines(display_lines(cell, width))


def display_lines_for_mode(cell: Any, width: int, mode: HistoryRenderMode) -> list[Line]:
    if mode is HistoryRenderMode.RICH:
        return visible_lines(display_hyperlink_lines(cell, width))
    if mode is HistoryRenderMode.RAW:
        return raw_lines(cell)
    raise ValueError(f"unsupported history render mode: {mode!r}")


def display_hyperlink_lines_for_mode(cell: Any, width: int, mode: HistoryRenderMode) -> list[HyperlinkLine]:
    if mode is HistoryRenderMode.RICH:
        return display_hyperlink_lines(cell, width)
    if mode is HistoryRenderMode.RAW:
        return plain_hyperlink_lines(raw_lines(cell))
    raise ValueError(f"unsupported history render mode: {mode!r}")


def desired_height(cell: Any, width: int) -> int:
    return desired_height_for_mode(cell, width, HistoryRenderMode.RICH)


def desired_height_for_mode(cell: Any, width: int, mode: HistoryRenderMode) -> int:
    return _wrapped_height(display_lines_for_mode(cell, width, mode), width)


def transcript_lines(cell: Any, width: int) -> list[Line]:
    method = getattr(cell, "transcript_lines", None)
    if callable(method):
        return list(method(width))
    return display_lines(cell, width)


def transcript_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
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


def transcript_animation_tick(cell: Any) -> int | None:
    method = getattr(cell, "transcript_animation_tick", None)
    return method() if callable(method) else None


def render(cell: Any, area: Any, buf: Any) -> Any:
    return not_ported(RUST_MODULE, "Renderable for Box<dyn HistoryCell>")


def _wrapped_height(lines: Iterable[Line], width: int) -> int:
    width = max(0, int(width))
    if width == 0:
        return 0
    total = 0
    for line in lines:
        text_width = _display_width(_line_text(line))
        total += max(1, (text_width + width - 1) // width)
    return total


def _line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


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


__all__ = [name for name in globals() if not name.startswith("_")]
