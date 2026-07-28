"""Storage contract from ``codex-memories-extension/src/backend.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


class SearchMatchModeKind(str, Enum):
    ANY = "any"
    ALL_ON_SAME_LINE = "all_on_same_line"
    ALL_WITHIN_LINES = "all_within_lines"


@dataclass(frozen=True)
class SearchMatchMode:
    kind: SearchMatchModeKind
    line_count: int | None = None

    @classmethod
    def any(cls) -> "SearchMatchMode":
        return cls(SearchMatchModeKind.ANY)

    @classmethod
    def all_on_same_line(cls) -> "SearchMatchMode":
        return cls(SearchMatchModeKind.ALL_ON_SAME_LINE)

    @classmethod
    def all_within_lines(cls, line_count: int) -> "SearchMatchMode":
        return cls(SearchMatchModeKind.ALL_WITHIN_LINES, line_count)


class MemoryEntryType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class AddAdHocMemoryNoteRequest:
    filename: str
    note: str


@dataclass(frozen=True)
class AddAdHocMemoryNoteResponse:
    pass


@dataclass(frozen=True)
class ListMemoriesRequest:
    path: str | None
    cursor: str | None
    max_results: int


@dataclass(frozen=True)
class MemoryEntry:
    path: str
    entry_type: MemoryEntryType


@dataclass(frozen=True)
class ListMemoriesResponse:
    path: str | None
    entries: tuple[MemoryEntry, ...]
    next_cursor: str | None
    truncated: bool


@dataclass(frozen=True)
class ReadMemoryRequest:
    path: str
    line_offset: int
    max_lines: int | None
    max_tokens: int


@dataclass(frozen=True)
class ReadMemoryResponse:
    path: str
    start_line_number: int
    content: str
    truncated: bool


@dataclass(frozen=True)
class SearchMemoriesRequest:
    queries: tuple[str, ...]
    match_mode: SearchMatchMode
    path: str | None
    cursor: str | None
    context_lines: int
    case_sensitive: bool
    normalized: bool
    max_results: int


@dataclass(frozen=True)
class MemorySearchMatch:
    path: str
    match_line_number: int
    content_start_line_number: int
    content: str
    matched_queries: tuple[str, ...]


@dataclass(frozen=True)
class SearchMemoriesResponse:
    queries: tuple[str, ...]
    match_mode: SearchMatchMode
    path: str | None
    matches: tuple[MemorySearchMatch, ...]
    next_cursor: str | None
    truncated: bool


class MemoriesBackendError(Exception):
    @classmethod
    def invalid_filename(cls, filename: str, reason: str) -> "MemoriesBackendError":
        return cls(f"filename '{filename}' {reason}")

    @classmethod
    def invalid_path(cls, path: str, reason: str) -> "MemoriesBackendError":
        return cls(f"path '{path}' {reason}")

    @classmethod
    def invalid_cursor(cls, cursor: str, reason: str) -> "MemoriesBackendError":
        return cls(f"cursor '{cursor}' {reason}")


class MemoriesBackend(Protocol):
    async def add_ad_hoc_note(
        self, request: AddAdHocMemoryNoteRequest
    ) -> AddAdHocMemoryNoteResponse: ...

    async def list(self, request: ListMemoriesRequest) -> ListMemoriesResponse: ...

    async def read(self, request: ReadMemoryRequest) -> ReadMemoryResponse: ...

    async def search(self, request: SearchMemoriesRequest) -> SearchMemoriesResponse: ...


__all__ = [
    "AddAdHocMemoryNoteRequest",
    "AddAdHocMemoryNoteResponse",
    "ListMemoriesRequest",
    "ListMemoriesResponse",
    "MemoriesBackend",
    "MemoriesBackendError",
    "MemoryEntry",
    "MemoryEntryType",
    "MemorySearchMatch",
    "ReadMemoryRequest",
    "ReadMemoryResponse",
    "SearchMatchMode",
    "SearchMatchModeKind",
    "SearchMemoriesRequest",
    "SearchMemoriesResponse",
]
