"""Semantic rendering helpers for the request-user-input overlay.

Rust reference: codex-rs/tui/src/bottom_pane/request_user_input/render.rs.

The Rust module renders ratatui widgets into a terminal buffer. The Python
port keeps the same layout decisions and state gates, but returns small
semantic events instead of framework-specific buffer cells.
"""

from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from ..._porting import RustTuiModule
from .layout import Rect, layout_sections

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::request_user_input::render",
    source="codex/codex-rs/tui/src/bottom_pane/request_user_input/render.rs",
    status="complete",
)

MIN_OVERLAY_HEIGHT = 8
PROGRESS_ROW_HEIGHT = 1
SPACER_ROWS_WITH_NOTES = 1
SPACER_ROWS_NO_OPTIONS = 0
TIP_SEPARATOR = " | "
UNANSWERED_CONFIRM_TITLE = "Submit with unanswered questions?"


@dataclass(frozen=True)
class StyledSpan:
    text: str
    style: Tuple[str, ...] = ()


@dataclass(frozen=True)
class StyledLine:
    spans: Tuple[StyledSpan, ...] = ()
    style: Tuple[str, ...] = ()

    @classmethod
    def from_text(cls, text: str, *style: str) -> "StyledLine":
        return cls((StyledSpan(str(text)),), tuple(style))

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


@dataclass
class UnansweredConfirmationData:
    title_line: StyledLine
    subtitle_line: StyledLine
    hint_line: StyledLine
    rows: List[Any]
    state: Any


@dataclass
class UnansweredConfirmationLayout:
    header_lines: List[StyledLine]
    hint_lines: List[StyledLine]
    rows: List[Any]
    state: Any


@dataclass(frozen=True)
class BreakPoint:
    span_idx: int
    byte_end: int


def line_to_owned(line: Any) -> StyledLine:
    """Clone a Rust-like line into an owned semantic line."""

    if isinstance(line, StyledLine):
        return StyledLine(tuple(StyledSpan(span.text, tuple(span.style)) for span in line.spans), tuple(line.style))
    if isinstance(line, StyledSpan):
        return StyledLine((StyledSpan(line.text, tuple(line.style)),))
    spans = getattr(line, "spans", None)
    style = tuple(getattr(line, "style", ()))
    if spans is not None:
        return StyledLine(tuple(StyledSpan(str(getattr(span, "text", span)), tuple(getattr(span, "style", ()))) for span in spans), style)
    return StyledLine.from_text(str(line))


def desired_height(overlay: Any, width: int) -> int:
    if _call_bool(overlay, "confirm_unanswered_active"):
        return unanswered_confirmation_height(overlay, width)

    inner = menu_surface_inset(Rect(0, 0, max(0, int(width)), 65535))
    inner_width = max(1, inner.width)
    has_options = _call_bool(overlay, "has_options")
    question_height = len(_call(overlay, "wrapped_question_lines", inner_width, default=[]))
    options_height = int(_call(overlay, "options_preferred_height", inner_width, default=0)) if has_options else 0
    notes_visible = (not has_options) or _call_bool(overlay, "notes_ui_visible")
    notes_height = int(_call(overlay, "notes_input_height", inner_width, default=0)) if notes_visible else 0
    spacer_rows = SPACER_ROWS_NO_OPTIONS
    footer_height = int(_call(overlay, "footer_required_height", inner_width, default=0))
    total = question_height + options_height + spacer_rows + notes_height + footer_height + PROGRESS_ROW_HEIGHT
    total += menu_surface_padding_height()
    return max(MIN_OVERLAY_HEIGHT, total)


def render(overlay: Any, area: Rect, buf: Optional[Any] = None) -> List[Dict[str, Any]]:
    return render_ui(overlay, area, buf)


def cursor_pos(overlay: Any, area: Rect) -> Optional[Tuple[int, int]]:
    return cursor_pos_impl(overlay, area)


def unanswered_confirmation_data(overlay: Any) -> UnansweredConfirmationData:
    unanswered = int(_call(overlay, "unanswered_question_count", default=_call(overlay, "unanswered_count", default=0)))
    suffix = "s" if unanswered != 1 else ""
    return UnansweredConfirmationData(
        title_line=StyledLine.from_text(_get_module_const(overlay, "UNANSWERED_CONFIRM_TITLE", UNANSWERED_CONFIRM_TITLE), "bold"),
        subtitle_line=StyledLine.from_text(f"{unanswered} unanswered question{suffix}"),
        hint_line=standard_popup_hint_line(),
        rows=list(_call(overlay, "unanswered_confirmation_rows", default=[])),
        state=getattr(overlay, "confirm_unanswered", None) or {},
    )


