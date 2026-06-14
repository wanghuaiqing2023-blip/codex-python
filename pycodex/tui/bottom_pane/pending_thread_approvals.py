"""Pending thread approval preview.

Port of Rust ``codex-tui::bottom_pane::pending_thread_approvals`` using
semantic rendered rows instead of ratatui buffers.
"""

from __future__ import annotations

import textwrap
from dataclasses import dataclass, field
from typing import MutableSequence

from .._porting import RustTuiModule
from ..ratatui_bridge import Rect

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::pending_thread_approvals",
    source="codex/codex-rs/tui/src/bottom_pane/pending_thread_approvals.rs",
)


@dataclass(frozen=True)
class RenderedLine:
    text: str
    style: str = "plain"


@dataclass
class PendingThreadApprovals:
    _threads: list[str] = field(default_factory=list)

    @classmethod
    def new(cls) -> "PendingThreadApprovals":
        return cls()

    def set_threads(self, threads: list[str]) -> bool:
        if self._threads == threads:
            return False
        self._threads = list(threads)
        return True

    def is_empty(self) -> bool:
        return not self._threads

    def threads(self) -> tuple[str, ...]:
        return tuple(self._threads)

    def as_renderable(self, width: int) -> list[RenderedLine]:
        if not self._threads or width < 4:
            return []

        lines: list[RenderedLine] = []
        for thread in self._threads[:3]:
            lines.extend(RenderedLine(text, "warning") for text in _wrap_thread(thread, width))

        if len(self._threads) > 3:
            lines.append(RenderedLine("    ...", "dim+italic"))

        lines.append(RenderedLine("    /agent to switch threads", "dim"))
        return lines

    def render(self, area: Rect, buf: MutableSequence[RenderedLine]) -> None:
        if area.is_empty():
            return
        buf.extend(self.as_renderable(area.width)[: area.height])

    def desired_height(self, width: int) -> int:
        return len(self.as_renderable(width))


def render(widget: PendingThreadApprovals, area: Rect, buf: MutableSequence[RenderedLine]) -> None:
    widget.render(area, buf)


def desired_height(widget: PendingThreadApprovals, width: int) -> int:
    return widget.desired_height(width)


def snapshot_rows(widget: PendingThreadApprovals, width: int) -> str:
    """Return a Rust-test-like visible-row snapshot padded to ``width``."""

    rows = [line.text[:width].ljust(width) for line in widget.as_renderable(width)]
    return "\n".join(rows)


def _wrap_thread(thread: str, width: int) -> list[str]:
    message = f"Approval needed in {thread}"
    return textwrap.wrap(
        message,
        width=max(width, 1),
        initial_indent="  ! ",
        subsequent_indent="    ",
        replace_whitespace=False,
        drop_whitespace=False,
    ) or ["  ! "]


__all__ = [
    "PendingThreadApprovals",
    "RUST_MODULE",
    "Rect",
    "RenderedLine",
    "desired_height",
    "render",
    "snapshot_rows",
]
