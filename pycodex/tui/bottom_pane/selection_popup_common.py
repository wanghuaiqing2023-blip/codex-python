"""Common selection-popup row layout helpers.

Port of Rust ``codex-tui::bottom_pane::selection_popup_common`` using semantic
``Line``/``Span``/``Rect`` values instead of ratatui buffers.
"""

from __future__ import annotations

import textwrap
import unicodedata
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, List, MutableSequence, Optional, Tuple

from .._porting import RustTuiModule
from ..ratatui_bridge import Rect
from .scroll_state import ScrollState

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::selection_popup_common",
    source="codex/codex-rs/tui/src/bottom_pane/selection_popup_common.rs",
    status="complete",
)


@dataclass(frozen=True)
class Span:
    text: str
    style: str = "plain"

    @property
    def width(self) -> int:
        return _cell_width(self.text)


@dataclass(frozen=True)
class Line:
    spans: Tuple[Span, ...]

    @classmethod
    def from_text(cls, text: str, style: str = "plain") -> "Line":
        return cls((Span(text, style),))

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    @property
    def width(self) -> int:
        return sum(span.width for span in self.spans)


@dataclass(frozen=True)
class TerminalPopupLine:
    text: str
    selected: bool = False


@dataclass
class GenericDisplayRow:
    name: str = ""
    name_prefix_spans: List[Span] = field(default_factory=list)
    display_shortcut: Optional[Any] = None
    match_indices: Optional[List[int]] = None
    description: Optional[str] = None
    category_tag: Optional[str] = None
    disabled_reason: Optional[str] = None
    is_disabled: bool = False
    wrap_indent: Optional[int] = None


class ColumnWidthMode(Enum):
    AUTO_VISIBLE = "AutoVisible"
    AUTO_ALL_ROWS = "AutoAllRows"
    FIXED = "Fixed"


@dataclass(frozen=True)
class ColumnWidthConfig:
    mode: ColumnWidthMode = ColumnWidthMode.AUTO_VISIBLE
    name_column_width: Optional[int] = None

    @classmethod
    def new(cls, mode: ColumnWidthMode, name_column_width: Optional[int] = None) -> "ColumnWidthConfig":
        return cls(mode=mode, name_column_width=name_column_width)


FIXED_LEFT_COLUMN_NUMERATOR = 3
FIXED_LEFT_COLUMN_DENOMINATOR = 10
MENU_SURFACE_INSET_V = 1
MENU_SURFACE_INSET_H = 2


def menu_surface_inset(area: Rect) -> Rect:
    return Rect(
        x=area.x + MENU_SURFACE_INSET_H,
        y=area.y + MENU_SURFACE_INSET_V,
        width=max(area.width - MENU_SURFACE_INSET_H * 2, 0),
        height=max(area.height - MENU_SURFACE_INSET_V * 2, 0),
    )


def menu_surface_padding_height() -> int:
    return MENU_SURFACE_INSET_V * 2


def render_menu_surface(area: Rect, buf: MutableSequence[Any]) -> Rect:
    if area.is_empty():
        return area
    buf.append(("surface", area))
    return menu_surface_inset(area)


def wrap_styled_line(line: Line, width: int) -> List[Line]:
    width = max(width, 1)
    text = line.text
    chunks = textwrap.wrap(text, width=width, replace_whitespace=False, drop_whitespace=False) or [""]
    style = line.spans[0].style if len(line.spans) == 1 else "plain"
    return [Line.from_text(chunk, style) for chunk in chunks]


def line_to_owned(line: Line) -> Line:
    return Line(tuple(Span(span.text, span.style) for span in line.spans))