def unanswered_confirmation_layout(overlay: Any, width: int) -> UnansweredConfirmationLayout:
    data = unanswered_confirmation_data(overlay)
    del width
    header = [data.title_line, data.subtitle_line]
    hint = [data.hint_line]
    return UnansweredConfirmationLayout(header, hint, data.rows, data.state)


def unanswered_confirmation_height(overlay: Any, width: int) -> int:
    layout = unanswered_confirmation_layout(overlay, width)
    rows_height = 1
    total = len(layout.header_lines) + 1 + rows_height + 1 + len(layout.hint_lines)
    total += menu_surface_padding_height()
    return max(MIN_OVERLAY_HEIGHT, total)


def render_unanswered_confirmation(overlay: Any, area: Rect, buf: Optional[Any] = None) -> List[Dict[str, Any]]:
    content = menu_surface_inset(area)
    layout = unanswered_confirmation_layout(overlay, content.width)
    events: List[Dict[str, Any]] = [{"kind": "surface", "area": _rect(area), "content_area": _rect(content)}]
    y = content.y
    for line in layout.header_lines:
        events.append({"kind": "unanswered_header", "x": content.x, "y": y, "text": line.text, "style": line.style})
        y += 1
    y += 1
    content_bottom = content.bottom()
    rows_area = Rect(content.x, y, content.width, max(1, min(len(layout.rows), max(1, content_bottom - y - len(layout.hint_lines) - 1))))
    events.extend(render_rows_bottom_aligned(rows_area, layout.rows, layout.state, rows_area.height, "No unanswered questions"))
    y = rows_area.bottom()
    if y < content_bottom - len(layout.hint_lines):
        y += 1
    for line in layout.hint_lines:
        if y >= content_bottom:
            break
        events.append({"kind": "hint", "x": content.x, "y": y, "text": line.text, "style": line.style})
        y += 1
    return _write_events(buf, events)


def render_ui(overlay: Any, area: Rect, buf: Optional[Any] = None) -> List[Dict[str, Any]]:
    if area.width == 0 or area.height == 0:
        return []
    if _call_bool(overlay, "confirm_unanswered_active"):
        return render_unanswered_confirmation(overlay, area, buf)

    content = menu_surface_inset(area)
    sections = layout_sections(overlay, content)
    events: List[Dict[str, Any]] = [{"kind": "surface", "area": _rect(area), "content_area": _rect(content)}]

    total = int(_call(overlay, "question_count", default=0))
    current_index = int(_call(overlay, "current_index", default=0))
    unanswered = int(_call(overlay, "unanswered_count", default=0))
    if total > 0:
        progress = f"Question {current_index + 1}/{total}"
        if unanswered > 0:
            progress += f" ({unanswered} unanswered)"
    else:
        progress = "No questions"
    events.append({"kind": "progress", "area": _rect(sections.progress_area), "text": progress})

    current_text = _composer_text(overlay)
    answered = bool(_call(overlay, "is_question_answered", current_index, current_text, default=False))
    q_style = () if answered else ("cyan",)
    for offset, line in enumerate(_call(overlay, "wrapped_question_lines", max(1, sections.question_area.width), default=[])):
        if offset >= sections.question_area.height:
            break
        owned = line_to_owned(line)
        events.append({"kind": "question", "x": sections.question_area.x, "y": sections.question_area.y + offset, "text": owned.text, "style": q_style})

    has_options = _call_bool(overlay, "has_options")
    if has_options and sections.options_area.height > 0:
        rows = list(_call(overlay, "option_rows", sections.options_area.width, default=[]))
        events.extend(render_rows_bottom_aligned(sections.options_area, rows, _call(overlay, "current_answer", default={}), sections.options_area.height, "No options"))

    notes_visible = _call_bool(overlay, "notes_ui_visible")
    if notes_visible and sections.notes_area.height > 0:
        text = _call(getattr(overlay, "composer", None), "current_text", default=current_text)
        events.append({"kind": "notes", "area": _rect(sections.notes_area), "text": text, "mask": "*" if _current_question_secret(overlay) else None})

    if sections.footer_lines > 0:
        footer_area = Rect(content.x, content.bottom() - sections.footer_lines, content.width, sections.footer_lines)
        events.extend(render_footer_lines(overlay, footer_area, has_options, sections.options_area))

    return _write_events(buf, events)


