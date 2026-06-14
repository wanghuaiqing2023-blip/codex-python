"""Python API boundary for Rust crate ``codex-file-search``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol


class FileSearchNotImplementedError(NotImplementedError):
    """Raised when file search runtime behavior is not ported yet."""


@dataclass(frozen=True)
class Cli:
    """Python boundary for Rust ``codex_file_search::Cli``."""

    raw_args: tuple[str, ...] = ()


class MatchType(Enum):
    FILE = "File"
    DIRECTORY = "Directory"


@dataclass(frozen=True)
class FileMatch:
    path: Path
    score: int | None = None
    indices: list[int] | None = None
    match_type: MatchType = MatchType.FILE

    def full_path(self) -> Path:
        return self.path


def file_name_from_path(path: str) -> str:
    """Return the basename for a search path, matching the Rust helper intent."""

    return Path(path).name if path else ""


@dataclass(frozen=True)
class FileSearchResults:
    matches: list[FileMatch] = field(default_factory=list)
    total_match_count: int = 0


@dataclass(frozen=True)
class FileSearchSnapshot:
    matches: list[FileMatch] = field(default_factory=list)
    total_match_count: int = 0
    scanned_file_count: int = 0
    walk_complete: bool = False


@dataclass(frozen=True)
class FileSearchOptions:
    limit: int = 20
    exclude: list[str] = field(default_factory=list)
    threads: int = 2
    compute_indices: bool = False
    respect_gitignore: bool = True


class SessionReporter(Protocol):
    def on_update(self, snapshot: FileSearchSnapshot) -> None: ...
    def on_complete(self) -> None: ...


class Reporter(Protocol):
    def print_json(self, results: FileSearchResults) -> None: ...


class FileSearchSession:
    """Python boundary for Rust ``FileSearchSession``."""

    def update_query(self, pattern_text: str) -> None:
        raise FileSearchNotImplementedError("FileSearchSession.update_query is not ported yet")


def create_session(
    roots: list[Path],
    options: FileSearchOptions,
    reporter: SessionReporter,
    cancel_flag: Any | None = None,
) -> FileSearchSession:
    raise FileSearchNotImplementedError("create_session is not ported yet")


async def run_main(cli: Cli, reporter: Reporter) -> None:
    raise FileSearchNotImplementedError("run_main is not ported yet")


def run(
    query: str,
    roots: list[Path],
    options: FileSearchOptions,
    cancel_flag: Any | None = None,
) -> FileSearchResults:
    raise FileSearchNotImplementedError("run is not ported yet")


def cmp_by_score_desc_then_path_asc(item: Any, score: Callable[[Any], int], path: Callable[[Any], str]) -> tuple[int, str]:
    """Sort-key helper equivalent for Rust comparison function."""

    return (-score(item), path(item))


__all__ = [
    "Cli",
    "FileMatch",
    "FileSearchNotImplementedError",
    "FileSearchOptions",
    "FileSearchResults",
    "FileSearchSession",
    "FileSearchSnapshot",
    "MatchType",
    "Reporter",
    "SessionReporter",
    "cmp_by_score_desc_then_path_asc",
    "create_session",
    "file_name_from_path",
    "run",
    "run_main",
]
