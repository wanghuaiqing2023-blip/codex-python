"""Behavior port for Rust ``codex-tui::bottom_pane::chat_composer::history_search``.

This module keeps the Rust module's local, independently measurable behavior:
history-search session state, visible footer semantics, status transitions, and
case-insensitive UTF-8 byte-range matching. Full ``ChatComposer`` key handling
remains owned by the larger composer module boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Sequence

from ..._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::history_search",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/history_search.rs",
)


class HistorySearchStatus(Enum):
    """Rust ``HistorySearchStatus`` variants."""

    IDLE = "Idle"
    SEARCHING = "Searching"
    MATCH = "Match"
    NO_MATCH = "NoMatch"


@dataclass
class HistorySearchSession:
    """Rust ``HistorySearchSession`` state.

    ``original_draft`` is intentionally duck-typed: its concrete type is owned by
    ``draft_state.rs``/``ChatComposer``. The history-search module only stores it
    so cancel-like flows can restore it.
    """

    original_draft: Any = None
    query: str = ""
    status: HistorySearchStatus = HistorySearchStatus.IDLE


@dataclass(frozen=True)
class Span:
    """Small semantic replacement for ratatui ``Span`` used by footer tests."""

    text: str
    style: str = "plain"


@dataclass(frozen=True)
class Line:
    """Small semantic replacement for ratatui ``Line``."""

    spans: tuple[Span, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


def is_history_search_active(session: HistorySearchSession | None) -> bool:
    """Return whether a history-search session is open."""

    return session is not None


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _folded_spans(text: str) -> tuple[bytes, list[tuple[int, int, int, int]]]:
    """Return folded UTF-8 bytes and folded-byte to original-byte spans.

    Rust lowers each ``char`` and keeps byte ranges in the original string. This
    matters for characters such as ``İ`` whose lowercase representation expands
    to multiple Unicode scalars. Every lowered scalar maps back to the original
    character byte range.
    """

    folded_parts: list[str] = []
    spans: list[tuple[int, int, int, int]] = []
    folded_byte_pos = 0
    original_byte_pos = 0

    for char in text:
        original_start = original_byte_pos
        original_end = original_start + _utf8_len(char)
        lowered = char.lower()
        for lowered_char in lowered:
            folded_start = folded_byte_pos
            folded_byte_pos += _utf8_len(lowered_char)
            spans.append((folded_start, folded_byte_pos, original_start, original_end))
            folded_parts.append(lowered_char)
        original_byte_pos = original_end

    return "".join(folded_parts).encode("utf-8"), spans


def case_insensitive_match_ranges(text: str, query: str) -> list[tuple[int, int]]:
    """Return UTF-8 byte ranges for case-insensitive matches.

    This mirrors Rust ``case_insensitive_match_ranges``: matching happens in the
    lowercased/folded byte stream, while returned ranges are byte offsets in the
    original text.
    """

    if not query:
        return []

    query_bytes = query.lower().encode("utf-8")
    if not query_bytes:
        return []

    folded_bytes, spans = _folded_spans(text)
    ranges: list[tuple[int, int]] = []
    search_from = 0

    while search_from <= len(folded_bytes):
        found_at = folded_bytes.find(query_bytes, search_from)
        if found_at < 0:
            break
        found_end = found_at + len(query_bytes)
        overlapping = [
            span
            for span in spans
            if span[1] > found_at and span[0] < found_end
        ]
        if overlapping:
            ranges.append((overlapping[0][2], overlapping[-1][3]))
        search_from = found_end

    return ranges


def history_search_footer_line(session: HistorySearchSession) -> Line:
    """Build the visible footer line for an active history search."""

    spans: list[Span] = [
        Span("reverse-i-search: ", "dim"),
        Span(session.query, "cyan"),
    ]

    if session.status is HistorySearchStatus.SEARCHING:
        spans.append(Span("  searching", "dim"))
    elif session.status is HistorySearchStatus.MATCH:
        spans.extend(
            [
                Span("  ", "dim"),
                Span("enter", "cyan+bold+not_dim"),
                Span(" accept", "dim"),
                Span(" 路 ", "dim"),
                Span("esc", "cyan+bold+not_dim"),
                Span(" cancel", "dim"),
            ]
        )
    elif session.status is HistorySearchStatus.NO_MATCH:
        spans.append(Span("  no match", "red"))

    return Line(tuple(spans))


def history_search_highlight_ranges(
    session: HistorySearchSession | None,
    text: str,
) -> list[tuple[int, int]]:
    """Return visible match highlight byte ranges while a match is previewed."""

    if session is None:
        return []
    if session.status is not HistorySearchStatus.MATCH:
        return []
    if not session.query:
        return []
    return case_insensitive_match_ranges(text, session.query)


def status_for_history_result(result: Any) -> HistorySearchStatus:
    """Map a Rust-like history search result kind to footer/search status.

    Accepted result kinds are ``Found``, ``AtBoundary``, ``Pending`` and
    ``NotFound`` as strings or objects with ``kind``/``type``/``name`` fields.
    """

    kind = _result_kind(result)
    if kind in {"Found", "AtBoundary"}:
        return HistorySearchStatus.MATCH
    if kind == "Pending":
        return HistorySearchStatus.SEARCHING
    if kind == "NotFound":
        return HistorySearchStatus.NO_MATCH
    raise ValueError(f"unknown history search result kind: {kind!r}")


def apply_history_search_result(
    session: HistorySearchSession,
    result: Any,
) -> HistorySearchSession:
    """Return a new session with status updated from a search result."""

    return HistorySearchSession(
        original_draft=session.original_draft,
        query=session.query,
        status=status_for_history_result(result),
    )


def _result_kind(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, dict):
        for key in ("kind", "type", "name"):
            value = result.get(key)
            if value is not None:
                return str(value)
    for attr in ("kind", "type", "name"):
        value = getattr(result, attr, None)
        if value is not None:
            if isinstance(value, Enum):
                return str(value.value)
            return str(value)
    if isinstance(result, Enum):
        return str(result.value)
    return str(result)


# Rust test-name scaffold functions retained as explicit boundaries for the
# larger ChatComposer lifecycle tests that are not owned solely by this module.
def history_search_opens_without_previewing_latest_entry(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_opens_without_previewing_latest_entry")


def history_search_match_ranges_are_case_insensitive(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_match_ranges_are_case_insensitive")


def history_search_accepts_matching_entry(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_accepts_matching_entry")


def vim_normal_history_search_preview_places_cursor_on_last_char(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "vim_normal_history_search_preview_places_cursor_on_last_char")


def history_search_stays_on_single_match_at_boundaries(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_stays_on_single_match_at_boundaries")


def history_search_footer_action_hints_are_emphasized(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_footer_action_hints_are_emphasized")


def history_search_highlights_matches_until_accepted(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_highlights_matches_until_accepted")


def history_search_esc_restores_original_draft(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_esc_restores_original_draft")


def history_search_ctrl_c_restores_original_draft(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_ctrl_c_restores_original_draft")


def composer_with_search_preview(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "composer_with_search_preview")


def history_search_flushes_pending_first_char_before_snapshot(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_flushes_pending_first_char_before_snapshot")


def history_search_flushes_buffered_paste_before_snapshot(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_flushes_buffered_paste_before_snapshot")


def history_search_esc_resets_normal_history_navigation(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_esc_resets_normal_history_navigation")


def history_search_no_match_restores_preview_but_keeps_search_open(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "history_search_no_match_restores_preview_but_keeps_search_open")


__all__ = [
    "HistorySearchSession",
    "HistorySearchStatus",
    "Line",
    "RUST_MODULE",
    "Span",
    "apply_history_search_result",
    "case_insensitive_match_ranges",
    "composer_with_search_preview",
    "history_search_accepts_matching_entry",
    "history_search_ctrl_c_restores_original_draft",
    "history_search_esc_resets_normal_history_navigation",
    "history_search_esc_restores_original_draft",
    "history_search_flushes_buffered_paste_before_snapshot",
    "history_search_flushes_pending_first_char_before_snapshot",
    "history_search_footer_action_hints_are_emphasized",
    "history_search_footer_line",
    "history_search_highlight_ranges",
    "history_search_highlights_matches_until_accepted",
    "history_search_match_ranges_are_case_insensitive",
    "history_search_no_match_restores_preview_but_keeps_search_open",
    "history_search_opens_without_previewing_latest_entry",
    "history_search_stays_on_single_match_at_boundaries",
    "is_history_search_active",
    "status_for_history_result",
    "vim_normal_history_search_preview_places_cursor_on_last_char",
]
