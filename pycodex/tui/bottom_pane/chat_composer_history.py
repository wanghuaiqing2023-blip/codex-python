"""Behavior port for Rust ``codex-tui::bottom_pane::chat_composer_history``.

This module owns shell-style composer history navigation and incremental search.
Python keeps the same combined offset space: persistent entries first, local
session entries after them, with newest entries at the highest offsets.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from pycodex.protocol.user_input import TextElement

from . import MentionBinding
from ..mention_codec import decode_history_mentions
from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::chat_composer_history",
    source="codex/codex-rs/tui/src/bottom_pane/chat_composer_history.rs",
    status="complete",
)


@dataclass(eq=True)
class HistoryEntry:
    """A composer history entry that can rehydrate draft state."""

    text: str = ""
    text_elements: List[TextElement] = field(default_factory=list)
    local_image_paths: List[Path] = field(default_factory=list)
    remote_image_urls: List[str] = field(default_factory=list)
    mention_bindings: List[Any] = field(default_factory=list)
    pending_pastes: List[Tuple[str, str]] = field(default_factory=list)

    @classmethod
    def new(cls, text: str) -> "HistoryEntry":
        decoded = decode_history_mentions(text)
        return cls(
            text=decoded.text,
            mention_bindings=[
                MentionBinding(mention=mention.mention, path=mention.path)
                for mention in decoded.mentions
            ],
        )

    @classmethod
    def with_pending(
        cls,
        text: str,
        text_elements: Iterable[TextElement],
        local_image_paths: Iterable[Any],
        pending_pastes: Iterable[Tuple[str, str]],
    ) -> "HistoryEntry":
        return cls(
            text=text,
            text_elements=list(text_elements),
            local_image_paths=[Path(path) for path in local_image_paths],
            pending_pastes=list(pending_pastes),
        )

    @classmethod
    def with_pending_and_remote(
        cls,
        text: str,
        text_elements: Iterable[TextElement],
        local_image_paths: Iterable[Any],
        pending_pastes: Iterable[Tuple[str, str]],
        remote_image_urls: Iterable[str],
    ) -> "HistoryEntry":
        return cls(
            text=text,
            text_elements=list(text_elements),
            local_image_paths=[Path(path) for path in local_image_paths],
            remote_image_urls=list(remote_image_urls),
            pending_pastes=list(pending_pastes),
        )

    def is_empty_submission(self) -> bool:
        return (
            not self.text
            and not self.text_elements
            and not self.local_image_paths
            and not self.remote_image_urls
            and not self.mention_bindings
            and not self.pending_pastes
        )


class HistorySearchDirection(Enum):
    OLDER = "Older"
    NEWER = "Newer"


@dataclass(frozen=True)
class HistorySearchResult:
    kind: str
    entry: Optional[HistoryEntry] = None

    @classmethod
    def found(cls, entry: HistoryEntry) -> "HistorySearchResult":
        return cls("Found", entry)

    @classmethod
    def pending(cls) -> "HistorySearchResult":
        return cls("Pending")

    @classmethod
    def at_boundary(cls) -> "HistorySearchResult":
        return cls("AtBoundary")

    @classmethod
    def not_found(cls) -> "HistorySearchResult":
        return cls("NotFound")


HistorySearchResult.PENDING = HistorySearchResult.pending()  # type: ignore[attr-defined]
HistorySearchResult.AT_BOUNDARY = HistorySearchResult.at_boundary()  # type: ignore[attr-defined]
HistorySearchResult.NOT_FOUND = HistorySearchResult.not_found()  # type: ignore[attr-defined]


@dataclass(frozen=True)
class HistoryEntryResponse:
    kind: str
    entry: Optional[HistoryEntry] = None
    search_result: Optional[HistorySearchResult] = None

    @classmethod
    def found(cls, entry: HistoryEntry) -> "HistoryEntryResponse":
        return cls("Found", entry=entry)

    @classmethod
    def search(cls, result: HistorySearchResult) -> "HistoryEntryResponse":
        return cls("Search", search_result=result)

    @classmethod
    def ignored(cls) -> "HistoryEntryResponse":
        return cls("Ignored")


HistoryEntryResponse.IGNORED = HistoryEntryResponse.ignored()  # type: ignore[attr-defined]


@dataclass
class UniqueHistoryMatch:
    offset: int
    entry: HistoryEntry


@dataclass
class PendingHistorySearch:
    offset: int
    direction: HistorySearchDirection
    boundary_if_exhausted: bool


@dataclass
class HistorySearchState:
    query: str
    query_lower: str
    selected_offset: Optional[int] = None
    unique_matches: List[UniqueHistoryMatch] = field(default_factory=list)
    selected_match_index: Optional[int] = None
    seen_texts: Set[str] = field(default_factory=set)
    awaiting: Optional[PendingHistorySearch] = None
    exhausted_older: bool = False
    exhausted_newer: bool = False

    @classmethod
    def new(cls, query: str) -> "HistorySearchState":
        return cls(query=query, query_lower=query.lower())

    def is_exhausted(self, direction: HistorySearchDirection) -> bool:
        return self.exhausted_older if direction is HistorySearchDirection.OLDER else self.exhausted_newer

    def mark_exhausted(self, direction: HistorySearchDirection) -> None:
        if direction is HistorySearchDirection.OLDER:
            self.exhausted_older = True
        else:
            self.exhausted_newer = True

    def record_match(self, offset: int, entry: HistoryEntry) -> None:
        for index, history_match in enumerate(self.unique_matches):
            if history_match.offset == offset:
                self.select_match(index)
                return
        self.seen_texts.add(entry.text)
        insert_index = 0
        while insert_index < len(self.unique_matches) and self.unique_matches[insert_index].offset > offset:
            insert_index += 1
        self.unique_matches.insert(insert_index, UniqueHistoryMatch(offset=offset, entry=entry))
        self.select_match(insert_index)

    def select_match(self, index: int) -> None:
        if index < 0 or index >= len(self.unique_matches):
            return
        history_match = self.unique_matches[index]
        self.selected_offset = history_match.offset
        self.selected_match_index = index
        self.awaiting = None
        self.exhausted_older = False
        self.exhausted_newer = False


@dataclass
class ChatComposerHistory:
    thread_id: Any = None
    persistent_log_id: Optional[int] = None
    persistent_entry_count: int = 0
    local_history: List[HistoryEntry] = field(default_factory=list)
    fetched_history: Dict[int, HistoryEntry] = field(default_factory=dict)
    history_cursor: Optional[int] = None
    last_history_text: Optional[str] = None
    search_state: Optional[HistorySearchState] = None

    @classmethod
    def new(cls) -> "ChatComposerHistory":
        return cls()

    def set_metadata(self, thread_id: Any, log_id: int, entry_count: int) -> None:
        self.thread_id = thread_id
        self.persistent_log_id = log_id
        self.persistent_entry_count = entry_count
        self.fetched_history.clear()
        self.local_history.clear()
        self.history_cursor = None
        self.last_history_text = None
        self.search_state = None

    def record_local_submission(self, entry: HistoryEntry) -> None:
        if entry.is_empty_submission():
            return
        self.history_cursor = None
        self.last_history_text = None
        self.search_state = None
        if self.local_history and self.local_history[-1] == entry:
            return
        self.local_history.append(entry)

    def reset_navigation(self) -> None:
        self.history_cursor = None
        self.last_history_text = None
        self.search_state = None

    def reset_search(self) -> None:
        self.search_state = None

    def should_handle_navigation(self, text: str, cursor: int) -> bool:
        if self.persistent_entry_count == 0 and not self.local_history:
            return False
        if not text:
            return True
        if cursor != 0 and cursor != len(text.encode("utf-8")):
            return False
        return self.last_history_text == text

    def navigate_up(self, app_event_tx: Any = None) -> Optional[HistoryEntry]:
        self.search_state = None
        total_entries = self.total_entries()
        if total_entries == 0:
            return None
        if self.history_cursor is None:
            next_idx = total_entries - 1
        elif self.history_cursor == 0:
            return None
        else:
            next_idx = self.history_cursor - 1
        self.history_cursor = next_idx
        return self.populate_history_at_index(next_idx, app_event_tx)

    def navigate_down(self, app_event_tx: Any = None) -> Optional[HistoryEntry]:
        self.search_state = None
        total_entries = self.total_entries()
        if total_entries == 0 or self.history_cursor is None:
            return None
        if self.history_cursor + 1 >= total_entries:
            self.history_cursor = None
            self.last_history_text = None
            return HistoryEntry.new("")
        self.history_cursor += 1
        return self.populate_history_at_index(self.history_cursor, app_event_tx)

    def on_entry_response(
        self,
        log_id: int,
        offset: int,
        entry: Optional[str],
        app_event_tx: Any = None,
    ) -> HistoryEntryResponse:
        if self.persistent_log_id != log_id:
            return HistoryEntryResponse.IGNORED

        history_entry = HistoryEntry.new(entry) if entry is not None else None
        if history_entry is not None:
            self.fetched_history[offset] = history_entry

        pending = self.search_state.awaiting if self.search_state is not None else None
        if pending is not None and pending.offset == offset:
            if history_entry is not None and self.search_matches(history_entry) and self.search_result_is_unique(history_entry):
                return HistoryEntryResponse.search(self.search_match(offset, history_entry))
            return HistoryEntryResponse.search(
                self.advance_search_after(offset, pending.direction, pending.boundary_if_exhausted, app_event_tx)
            )

        if self.history_cursor == offset:
            if history_entry is None:
                return HistoryEntryResponse.IGNORED
            self.last_history_text = history_entry.text
            return HistoryEntryResponse.found(history_entry)

        return HistoryEntryResponse.IGNORED

    def search(
        self,
        query: str,
        direction: HistorySearchDirection,
        restart: bool,
        app_event_tx: Any = None,
    ) -> HistorySearchResult:
        if self.total_entries() == 0:
            self.search_state = HistorySearchState.new(query)
            return HistorySearchResult.NOT_FOUND

        query_changed = self.search_state is None or self.search_state.query != query
        if not query_changed and not restart and self.search_state is not None and self.search_state.awaiting is not None:
            return HistorySearchResult.PENDING

        if query_changed or restart or self.search_state is None:
            self.search_state = HistorySearchState.new(query)

        if self.search_state.is_exhausted(direction):
            return self.exhausted_search_result(direction)

        cached = self.select_cached_unique_match(direction)
        if cached is not None and not restart:
            return cached

        start_offset = self.search_start_offset(direction)
        if start_offset is None:
            return self.exhausted_search_result(direction)
        return self.advance_search_from(start_offset, direction, bool(self.search_state.selected_offset is not None), app_event_tx)

    def total_entries(self) -> int:
        return self.persistent_entry_count + len(self.local_history)

    def search_start_offset(self, direction: HistorySearchDirection) -> Optional[int]:
        if self.search_state is None:
            return None
        if self.search_state.selected_offset is None:
            return self.total_entries() - 1 if direction is HistorySearchDirection.OLDER else 0
        if direction is HistorySearchDirection.OLDER:
            next_offset = self.search_state.selected_offset - 1
            return next_offset if next_offset >= 0 else None
        next_offset = self.search_state.selected_offset + 1
        return next_offset if next_offset < self.total_entries() else None

    def advance_search_after(
        self,
        offset: int,
        direction: HistorySearchDirection,
        boundary_if_exhausted: bool,
        app_event_tx: Any = None,
    ) -> HistorySearchResult:
        next_offset = offset - 1 if direction is HistorySearchDirection.OLDER else offset + 1
        if next_offset < 0 or next_offset >= self.total_entries():
            if self.search_state is not None:
                self.search_state.awaiting = None
                self.search_state.mark_exhausted(direction)
            if boundary_if_exhausted and self.search_state is not None and self.search_state.selected_offset is not None:
                return HistorySearchResult.AT_BOUNDARY
            return HistorySearchResult.NOT_FOUND
        return self.advance_search_from(next_offset, direction, boundary_if_exhausted, app_event_tx)

    def advance_search_from(
        self,
        offset: int,
        direction: HistorySearchDirection,
        boundary_if_exhausted: bool,
        app_event_tx: Any = None,
    ) -> HistorySearchResult:
        current = offset
        while 0 <= current < self.total_entries():
            entry = self.entry_at_cached_offset(current)
            if entry is None:
                self._request_persistent_offset(current, app_event_tx)
                if self.search_state is not None:
                    self.search_state.awaiting = PendingHistorySearch(current, direction, boundary_if_exhausted)
                return HistorySearchResult.PENDING
            if self.search_matches(entry) and self.search_result_is_unique(entry):
                return self.search_match(current, entry)
            current = current - 1 if direction is HistorySearchDirection.OLDER else current + 1

        if self.search_state is not None:
            self.search_state.awaiting = None
            self.search_state.mark_exhausted(direction)
        if boundary_if_exhausted and self.search_state is not None and self.search_state.selected_offset is not None:
            return HistorySearchResult.AT_BOUNDARY
        return HistorySearchResult.NOT_FOUND

    def entry_at_cached_offset(self, offset: int) -> Optional[HistoryEntry]:
        if offset < 0 or offset >= self.total_entries():
            return None
        if offset >= self.persistent_entry_count:
            return self.local_history[offset - self.persistent_entry_count]
        return self.fetched_history.get(offset)

    def search_matches(self, entry: HistoryEntry) -> bool:
        if self.search_state is None:
            return False
        return self.search_state.query_lower in entry.text.lower()

    def search_result_is_unique(self, entry: HistoryEntry) -> bool:
        if self.search_state is None:
            return False
        return entry.text not in self.search_state.seen_texts

    def search_match(self, offset: int, entry: HistoryEntry) -> HistorySearchResult:
        if self.search_state is None:
            return HistorySearchResult.NOT_FOUND
        self.search_state.record_match(offset, entry)
        return HistorySearchResult.found(entry)

    def select_cached_unique_match(self, direction: HistorySearchDirection) -> Optional[HistorySearchResult]:
        if self.search_state is None or self.search_state.selected_match_index is None:
            return None
        next_index = self.search_state.selected_match_index + (1 if direction is HistorySearchDirection.OLDER else -1)
        if 0 <= next_index < len(self.search_state.unique_matches):
            self.search_state.select_match(next_index)
            return HistorySearchResult.found(self.search_state.unique_matches[next_index].entry)
        return None

    def exhausted_search_result(self, direction: HistorySearchDirection) -> HistorySearchResult:
        if self.search_state is not None:
            self.search_state.mark_exhausted(direction)
            if self.search_state.selected_offset is not None:
                return HistorySearchResult.AT_BOUNDARY
        return HistorySearchResult.NOT_FOUND

    def populate_history_at_index(self, idx: int, app_event_tx: Any = None) -> Optional[HistoryEntry]:
        entry = self.entry_at_cached_offset(idx)
        if entry is not None:
            self.last_history_text = entry.text
            return entry
        self._request_persistent_offset(idx, app_event_tx)
        return None

    def _request_persistent_offset(self, offset: int, app_event_tx: Any = None) -> None:
        if offset < 0 or offset >= self.persistent_entry_count:
            return
        if self.thread_id is None or self.persistent_log_id is None:
            return
        event = {
            "type": "LookupMessageHistoryEntry",
            "thread_id": self.thread_id,
            "offset": offset,
            "log_id": self.persistent_log_id,
        }
        if app_event_tx is None:
            return
        if hasattr(app_event_tx, "send"):
            app_event_tx.send(event)
        elif hasattr(app_event_tx, "append"):
            app_event_tx.append(event)
        elif callable(app_event_tx):
            app_event_tx(event)


__all__ = [
    "ChatComposerHistory",
    "HistoryEntry",
    "HistoryEntryResponse",
    "HistorySearchDirection",
    "HistorySearchResult",
    "HistorySearchState",
    "PendingHistorySearch",
    "RUST_MODULE",
    "UniqueHistoryMatch",
]