def render_footer_lines(overlay: Any, footer_area: Rect, has_options: Optional[bool] = None, options_area: Rect | None = None) -> List[Dict[str, Any]]:
    has_options = _call_bool(overlay, "has_options") if has_options is None else has_options
    option_tip = None
    if has_options and options_area is not None and options_area.height > 0:
        required = int(_call(overlay, "options_required_height", footer_area.width, default=0))
        if required > options_area.height:
            selected = int(_call(overlay, "selected_option_index", default=0)) + 1
            total = int(_call(overlay, "options_len", default=max(1, selected)))
            option_tip = f"option {selected}/{total}"
    tips = _call(overlay, "footer_tip_lines_with_prefix", footer_area.width, option_tip, default=[])
    events: List[Dict[str, Any]] = []
    for row, tip in enumerate(tips):
        if row >= footer_area.height:
            break
        parts = [str(part) for part in (tip if isinstance(tip, (list, tuple)) else [tip]) if str(part)]
        text = TIP_SEPARATOR.join(parts)
        text = truncate_line_word_boundary_with_ellipsis(StyledLine.from_text(text), footer_area.width).text
        events.append({"kind": "footer", "x": footer_area.x, "y": footer_area.y + row, "text": text, "highlight_style": ("cyan", "bold"), "tip_style": ("dim",)})
    return events


def cursor_pos_impl(overlay: Any, area: Rect) -> Optional[Tuple[int, int]]:
    if _call_bool(overlay, "confirm_unanswered_active"):
        return None
    if not _call_bool(overlay, "focus_is_notes"):
        return None
    if _call_bool(overlay, "has_options") and not _call_bool(overlay, "notes_ui_visible"):
        return None
    content = menu_surface_inset(area)
    if content.width == 0 or content.height == 0:
        return None
    notes_area = layout_sections(overlay, content).notes_area
    if notes_area.width == 0 or notes_area.height == 0:
        return None
    composer = getattr(overlay, "composer", None)
    return _call(composer, "cursor_pos", notes_area, default=None)


def render_notes_input(overlay: Any, area: Rect, buf: Optional[Any] = None) -> List[Dict[str, Any]]:
    event = {"kind": "notes", "area": _rect(area), "text": _composer_text(overlay), "mask": "*" if _current_question_secret(overlay) else None}
    return _write_events(buf, [event])


def line_width(line: Any) -> int:
    return sum(_char_width(char) for char in line_to_owned(line).text)


def render_rows_bottom_aligned(area: Rect, rows: Iterable[Any], state: Any, max_results: int, empty_message: str) -> List[Dict[str, Any]]:
    materialized = list(rows)[: max(0, int(max_results))]
    if not materialized:
        materialized = [empty_message]
    visible = materialized[-area.height :] if area.height > 0 else []
    start_y = area.y + max(0, area.height - len(visible))
    selected_idx = None
    if isinstance(state, dict):
        selected_idx = state.get("selected_idx")
    elif hasattr(state, "selected_idx"):
        selected_idx = getattr(state, "selected_idx")
    events: List[Dict[str, Any]] = []
    base_index = max(0, len(materialized) - len(visible))
    for offset, row in enumerate(visible):
        events.append({
            "kind": "row",
            "x": area.x,
            "y": start_y + offset,
            "text": _row_text(row),
            "index": base_index + offset,
            "selected": selected_idx == base_index + offset,
        })
    return events


