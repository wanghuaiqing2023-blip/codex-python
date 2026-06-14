"""Semantic port of Rust ``bottom_pane/file_search_popup.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .._porting import RustTuiModule
from .popup_consts import MAX_POPUP_ROWS
from .scroll_state import ScrollState

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::file_search_popup",
    source="codex/codex-rs/tui/src/bottom_pane/file_search_popup.rs",
)


@dataclass(frozen=True)
class FileMatch:
    score: int
    path: Path
    match_type: str = "File"
    root: Path | None = None
    indices: list[int] | None = None


@dataclass(frozen=True)
class GenericDisplayRow:
    name: str
    match_indices: list[int] | None = None
    description: str | None = None
    category_tag: str | None = None
    is_disabled: bool = False
    disabled_reason: str | None = None


@dataclass(frozen=True)
class RenderedFileSearchPopup:
    rows: tuple[GenericDisplayRow, ...]
    selected_idx: int | None
    scroll_top: int
    empty_message: str
    max_rows: int = MAX_POPUP_ROWS


@dataclass
class FileSearchPopup:
    display_query: str = ""
    pending_query: str = ""
    waiting: bool = True
    matches: list[FileMatch] = field(default_factory=list)
    state: ScrollState = field(default_factory=ScrollState.new)

    @classmethod
    def new(cls) -> "FileSearchPopup":
        return cls()

    def set_query(self, query: str) -> None:
        query = str(query)
        if query == self.pending_query:
            return
        self.pending_query = query
        self.waiting = True

    def set_empty_prompt(self) -> None:
        self.display_query = ""
        self.pending_query = ""
        self.waiting = False
        self.matches.clear()
        self.state.reset()

    def set_matches(self, query: str, matches: Iterable[Any]) -> None:
        query = str(query)
        if query != self.pending_query:
            return
        self.display_query = query
        self.matches = [_coerce_file_match(match) for match in matches][:MAX_POPUP_ROWS]
        self.waiting = False
        length = len(self.matches)
        self.state.clamp_selection(length)
        self.state.ensure_visible(length, min(length, MAX_POPUP_ROWS))

    def move_up(self) -> None:
        length = len(self.matches)
        self.state.move_up_wrap(length)
        self.state.ensure_visible(length, min(length, MAX_POPUP_ROWS))

    def move_down(self) -> None:
        length = len(self.matches)
        self.state.move_down_wrap(length)
        self.state.ensure_visible(length, min(length, MAX_POPUP_ROWS))

    def selected_match(self) -> Path | None:
        idx = self.state.selected_idx
        if idx is None or idx < 0 or idx >= len(self.matches):
            return None
        return self.matches[idx].path

    def calculate_required_height(self) -> int:
        return max(1, min(len(self.matches), MAX_POPUP_ROWS))

    def rows(self) -> list[GenericDisplayRow]:
        return [
            GenericDisplayRow(
                name=str(match.path),
                match_indices=None if match.indices is None else list(match.indices),
            )
            for match in self.matches
        ]

    def empty_message(self) -> str:
        return "loading..." if self.waiting else "no matches"

    def render_ref(self, area: Any = None, buf: Any = None) -> RenderedFileSearchPopup:
        del area
        rendered = RenderedFileSearchPopup(
            rows=tuple(self.rows()),
            selected_idx=self.state.selected_idx,
            scroll_top=self.state.scroll_top,
            empty_message=self.empty_message(),
        )
        if isinstance(buf, list):
            buf.append(rendered)
        return rendered


def render_ref(popup: FileSearchPopup, area: Any = None, buf: Any = None) -> RenderedFileSearchPopup:
    return popup.render_ref(area, buf)


def file_match(index: int) -> FileMatch:
    return FileMatch(
        score=int(index),
        path=Path(f"src/file_{int(index):02}.rs"),
        match_type="File",
        root=Path("/tmp/repo"),
        indices=None,
    )


def _coerce_file_match(value: Any) -> FileMatch:
    if isinstance(value, FileMatch):
        return value
    if isinstance(value, dict):
        path = value.get("path", "")
        score = value.get("score", 0)
        match_type = value.get("match_type", "File")
        root = value.get("root")
        indices = value.get("indices")
    else:
        path = getattr(value, "path", "")
        score = getattr(value, "score", 0)
        match_type = getattr(value, "match_type", "File")
        root = getattr(value, "root", None)
        indices = getattr(value, "indices", None)
    return FileMatch(
        score=int(score),
        path=Path(path),
        match_type=str(match_type),
        root=None if root is None else Path(root),
        indices=None if indices is None else [int(index) for index in indices],
    )


__all__ = [
    "FileMatch",
    "FileSearchPopup",
    "GenericDisplayRow",
    "RUST_MODULE",
    "RenderedFileSearchPopup",
    "file_match",
    "render_ref",
]
