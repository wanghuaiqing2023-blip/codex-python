"""Semantic renderer for Rust bottom_pane/mentions_v2/render.rs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..._porting import RustTuiModule
from ..popup_consts import MAX_POPUP_ROWS
from .candidate import MentionType, SearchResult, Selection
from .footer import render_footer
from .search_mode import SearchMode

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::render",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/render.rs",
)


@dataclass(frozen=True)
class RenderSpan:
    text: str
    style: tuple[str, ...] = ()


@dataclass(frozen=True)
class RenderLine:
    spans: tuple[RenderSpan, ...] = field(default_factory=tuple)

    def text(self) -> str:
        return "".join(span.text for span in self.spans)

    def width(self) -> int:
        return len(self.text())


@dataclass(frozen=True)
class RenderedPopup:
    rows: tuple[RenderLine, ...]
    footer: Any | None = None


def render_popup(
    area: Any,
    buf: Any,
    rows: Iterable[SearchResult],
    state: Any,
    empty_message: str,
    search_mode: SearchMode,
) -> RenderedPopup:
    width = _area_width(area)
    height = _area_height(area)
    if height > 2:
        list_height = height - 2
        hint_width = max(width - 2, 0)
        rendered_rows = render_rows({"width": max(width - 2, 0), "height": list_height}, buf, list(rows), state, empty_message)
        footer = render_footer(hint_width, search_mode=search_mode)
    else:
        rendered_rows = render_rows({"width": width, "height": height}, buf, list(rows), state, empty_message)
        footer = None
    popup = RenderedPopup(tuple(rendered_rows), footer)
    if isinstance(buf, list):
        buf.append(popup)
    return popup


def render_rows(area: Any, buf: Any, rows: list[SearchResult], state: Any, empty_message: str) -> list[RenderLine]:
    width = _area_width(area)
    height = _area_height(area)
    if height == 0:
        return []
    if not rows:
        line = RenderLine((RenderSpan(empty_message, ("italic",)),))
        if isinstance(buf, list):
            buf.append(line)
        return [line]

    visible_items = min(MAX_POPUP_ROWS, len(rows), max(height, 1))
    start_idx = min(_scroll_top(state), max(len(rows) - 1, 0))
    selected_idx = _selected_idx(state)
    if selected_idx is not None:
        if selected_idx < start_idx:
            start_idx = selected_idx
        elif visible_items > 0:
            bottom = start_idx + visible_items - 1
            if selected_idx > bottom:
                start_idx = selected_idx + 1 - visible_items

    window = rows[start_idx : start_idx + visible_items]
    primary_column_width = max((primary_text_width(row) for row in window), default=0)
    rendered: list[RenderLine] = []
    for idx, row in enumerate(rows[start_idx : start_idx + visible_items], start=start_idx):
        rendered.append(build_line(row, selected_idx == idx, width, primary_column_width))
    if isinstance(buf, list):
        buf.extend(rendered)
    return rendered


def build_line(row: SearchResult, selected: bool, width: int, primary_column_width: int) -> RenderLine:
    base_style = ("bold",) if selected else ()
    dim_style = ("bold",) if selected else ("dim",)
    tag = row.mention_type.span(base_style)
    tag_text = tag.content
    tag_width = len(tag_text)
    content_width = max(width - (tag_width + 2), 0)
    content = truncate_line_with_ellipsis_if_overflow(content_line(row, base_style, dim_style, primary_column_width), content_width)
    rendered_content_width = content.width()
    padding = max(width - (rendered_content_width + tag_width), 0)
    spans = list(content.spans)
    if padding > 0:
        spans.append(RenderSpan(" " * padding, dim_style))
    spans.append(RenderSpan(tag_text, tuple(tag.style)))
    return RenderLine(tuple(spans))


def content_line(row: SearchResult, base_style: tuple[str, ...] = (), dim_style: tuple[str, ...] = ("dim",), primary_column_width: int | None = None) -> RenderLine:
    primary_column_width = primary_text_width(row) if primary_column_width is None else primary_column_width
    spans = list(primary_spans(row, base_style))
    secondary = secondary_line(row, base_style, dim_style)
    if secondary is not None:
        padding = max(primary_column_width - primary_text_width(row), 0) + 2
        spans.append(RenderSpan(" " * padding, dim_style))
        spans.extend(secondary.spans)
    return RenderLine(tuple(spans))


def primary_spans(row: SearchResult, base_style: tuple[str, ...] = ()) -> list[RenderSpan]:
    name = file_name(row)
    if name is not None:
        style = (*base_style, "cyan") if row.mention_type is MentionType.FILE else base_style
        return [RenderSpan(name, style)]

    name_style = _name_style(row.mention_type, base_style)
    if row.match_indices is None:
        return [RenderSpan(row.display_name, name_style)]
    matched = set(row.match_indices)
    return [RenderSpan(ch, (*name_style, "bold") if idx in matched else name_style) for idx, ch in enumerate(row.display_name)]


def secondary_line(row: SearchResult, base_style: tuple[str, ...] = (), dim_style: tuple[str, ...] = ("dim",)) -> RenderLine | None:
    if file_name(row) is not None:
        spans = path_spans(row, base_style)
        if row.description:
            spans.append(RenderSpan("  ", dim_style))
            spans.append(RenderSpan(row.description, dim_style))
        return RenderLine(tuple(spans))
    if row.description:
        return RenderLine((RenderSpan(row.description, dim_style),))
    return None


def path_spans(row: SearchResult, base_style: tuple[str, ...] = ()) -> list[RenderSpan]:
    start = file_name_start(row)
    path_style = (*base_style, "dim")
    if start == 0:
        return [RenderSpan("./", path_style)]
    if start == -1:
        return [RenderSpan(row.display_name, base_style)]
    prefix = row.display_name[:start]
    if row.match_indices is None:
        return [RenderSpan(prefix, path_style)]
    matched = set(row.match_indices)
    return [RenderSpan(ch, (*path_style, "bold") if idx in matched else path_style) for idx, ch in enumerate(row.display_name[:start])]


def primary_text_width(row: SearchResult) -> int:
    name = file_name(row)
    return len(name if name is not None else row.display_name)


def file_name(row: SearchResult) -> str | None:
    start = file_name_start(row)
    if start == -1:
        return None
    return row.display_name[start:]


def file_name_start(row: SearchResult) -> int:
    if row.selection.kind == "File" and row.mention_type.is_filesystem():
        slash = max(row.display_name.rfind("/"), row.display_name.rfind("\\"))
        return 0 if slash < 0 else slash + 1
    return -1


def truncate_line_with_ellipsis_if_overflow(line: RenderLine, width: int) -> RenderLine:
    width = max(int(width), 0)
    if line.width() <= width:
        return line
    if width == 0:
        return RenderLine(())
    if width == 1:
        return RenderLine((RenderSpan("."),))
    return RenderLine((RenderSpan(line.text()[: width - 1] + "."),))


def line_text(line: RenderLine | None) -> str | None:
    return None if line is None else line.text()


def _name_style(mention_type: MentionType, base_style: tuple[str, ...]) -> tuple[str, ...]:
    if mention_type is MentionType.PLUGIN:
        return (*base_style, "magenta")
    if mention_type is MentionType.SKILL:
        return (*base_style, "dim")
    return base_style


def _area_width(area: Any) -> int:
    if isinstance(area, int):
        return max(area, 0)
    if isinstance(area, dict):
        return max(int(area.get("width", 0)), 0)
    return max(int(getattr(area, "width", 0)), 0)


def _area_height(area: Any) -> int:
    if isinstance(area, int):
        return 1
    if isinstance(area, dict):
        return max(int(area.get("height", 0)), 0)
    return max(int(getattr(area, "height", 0)), 0)


def _selected_idx(state: Any) -> int | None:
    if isinstance(state, dict):
        return state.get("selected_idx")
    return getattr(state, "selected_idx", None)


def _scroll_top(state: Any) -> int:
    if isinstance(state, dict):
        return int(state.get("scroll_top", 0) or 0)
    return int(getattr(state, "scroll_top", 0) or 0)


__all__ = [
    "RUST_MODULE",
    "RenderLine",
    "RenderSpan",
    "RenderedPopup",
    "build_line",
    "content_line",
    "file_name",
    "file_name_start",
    "line_text",
    "path_spans",
    "primary_spans",
    "primary_text_width",
    "render_popup",
    "render_rows",
    "secondary_line",
    "truncate_line_with_ellipsis_if_overflow",
]
