"""Web-search display helpers ported from Codex core.

This mirrors ``codex-rs/core/src/web_search.rs``.
"""

from __future__ import annotations

from pycodex.protocol import WebSearchAction


def _search_action_detail(query: str | None, queries: tuple[str, ...] | None) -> str:
    if query:
        return query

    first = queries[0] if queries else ""
    if queries is not None and len(queries) > 1 and first:
        return f"{first} ..."
    return first


def web_search_action_detail(action: WebSearchAction) -> str:
    if action.type == "search":
        return _search_action_detail(action.query, action.queries)
    if action.type == "open_page":
        return action.url or ""
    if action.type == "find_in_page":
        if action.pattern is not None and action.url is not None:
            return f"'{action.pattern}' in {action.url}"
        if action.pattern is not None:
            return f"'{action.pattern}'"
        if action.url is not None:
            return action.url
        return ""
    return ""


def web_search_detail(action: WebSearchAction | None, query: str) -> str:
    detail = web_search_action_detail(action) if action is not None else ""
    return query if detail == "" else detail


__all__ = [
    "web_search_action_detail",
    "web_search_detail",
]
