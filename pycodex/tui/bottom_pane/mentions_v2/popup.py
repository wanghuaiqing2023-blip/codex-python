"""Semantic popup state for Rust ``bottom_pane/mentions_v2/popup.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from ..._porting import RustTuiModule
from ..popup_consts import MAX_POPUP_ROWS
from ..scroll_state import ScrollState
from .candidate import Candidate, SearchResult, Selection
from .filter import filtered_candidates
from .render import RenderedPopup, render_popup
from .search_mode import SearchMode

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::popup",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/popup.rs",
)


@dataclass
class FileSearch:
    """State mirror for Rust's private ``FileSearch`` helper."""

    pending_query: str = ""
    display_query: str = ""
    waiting: bool = False
    matches: list[Any] = field(default_factory=list)

    def set_query(self, query: str) -> None:
        if query == "":
            self.pending_query = ""
            self.display_query = ""
            self.waiting = False
            self.matches.clear()
        elif query != self.pending_query:
            self.pending_query = str(query)
            self.waiting = True

    def set_matches(self, query: str, matches: Iterable[Any]) -> None:
        if query != self.pending_query:
            return
        self.display_query = str(query)
        self.matches = list(matches)[:MAX_POPUP_ROWS]
        self.waiting = False

    def should_show_matches(self) -> bool:
        return bool(self.matches)

    def empty_message(self) -> str:
        return "loading..." if self.waiting else "no matches"


@dataclass
class Popup:
    query: str = ""
    file_search: FileSearch = field(default_factory=FileSearch)
    candidates: list[Candidate] = field(default_factory=list)
    search_mode: SearchMode = SearchMode.RESULTS
    state: ScrollState = field(default_factory=ScrollState.new)

    @classmethod
    def new(cls, candidates: Iterable[Candidate]) -> "Popup":
        return cls(candidates=list(candidates))

    def set_candidates(self, candidates: Iterable[Candidate]) -> None:
        self.candidates = list(candidates)
        self.clamp_selection()

    def set_query(self, query: str) -> None:
        self.query = str(query)
        self.file_search.set_query(self.query)
        self.clamp_selection()

    def set_file_matches(self, query: str, matches: Iterable[Any]) -> None:
        self.file_search.set_matches(str(query), matches)
        self.clamp_selection()

    def selected(self) -> Selection | None:
        idx = self.state.selected_idx
        if idx is None:
            return None
        rows = self.rows()
        if idx < 0 or idx >= len(rows):
            return None
        return rows[idx].selection

    def move_up(self) -> None:
        length = len(self.rows())
        self.state.move_up_wrap(length)
        self.state.ensure_visible(length, min(MAX_POPUP_ROWS, length))

    def move_down(self) -> None:
        length = len(self.rows())
        self.state.move_down_wrap(length)
        self.state.ensure_visible(length, min(MAX_POPUP_ROWS, length))

    def previous_search_mode(self) -> None:
        self.search_mode = self.search_mode.previous()
        self.clamp_selection()

    def next_search_mode(self) -> None:
        self.search_mode = self.search_mode.next()
        self.clamp_selection()

    def calculate_required_height(self, _width: int) -> int:
        return MAX_POPUP_ROWS + 2

    def clamp_selection(self) -> None:
        length = len(self.rows())
        self.state.clamp_selection(length)
        self.state.ensure_visible(length, min(MAX_POPUP_ROWS, length))

    def rows(self) -> list[SearchResult]:
        return filtered_candidates(
            self.candidates,
            self.file_search.matches,
            self.query,
            self.search_mode,
            self.file_search.should_show_matches(),
        )

    def render_ref(self, area: Any, buf: Any = None) -> RenderedPopup:
        return render_popup(
            area,
            [] if buf is None else buf,
            self.rows(),
            self.state,
            self.file_search.empty_message(),
            self.search_mode,
        )


def render_ref(popup: Popup, area: Any, buf: Any = None) -> RenderedPopup:
    return popup.render_ref(area, buf)


__all__ = [
    "FileSearch",
    "Popup",
    "RUST_MODULE",
    "render_ref",
]