def truncate_line_word_boundary_with_ellipsis(line: Any, max_width: int) -> StyledLine:
    max_width = max(0, int(max_width))
    owned = line_to_owned(line)
    if max_width == 0:
        return StyledLine.from_text("")
    if line_width(owned) <= max_width:
        return owned
    ellipsis = "…"
    ellipsis_width = line_width(StyledLine.from_text(ellipsis))
    if max_width <= ellipsis_width:
        return StyledLine.from_text(ellipsis[:max_width], *(owned.style or ()))
    limit = max_width - ellipsis_width
    text = owned.text
    fallback = _take_display_width(text, limit)
    boundary = -1
    visible = _take_display_width(text, limit)
    for idx, char in enumerate(visible):
        if char.isspace():
            boundary = idx
    prefix = visible[:boundary].rstrip() if boundary > 0 else fallback.rstrip()
    if not prefix:
        prefix = fallback
    return StyledLine.from_text(prefix + ellipsis, *(owned.style or ()))


def _char_width(char: str) -> int:
    if unicodedata.combining(char):
        return 0
    if unicodedata.east_asian_width(char) in {"F", "W"}:
        return 2
    return 1


def _take_display_width(text: str, max_width: int) -> str:
    used = 0
    out: List[str] = []
    for char in text:
        width = _char_width(char)
        if used + width > max_width:
            break
        out.append(char)
        used += width
    return "".join(out)


def standard_popup_hint_line() -> StyledLine:
    return StyledLine((StyledSpan("enter", ("cyan", "bold")), StyledSpan(" submit"), StyledSpan(TIP_SEPARATOR), StyledSpan("esc", ("cyan", "bold")), StyledSpan(" cancel")), ("dim",))


def wrap_styled_line(line: Any, width: int) -> List[StyledLine]:
    owned = line_to_owned(line)
    width = max(1, int(width))
    text = owned.text
    if not text:
        return [StyledLine.from_text("")]
    chunks = [text[index : index + width] for index in range(0, len(text), width)]
    return [StyledLine.from_text(chunk, *owned.style) for chunk in chunks]


def menu_surface_inset(area: Rect) -> Rect:
    if area.width <= 2 or area.height <= 2:
        return Rect(area.x, area.y, 0, 0)
    return Rect(area.x + 1, area.y + 1, area.width - 2, area.height - 2)


def menu_surface_padding_height() -> int:
    return 2


def _call(obj: Any, name: str, *args: Any, default: Any = None) -> Any:
    if obj is None:
        return default
    attr = getattr(obj, name, None)
    if attr is None:
        return default
    return attr(*args) if callable(attr) else attr


def _call_bool(obj: Any, name: str) -> bool:
    return bool(_call(obj, name, default=False))


def _composer_text(overlay: Any) -> str:
    composer = getattr(overlay, "composer", None)
    value = _call(composer, "current_text", default="")
    return "" if value is None else str(value)


def _current_question_secret(overlay: Any) -> bool:
    question = _call(overlay, "current_question", default=None)
    return bool(getattr(question, "is_secret", False))


def _get_module_const(overlay: Any, name: str, default: Any) -> Any:
    return getattr(overlay, name, default)


def _row_text(row: Any) -> str:
    if isinstance(row, StyledLine):
        return row.text
    if isinstance(row, StyledSpan):
        return row.text
    if isinstance(row, dict):
        return str(row.get("text", row))
    return str(getattr(row, "text", row))


def _rect(area: Rect) -> Dict[str, int]:
    return {"x": area.x, "y": area.y, "width": area.width, "height": area.height}


def _write_events(buf: Optional[Any], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if buf is not None and hasattr(buf, "extend"):
        buf.extend(events)
    return events


__all__ = [
    "BreakPoint",
    "MIN_OVERLAY_HEIGHT",
    "PROGRESS_ROW_HEIGHT",
    "RUST_MODULE",
    "SPACER_ROWS_NO_OPTIONS",
    "SPACER_ROWS_WITH_NOTES",
    "StyledLine",
    "StyledSpan",
    "TIP_SEPARATOR",
    "UNANSWERED_CONFIRM_TITLE",
    "UnansweredConfirmationData",
    "UnansweredConfirmationLayout",
    "cursor_pos",
    "cursor_pos_impl",
    "desired_height",
    "line_to_owned",
    "line_width",
    "render",
    "render_footer_lines",
    "render_notes_input",
    "render_rows_bottom_aligned",
    "render_ui",
    "render_unanswered_confirmation",
    "standard_popup_hint_line",
    "truncate_line_word_boundary_with_ellipsis",
    "unanswered_confirmation_data",
    "unanswered_confirmation_height",
    "unanswered_confirmation_layout",
    "wrap_styled_line",
]