def compute_desc_col(
    rows_all: List[GenericDisplayRow],
    start_idx: int,
    visible_items: int,
    content_width: int,
    column_width: ColumnWidthConfig = ColumnWidthConfig(),
) -> int:
    if content_width <= 1:
        return 0

    max_desc_col = content_width - 1
    max_auto_desc_col = min(max_desc_col, max((content_width * (FIXED_LEFT_COLUMN_DENOMINATOR - FIXED_LEFT_COLUMN_NUMERATOR)) // FIXED_LEFT_COLUMN_DENOMINATOR, 1))
    if column_width.mode is ColumnWidthMode.FIXED:
        return min(max((content_width * FIXED_LEFT_COLUMN_NUMERATOR) // FIXED_LEFT_COLUMN_DENOMINATOR, 1), max_desc_col)

    if column_width.mode is ColumnWidthMode.AUTO_VISIBLE:
        rows = rows_all[start_idx : start_idx + visible_items]
    else:
        rows = rows_all

    max_name_width = max((_row_name_width(row) for row in rows), default=0)
    if column_width.name_column_width is not None:
        max_name_width = max(column_width.name_column_width, max_name_width)
    if column_width.mode is ColumnWidthMode.AUTO_ALL_ROWS:
        return min(max_name_width + 2, max_desc_col)
    return min(max_name_width + 2, max_auto_desc_col)


def wrap_indent(row: GenericDisplayRow, desc_col: int, max_width: int) -> int:
    max_indent = max(max_width - 1, 0)
    indent = row.wrap_indent if row.wrap_indent is not None else desc_col if row.description is not None or row.disabled_reason is not None else 0
    return min(indent, max_indent)


def should_wrap_name_in_column(row: GenericDisplayRow) -> bool:
    return (
        row.wrap_indent is not None
        and row.description is not None
        and row.disabled_reason is None
        and row.match_indices is None
        and row.display_shortcut is None
        and row.category_tag is None
        and not row.name_prefix_spans
    )


def wrap_two_column_row(row: GenericDisplayRow, desc_col: int, width: int) -> List[Line]:
    if row.description is None:
        return []

    width = max(width, 1)
    max_desc_col = width - 1
    if max_desc_col == 0:
        return []

    desc_col = min(max(desc_col, 1), max_desc_col)
    left_width = max(desc_col - 2, 1)
    right_width = max(width - desc_col, 1)
    name_indent = min(row.wrap_indent or 0, max(left_width - 1, 0))
    name_lines = textwrap.wrap(row.name, width=left_width, subsequent_indent=" " * name_indent) or [""]
    desc_lines = textwrap.wrap(row.description, width=right_width) or [""]

    out: List[Line] = []
    for idx in range(max(len(name_lines), len(desc_lines), 1)):
        spans: List[Span] = []
        if idx < len(name_lines):
            spans.append(Span(name_lines[idx]))
        if idx < len(desc_lines):
            left_used = sum(span.width for span in spans)
            gap = desc_col if left_used == 0 else max(desc_col - left_used, 2)
            spans.append(Span(" " * gap))
            spans.append(Span(desc_lines[idx], "dim"))
        out.append(Line(tuple(spans)))
    return out


def wrap_standard_row(row: GenericDisplayRow, desc_col: int, width: int) -> List[Line]:
    line = build_full_line(row, desc_col)
    width = max(width, 1)
    indent = " " * wrap_indent(row, desc_col, width)
    chunks = textwrap.wrap(line.text, width=width, subsequent_indent=indent, replace_whitespace=False, drop_whitespace=False) or [""]
    return [Line.from_text(chunk) for chunk in chunks]


def wrap_row_lines(row: GenericDisplayRow, desc_col: int, width: int) -> List[Line]:
    if should_wrap_name_in_column(row):
        wrapped = wrap_two_column_row(row, desc_col, width)
        if wrapped:
            return wrapped
    return wrap_standard_row(row, desc_col, width)


def apply_row_state_style(lines: List[Line], selected: bool, is_disabled: bool) -> None:
    style = "accent" if selected else None
    if is_disabled:
        style = "dim" if style is None else f"{style}+dim"
    if style is None:
        return
    for idx, line in enumerate(lines):
        lines[idx] = Line(tuple(Span(span.text, style) for span in line.spans))


def compute_item_window_start(rows_all: List[GenericDisplayRow], state: ScrollState, max_items: int) -> int:
    if not rows_all or max_items == 0:
        return 0
    start_idx = min(state.scroll_top, len(rows_all) - 1)
    if state.selected_idx is not None:
        if state.selected_idx < start_idx:
            start_idx = state.selected_idx
        else:
            bottom = start_idx + max_items - 1
            if state.selected_idx > bottom:
                start_idx = state.selected_idx + 1 - max_items
    return start_idx


def is_selected_visible_in_wrapped_viewport(
    rows_all: List[GenericDisplayRow],
    start_idx: int,
    max_items: int,
    selected_idx: int,
    desc_col: int,
    width: int,
    viewport_height: int,
) -> bool:
    if viewport_height == 0:
        return False
    used_lines = 0
    for idx, row in enumerate(rows_all[start_idx : start_idx + max_items], start=start_idx):
        row_lines = max(len(wrap_row_lines(row, desc_col, width)), 1)
        if used_lines > 0 and used_lines + row_lines > viewport_height:
            break
        if idx == selected_idx:
            return True
        used_lines += row_lines
        if used_lines >= viewport_height:
            break
    return False


def adjust_start_for_wrapped_selection_visibility(
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_items: int,
    desc_measure_items: int,
    width: int,
    viewport_height: int,
    column_width: ColumnWidthConfig = ColumnWidthConfig(),
) -> int:
    start_idx = compute_item_window_start(rows_all, state, max_items)
    if state.selected_idx is None or viewport_height == 0:
        return start_idx
    while start_idx < state.selected_idx:
        desc_col = compute_desc_col(rows_all, start_idx, desc_measure_items, width, column_width)
        if is_selected_visible_in_wrapped_viewport(rows_all, start_idx, max_items, state.selected_idx, desc_col, width, viewport_height):
            break
        start_idx += 1
    return start_idx


def build_full_line(row: GenericDisplayRow, desc_col: int) -> Line:
    description = _combined_description(row)
    prefix_width = sum(span.width for span in row.name_prefix_spans)
    name_limit = max(desc_col - 2 - prefix_width, 0) if description is not None else 10**9
    name = row.name
    truncated = False
    name, truncated = _truncate_cells(name, name_limit)
    spans = list(row.name_prefix_spans)
    match_set = set(row.match_indices or [])
    for idx, ch in enumerate(name):
        spans.append(Span(ch, "bold" if idx in match_set else "plain"))
    if truncated:
        spans.append(Span("…"))
    if row.disabled_reason is not None:
        spans.append(Span(" (disabled)", "dim"))
    name_width = prefix_width + sum(span.width for span in spans[len(row.name_prefix_spans) :])
    if row.display_shortcut is not None:
        spans.extend([Span(" ("), Span(str(row.display_shortcut)), Span(")")])
    if description is not None:
        gap = max(desc_col - name_width, 0)
        if gap:
            spans.append(Span(" " * gap))
        spans.append(Span(description, "dim"))
    if row.category_tag:
        spans.extend([Span("  "), Span(row.category_tag, "dim")])
    return Line(tuple(spans))


def render_rows(
    area: Rect,
    buf: MutableSequence[Line],
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_results: int,
    empty_message: str,
) -> int:
    return render_rows_with_col_width_mode(area, buf, rows_all, state, max_results, empty_message, ColumnWidthConfig())


def render_rows_with_col_width_mode(
    area: Rect,
    buf: MutableSequence[Line],
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_results: int,
    empty_message: str,
    column_width: ColumnWidthConfig,
) -> int:
    return _render_rows_inner(area, buf, rows_all, state, max_results, empty_message, column_width, wrap=True)


def render_terminal_popup_lines(
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    *,
    width: int,
    max_results: int,
    empty_message: str,
    column_width: ColumnWidthConfig,
) -> List[TerminalPopupLine]:
    """Render selection-popup rows into terminal live-pane DTOs.

    Rust owner: ``codex-tui::bottom_pane::selection_popup_common`` owns row
    windowing, wrapping, and selected-row styling.  Terminal adapters should
    consume these DTOs instead of reimplementing popup row rendering.
    """

    buffer: list[Line] = []
    render_rows_with_col_width_mode(
        Rect(0, 0, max(1, width), max(1, max_results)),
        buffer,
        rows_all,
        state,
        max_results,
        empty_message,
        column_width,
    )
    return [
        TerminalPopupLine(
            line.text,
            _line_has_accent_style(line),
        )
        for line in buffer
    ]


def render_rows_single_line(
    area: Rect,
    buf: MutableSequence[Line],
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_results: int,
    empty_message: str,
) -> int:
    return render_rows_single_line_with_col_width_mode(area, buf, rows_all, state, max_results, empty_message, ColumnWidthConfig())


def render_rows_single_line_with_col_width_mode(
    area: Rect,
    buf: MutableSequence[Line],
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_results: int,
    empty_message: str,
    column_width: ColumnWidthConfig,
) -> int:
    return _render_rows_inner(area, buf, rows_all, state, max_results, empty_message, column_width, wrap=False)


def measure_rows_height(rows_all: List[GenericDisplayRow], state: ScrollState, max_results: int, width: int) -> int:
    return measure_rows_height_with_col_width_mode(rows_all, state, max_results, width, ColumnWidthConfig())


def measure_rows_height_with_col_width_mode(
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_results: int,
    width: int,
    column_width: ColumnWidthConfig,
) -> int:
    if not rows_all:
        return 1
    content_width = max(width - 1, 1)
    visible_items = min(max_results, len(rows_all))
    start_idx = compute_item_window_start(rows_all, state, visible_items)
    desc_col = compute_desc_col(rows_all, start_idx, visible_items, content_width, column_width)
    total = 0
    for row in rows_all[start_idx : start_idx + visible_items]:
        total += len(wrap_row_lines(row, desc_col, content_width))
    return max(total, 1)


def _render_rows_inner(
    area: Rect,
    buf: MutableSequence[Line],
    rows_all: List[GenericDisplayRow],
    state: ScrollState,
    max_results: int,
    empty_message: str,
    column_width: ColumnWidthConfig,
    *,
    wrap: bool,
) -> int:
    if not rows_all:
        if area.height > 0:
            buf.append(Line.from_text(empty_message, "dim+italic"))
        return 1 if area.height > 0 else 0
    max_items = min(max_results, len(rows_all), max(area.height, 1) if not wrap else len(rows_all))
    if max_items == 0:
        return 0
    start_idx = compute_item_window_start(rows_all, state, max_items)
    desc_col = compute_desc_col(rows_all, start_idx, max_items, area.width, column_width)
    rendered = 0
    for idx, row in enumerate(rows_all[start_idx : start_idx + max_items], start=start_idx):
        lines = wrap_row_lines(row, desc_col, area.width) if wrap else [_truncate_line(build_full_line(row, desc_col), area.width)]
        apply_row_state_style(lines, state.selected_idx == idx and not row.is_disabled, row.is_disabled)
        for line in lines:
            if rendered >= area.height:
                return rendered
            buf.append(line)
            rendered += 1
    return rendered


def _truncate_line(line: Line, width: int) -> Line:
    if line.width <= width:
        return line
    if width <= 0:
        return Line(())
    return Line.from_text(line.text[: max(width - 1, 0)] + "…")


def _line_has_accent_style(line: Any) -> bool:
    spans = getattr(line, "spans", ())
    for span in spans:
        style = str(getattr(span, "style", ""))
        if "accent" in style:
            return True
    return False


def _row_name_width(row: GenericDisplayRow) -> int:
    width = sum(span.width for span in row.name_prefix_spans) + _cell_width(row.name)
    if row.disabled_reason is not None:
        width += len(" (disabled)")
    return width


def _combined_description(row: GenericDisplayRow) -> Optional[str]:
    if row.description is not None and row.disabled_reason is not None:
        return f"{row.description} (disabled: {row.disabled_reason})"
    if row.description is not None:
        return row.description
    if row.disabled_reason is not None:
        return f"disabled: {row.disabled_reason}"
    return None


def _cell_width(text: str) -> int:
    width = 0
    for ch in text:
        if unicodedata.combining(ch):
            continue
        if unicodedata.category(ch) in {"Cc", "Cf"}:
            continue
        width += 2 if unicodedata.east_asian_width(ch) in {"F", "W"} else 1
    return width


def _truncate_cells(text: str, max_width: int) -> Tuple[str, bool]:
    if max_width >= 10**8:
        return text, False
    if max_width <= 0:
        return "", bool(text)
    out: List[str] = []
    used = 0
    truncated = False
    for ch in text:
        ch_width = _cell_width(ch)
        if used + ch_width > max_width:
            truncated = True
            break
        out.append(ch)
        used += ch_width
    if not truncated:
        remaining = text[len("".join(out)) :]
        truncated = bool(remaining)
    return "".join(out), truncated


__all__ = [
    "ColumnWidthConfig",
    "ColumnWidthMode",
    "FIXED_LEFT_COLUMN_DENOMINATOR",
    "FIXED_LEFT_COLUMN_NUMERATOR",
    "GenericDisplayRow",
    "Line",
    "MENU_SURFACE_INSET_H",
    "MENU_SURFACE_INSET_V",
    "RUST_MODULE",
    "Rect",
    "Span",
    "TerminalPopupLine",
    "adjust_start_for_wrapped_selection_visibility",
    "apply_row_state_style",
    "build_full_line",
    "compute_desc_col",
    "compute_item_window_start",
    "is_selected_visible_in_wrapped_viewport",
    "line_to_owned",
    "measure_rows_height",
    "measure_rows_height_with_col_width_mode",
    "menu_surface_inset",
    "menu_surface_padding_height",
    "render_menu_surface",
    "render_rows",
    "render_rows_single_line",
    "render_rows_single_line_with_col_width_mode",
    "render_terminal_popup_lines",
    "render_rows_with_col_width_mode",
    "should_wrap_name_in_column",
    "wrap_indent",
    "wrap_row_lines",
    "wrap_standard_row",
    "wrap_styled_line",
    "wrap_two_column_row",
]

