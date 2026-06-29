"""Unified-exec background session footer.

Python port of Rust ``codex-tui::bottom_pane::unified_exec_footer``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, List, Optional

from .._porting import RustTuiModule
from ..live_wrap import take_prefix_by_width

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::unified_exec_footer",
    source="codex/codex-rs/tui/src/bottom_pane/unified_exec_footer.rs",
    status="complete",
)


@dataclass(frozen=True)
class FooterLine:
    """Semantic stand-in for a dim ratatui ``Line``."""

    text: str
    dim: bool = True


@dataclass
class UnifiedExecFooter:
    """Tracks active unified-exec processes and renders a compact summary."""

    processes: List[str] = field(default_factory=list)

    @classmethod
    def new(cls) -> "UnifiedExecFooter":
        return cls()

    def set_processes(self, processes: Iterable[str]) -> bool:
        next_processes = [str(process) for process in processes]
        if self.processes == next_processes:
            return False
        self.processes = next_processes
        return True

    def is_empty(self) -> bool:
        return not self.processes

    def summary_text(self) -> Optional[str]:
        if not self.processes:
            return None
        count = len(self.processes)
        plural = "" if count == 1 else "s"
        return f"{count} background terminal{plural} running · /ps to view · /stop to close"

    def render_lines(self, width: int) -> List[FooterLine]:
        width = int(width)
        if width < 4:
            return []
        summary = self.summary_text()
        if summary is None:
            return []
        message = f"  {summary}"
        truncated, _suffix, _taken = take_prefix_by_width(message, width)
        return [FooterLine(truncated, dim=True)]

    def render(self, area: Any = None, buf: Any = None) -> List[FooterLine]:
        width = _area_width(area)
        height = _area_height(area)
        if width <= 0 or height <= 0:
            return []
        return self.render_lines(width)[:height]

    def desired_height(self, width: int) -> int:
        return len(self.render_lines(width))


def render(footer: UnifiedExecFooter, area: Any = None, buf: Any = None) -> List[FooterLine]:
    return footer.render(area, buf)


def desired_height(footer: UnifiedExecFooter, width: int) -> int:
    return footer.desired_height(width)


def _area_width(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("width", 0))
    if isinstance(area, tuple) and len(area) >= 3:
        return int(area[2])
    return int(getattr(area, "width", 0))


def _area_height(area: Any) -> int:
    if area is None:
        return 0
    if isinstance(area, dict):
        return int(area.get("height", 0))
    if isinstance(area, tuple) and len(area) >= 4:
        return int(area[3])
    return int(getattr(area, "height", 0))


__all__ = [
    "FooterLine",
    "RUST_MODULE",
    "UnifiedExecFooter",
    "desired_height",
    "render",
]
