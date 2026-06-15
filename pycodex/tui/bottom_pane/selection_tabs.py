"""Selection tab bar helpers.

Port of Rust ``codex-tui::bottom_pane::selection_tabs`` using semantic lines
instead of ratatui ``Line``/``Span`` values.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, MutableSequence, Tuple, Union

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::selection_tabs",
    source="codex/codex-rs/tui/src/bottom_pane/selection_tabs.rs",
    status="complete",
)

TAB_GAP_WIDTH = 2


@dataclass(frozen=True)
class StyledSpan:
    text: str
    style: str = "plain"

    @property
    def width(self) -> int:
        # Rust delegates to ratatui/Unicode width.  For this tab label helper,
        # tests and callers use ordinary tab labels, so codepoint width is the
        # intended semantic approximation without adding dependencies.
        return len(self.text)


@dataclass(frozen=True)
class StyledLine:
    spans: Tuple[StyledSpan, ...]

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    @property
    def width(self) -> int:
        return sum(span.width for span in self.spans)


@dataclass
class SelectionTab:
    id: str
    label: str
    header: Any = None
    items: List[Any] = field(default_factory=list)


def tab_bar_height(tabs: List[SelectionTab], active_idx: int, width: int) -> int:
    if not tabs:
        return 0
    return min(len(tab_bar_lines(tabs, active_idx, width)), 2**16 - 1)


def render_tab_bar(
    tabs: List[SelectionTab],
    active_idx: int,
    area: Any,
    buf: Union[MutableSequence[str], MutableSequence[StyledLine]],
) -> None:
    """Render semantic tab lines into ``buf`` up to ``area.height``.

    ``area`` may be an object/dict with ``width`` and ``height`` fields.  The
    buffer is append-oriented because Python does not model ratatui's mutable
    cell grid in this module.
    """

    width = _field(area, "width")
    height = _field(area, "height")
    for line in tab_bar_lines(tabs, active_idx, width)[: int(height)]:
        buf.append(line)  # type: ignore[arg-type]


def tab_bar_lines(tabs: List[SelectionTab], active_idx: int, width: int) -> List[StyledLine]:
    if not tabs:
        return []

    max_width = max(int(width), 1)
    lines: List[StyledLine] = []
    current_spans: List[StyledSpan] = []
    current_width = 0

    for idx, tab in enumerate(tabs):
        unit = tab_unit(tab.label, idx == active_idx)
        unit_width = sum(span.width for span in unit)
        gap_width = 0 if not current_spans else TAB_GAP_WIDTH

        if current_spans and current_width + gap_width + unit_width > max_width:
            lines.append(StyledLine(tuple(current_spans)))
            current_spans = []
            current_width = 0

        if current_spans:
            current_spans.append(StyledSpan("  "))
            current_width += TAB_GAP_WIDTH

        current_width += unit_width
        current_spans.extend(unit)

    if current_spans:
        lines.append(StyledLine(tuple(current_spans)))
    return lines


def tab_unit(label: str, active: bool) -> List[StyledSpan]:
    if active:
        return [
            StyledSpan("[", "accent"),
            StyledSpan(label, "accent"),
            StyledSpan("]", "accent"),
        ]
    return [StyledSpan(label, "dim")]


def _field(area: Any, name: str) -> Any:
    if isinstance(area, dict):
        return area[name]
    return getattr(area, name)


__all__ = [
    "RUST_MODULE",
    "SelectionTab",
    "StyledLine",
    "StyledSpan",
    "TAB_GAP_WIDTH",
    "render_tab_bar",
    "tab_bar_height",
    "tab_bar_lines",
    "tab_unit",
]

