"""Web-search activity history cells.

Upstream source: ``codex/codex-rs/tui/src/history_cell/search.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from time import monotonic
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line
from .base import PrefixedWrappedHistoryCell

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::search",
    source="codex/codex-rs/tui/src/history_cell/search.rs",
)

SEARCH_BULLET = "- "


class WebSearchActionKind(Enum):
    Search = "search"
    OpenPage = "open_page"
    FindInPage = "find_in_page"
    Other = "other"


@dataclass(frozen=True)
class WebSearchAction:
    kind: WebSearchActionKind
    query: str | None = None
    queries: tuple[str, ...] | None = None
    url: str | None = None
    pattern: str | None = None

    @classmethod
    def search(
        cls, query: str | None = None, queries: Iterable[str] | None = None
    ) -> "WebSearchAction":
        return cls(
            WebSearchActionKind.Search,
            query=query,
            queries=None if queries is None else tuple(str(item) for item in queries),
        )

    @classmethod
    def open_page(cls, url: str | None = None) -> "WebSearchAction":
        return cls(WebSearchActionKind.OpenPage, url=url)

    @classmethod
    def find_in_page(
        cls, url: str | None = None, pattern: str | None = None
    ) -> "WebSearchAction":
        return cls(WebSearchActionKind.FindInPage, url=url, pattern=pattern)

    @classmethod
    def other(cls) -> "WebSearchAction":
        return cls(WebSearchActionKind.Other)

    @classmethod
    def coerce(cls, value: "WebSearchAction | dict[str, Any] | Any") -> "WebSearchAction":
        if isinstance(value, cls):
            return value
        if isinstance(value, dict):
            kind = str(value.get("kind", value.get("type", "other"))).lower()
            if kind in {"search", "web_search"}:
                return cls.search(value.get("query"), value.get("queries"))
            if kind in {"openpage", "open_page", "open"}:
                return cls.open_page(value.get("url"))
            if kind in {"findinpage", "find_in_page", "find"}:
                return cls.find_in_page(value.get("url"), value.get("pattern"))
            return cls.other()
        kind = str(getattr(value, "kind", getattr(value, "type", "other"))).lower()
        if kind in {"search", "websearchactionkind.search"}:
            return cls.search(getattr(value, "query", None), getattr(value, "queries", None))
        if kind in {"openpage", "open_page"}:
            return cls.open_page(getattr(value, "url", None))
        if kind in {"findinpage", "find_in_page"}:
            return cls.find_in_page(getattr(value, "url", None), getattr(value, "pattern", None))
        return cls.other()


def web_search_header(completed: bool) -> str:
    return "Searched" if completed else "Searching the web"


def web_search_action_detail(action: WebSearchAction | dict[str, Any] | Any) -> str:
    action = WebSearchAction.coerce(action)
    if action.kind is WebSearchActionKind.Search:
        if action.query:
            return action.query
        items = action.queries
        first = items[0] if items else ""
        if items is not None and len(items) > 1 and first:
            return f"{first} ..."
        return first
    if action.kind is WebSearchActionKind.OpenPage:
        return action.url or ""
    if action.kind is WebSearchActionKind.FindInPage:
        if action.pattern is not None and action.url is not None:
            return f"'{action.pattern}' in {action.url}"
        if action.pattern is not None:
            return f"'{action.pattern}'"
        if action.url is not None:
            return action.url
        return ""
    return ""


def web_search_detail(action: WebSearchAction | dict[str, Any] | Any | None, query: str) -> str:
    detail = web_search_action_detail(action) if action is not None else ""
    return str(query) if detail == "" else detail


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


@dataclass
class WebSearchCell:
    call_id_value: str
    query: str
    action: WebSearchAction | None = None
    start_time: float = 0.0
    completed: bool = False
    animations_enabled: bool = False

    @classmethod
    def new(
        cls,
        call_id: str,
        query: str,
        action: WebSearchAction | dict[str, Any] | Any | None = None,
        animations_enabled: bool = False,
    ) -> "WebSearchCell":
        return cls(
            str(call_id),
            str(query),
            None if action is None else WebSearchAction.coerce(action),
            monotonic(),
            False,
            bool(animations_enabled),
        )

    def call_id(self) -> str:
        return self.call_id_value

    def update(self, action: WebSearchAction | dict[str, Any] | Any, query: str) -> None:
        self.action = WebSearchAction.coerce(action)
        self.query = str(query)

    def complete(self) -> None:
        self.completed = True

    def display_lines(self, width: int) -> list[Line]:
        header = web_search_header(self.completed)
        detail = web_search_detail(self.action, self.query)
        text = header if detail == "" else f"{header} {detail}"
        return PrefixedWrappedHistoryCell.new(text, SEARCH_BULLET, "  ").display_lines(width)

    def raw_lines(self) -> list[Line]:
        header = web_search_header(self.completed)
        detail = web_search_detail(self.action, self.query)
        return [Line.from_text(header if detail == "" else f"{header} {detail}")]


def new_active_web_search_call(
    call_id: str, query: str, animations_enabled: bool
) -> WebSearchCell:
    return WebSearchCell.new(call_id, query, None, animations_enabled)


def new_web_search_call(
    call_id: str, query: str, action: WebSearchAction | dict[str, Any] | Any
) -> WebSearchCell:
    cell = WebSearchCell.new(call_id, query, action, False)
    cell.complete()
    return cell


def display_lines(cell: WebSearchCell, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: WebSearchCell) -> list[Line]:
    return cell.raw_lines()


__all__ = [
    "RUST_MODULE",
    "SEARCH_BULLET",
    "WebSearchAction",
    "WebSearchActionKind",
    "WebSearchCell",
    "display_lines",
    "line_text",
    "new_active_web_search_call",
    "new_web_search_call",
    "raw_lines",
    "web_search_action_detail",
    "web_search_detail",
    "web_search_header",
]
