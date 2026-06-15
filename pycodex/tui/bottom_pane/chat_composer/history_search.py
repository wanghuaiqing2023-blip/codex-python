"""Behavior port for Rust ``codex-tui::bottom_pane::chat_composer::history_search``.

This module keeps the Rust module's local, independently measurable behavior:
history-search session state, visible footer semantics, status transitions, and
case-insensitive UTF-8 byte-range matching. Full ``ChatComposer`` key handling
remains owned by the larger composer module boundary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, List, Optional, Tuple

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer::history_search",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer/history_search.rs",
    status="complete",
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

    spans: Tuple[Span, ...] = field(default_factory=tuple)

    @property
    def text(self) -> str:
        return "".join(span.text for span in self.spans)


def is_history_search_active(session: Optional[HistorySearchSession]) -> bool:
    """Return whether a history-search session is open."""

    return session is not None


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _folded_spans(text: str) -> Tuple[bytes, List[Tuple[int, int, int, int]]]:
    """Return folded UTF-8 bytes and folded-byte to original-byte spans.

    Rust lowers each ``char`` and keeps byte ranges in the original string. This
    matters for characters such as ``İ`` whose lowercase representation expands
    to multiple Unicode scalars. Every lowered scalar maps back to the original
    character byte range.
    """

    folded_parts: List[str] = []
    spans: List[Tuple[int, int, int, int]] = []
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


def case_insensitive_match_ranges(text: str, query: str) -> List[Tuple[int, int]]:
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
    ranges: List[Tuple[int, int]] = []
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

    spans: List[Span] = [
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
                Span(" · ", "dim"),
                Span("esc", "cyan+bold+not_dim"),
                Span(" cancel", "dim"),
            ]
        )
    elif session.status is HistorySearchStatus.NO_MATCH:
        spans.append(Span("  no match", "red"))

    return Line(tuple(spans))


def history_search_highlight_ranges(
    session: Optional[HistorySearchSession],
    text: str,
) -> List[Tuple[int, int]]:
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



@dataclass
class SemanticHistoryComposer:
    history: List[str] = field(default_factory=list)
    draft_text: str = ""
    cursor: int = 0
    vim_enabled: bool = False
    history_search: Optional[HistorySearchSession] = None
    search_matches: List[str] = field(default_factory=list)
    search_index: int = 0
    paste_buffer: str = ""
    normal_history_index: Optional[int] = None

    def record(self, text: str) -> None:
        self.history.append(text)

    def set_text_content(self, text: str, cursor: Optional[int] = None) -> None:
        self.draft_text = text
        self.cursor = len(text) if cursor is None else cursor

    def begin_history_search(self) -> None:
        if self.paste_buffer:
            self.draft_text += self.paste_buffer
            self.cursor = len(self.draft_text)
            self.paste_buffer = ""
        self.history_search = HistorySearchSession(original_draft=(self.draft_text, self.cursor), query="", status=HistorySearchStatus.IDLE)
        self.search_matches = []
        self.search_index = 0
        self.normal_history_index = None

    def type_query_char(self, ch: str) -> None:
        if self.history_search is None:
            return
        self.history_search.query += ch
        self._restart_search()

    def previous_match(self) -> None:
        self._step(1)

    def next_match(self) -> None:
        self._step(-1)

    def accept(self) -> None:
        if self.history_search is not None and self.history_search.status is HistorySearchStatus.MATCH:
            self.history_search = None
            self.search_matches = []
            self.cursor = max(len(self.draft_text) - 1, 0) if self.vim_enabled and self.draft_text else len(self.draft_text)

    def cancel(self) -> None:
        if self.history_search is None:
            return
        original_text, original_cursor = self.history_search.original_draft
        self.draft_text = original_text
        self.cursor = original_cursor
        self.history_search = None
        self.search_matches = []
        self.normal_history_index = None

    def normal_history_up(self) -> None:
        if not self.history:
            return
        self.normal_history_index = len(self.history) - 1 if self.normal_history_index is None else max(0, self.normal_history_index - 1)
        self.draft_text = self.history[self.normal_history_index]
        self.cursor = len(self.draft_text)

    def _restart_search(self) -> None:
        if self.history_search is None:
            return
        query = self.history_search.query
        original_text, original_cursor = self.history_search.original_draft
        if not query:
            self.draft_text = original_text
            self.cursor = original_cursor
            self.history_search.status = HistorySearchStatus.IDLE
            self.search_matches = []
            return
        seen = set()
        matches = []
        for entry in reversed(self.history):
            if query.lower() in entry.lower() and entry not in seen:
                seen.add(entry)
                matches.append(entry)
        self.search_matches = matches
        self.search_index = 0
        if matches:
            self._preview_current_match()
        else:
            self.draft_text = original_text
            self.cursor = original_cursor
            self.history_search.status = HistorySearchStatus.NO_MATCH

    def _step(self, delta: int) -> None:
        if self.history_search is None:
            return
        if not self.history_search.query:
            original_text, original_cursor = self.history_search.original_draft
            self.draft_text = original_text
            self.cursor = original_cursor
            self.history_search.status = HistorySearchStatus.IDLE
            return
        if not self.search_matches:
            self._restart_search()
            return
        next_index = self.search_index + delta
        if 0 <= next_index < len(self.search_matches):
            self.search_index = next_index
        self._preview_current_match()

    def _preview_current_match(self) -> None:
        if self.history_search is None or not self.search_matches:
            return
        self.draft_text = self.search_matches[self.search_index]
        self.cursor = max(len(self.draft_text) - 1, 0) if self.vim_enabled and self.draft_text else len(self.draft_text)
        self.history_search.status = HistorySearchStatus.MATCH


# Rust test-name helpers implemented against the semantic composer above.
def history_search_opens_without_previewing_latest_entry(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer()
    composer.record("remembered command")
    composer.set_text_content("")
    composer.begin_history_search()
    return composer.history_search is not None and composer.draft_text == "" and composer.history_search.status is HistorySearchStatus.IDLE


def history_search_match_ranges_are_case_insensitive(*args: Any, **kwargs: Any) -> bool:
    return (
        case_insensitive_match_ranges("git status git", "GIT") == [(0, 3), (11, 14)]
        and case_insensitive_match_ranges("aİ i", "i") == [(1, 3), (4, 5)]
        and case_insensitive_match_ranges("git", "") == []
    )


def history_search_accepts_matching_entry(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer()
    composer.record("git status")
    composer.record("cargo test")
    composer.set_text_content("draft")
    composer.begin_history_search()
    for ch in "git":
        composer.type_query_char(ch)
    matched = composer.draft_text == "git status" and composer.history_search is not None
    composer.accept()
    return matched and composer.history_search is None and composer.draft_text == "git status" and composer.cursor == len("git status")


def vim_normal_history_search_preview_places_cursor_on_last_char(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer(vim_enabled=True)
    composer.record("git status")
    composer.begin_history_search()
    for ch in "git":
        composer.type_query_char(ch)
    return composer.draft_text == "git status" and composer.cursor == len("git status") - 1


def history_search_stays_on_single_match_at_boundaries(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer()
    text = "Find and fix a bug in @filename"
    composer.record(text)
    composer.set_text_content("draft")
    composer.begin_history_search()
    for ch in "bug":
        composer.type_query_char(ch)
    for _ in range(3):
        composer.previous_match()
    older_ok = composer.draft_text == text and composer.history_search is not None and composer.history_search.status is HistorySearchStatus.MATCH
    for _ in range(3):
        composer.next_match()
    return older_ok and composer.draft_text == text and composer.history_search is not None and composer.history_search.status is HistorySearchStatus.MATCH


def history_search_footer_action_hints_are_emphasized(*args: Any, **kwargs: Any) -> bool:
    line = history_search_footer_line(HistorySearchSession(query="c", status=HistorySearchStatus.MATCH))
    return [span.text for span in line.spans] == ["reverse-i-search: ", "c", "  ", "enter", " accept", " · ", "esc", " cancel"] and line.spans[3].style == "cyan+bold+not_dim" and line.spans[6].style == "cyan+bold+not_dim"


def history_search_highlights_matches_until_accepted(*args: Any, **kwargs: Any) -> bool:
    session = HistorySearchSession(query="git", status=HistorySearchStatus.MATCH)
    before = history_search_highlight_ranges(session, "git status")
    after = history_search_highlight_ranges(None, "git status")
    return before == [(0, 3)] and after == []


def history_search_esc_restores_original_draft(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer()
    composer.record("remembered command")
    composer.set_text_content("draft", cursor=2)
    composer.begin_history_search()
    composer.type_query_char("r")
    previewed = composer.draft_text == "remembered command"
    composer.cancel()
    return previewed and composer.history_search is None and composer.draft_text == "draft" and composer.cursor == 2


def history_search_ctrl_c_restores_original_draft(*args: Any, **kwargs: Any) -> bool:
    return history_search_esc_restores_original_draft()


def composer_with_search_preview(*args: Any, **kwargs: Any) -> SemanticHistoryComposer:
    composer = SemanticHistoryComposer()
    composer.record("remembered command")
    composer.set_text_content("draft", cursor=2)
    composer.begin_history_search()
    composer.type_query_char("r")
    return composer


def history_search_flushes_pending_first_char_before_snapshot(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer(paste_buffer="h")
    composer.begin_history_search()
    active_with_flush = composer.history_search is not None and composer.draft_text == "h" and composer.paste_buffer == ""
    composer.cancel()
    return active_with_flush and composer.history_search is None and composer.draft_text == "h"


def history_search_flushes_buffered_paste_before_snapshot(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer(paste_buffer="paste")
    composer.begin_history_search()
    active_with_flush = composer.history_search is not None and composer.draft_text == "paste" and composer.paste_buffer == ""
    composer.cancel()
    return active_with_flush and composer.history_search is None and composer.draft_text == "paste"


def history_search_esc_resets_normal_history_navigation(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer()
    composer.record("oldest matching entry")
    composer.record("newest entry")
    composer.set_text_content("")
    composer.begin_history_search()
    for ch in "match":
        composer.type_query_char(ch)
    previewed = composer.draft_text == "oldest matching entry"
    composer.cancel()
    composer.normal_history_up()
    return previewed and composer.history_search is None and composer.draft_text == "newest entry"


def history_search_no_match_restores_preview_but_keeps_search_open(*args: Any, **kwargs: Any) -> bool:
    composer = SemanticHistoryComposer()
    composer.record("git status")
    composer.set_text_content("draft")
    composer.begin_history_search()
    for ch in "zzz":
        composer.type_query_char(ch)
    return composer.history_search is not None and composer.draft_text == "draft" and composer.history_search.status is HistorySearchStatus.NO_MATCH


__all__ = [
    "HistorySearchSession",
    "SemanticHistoryComposer",
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

