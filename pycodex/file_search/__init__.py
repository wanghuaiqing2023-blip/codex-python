"""Python port of Rust ``codex-file-search/src/lib.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from threading import Event
from typing import Any, Iterable, Protocol, Sequence

from .cli import Cli


class MatchType(str, Enum):
    FILE = "file"
    DIRECTORY = "directory"


@dataclass(frozen=True)
class FileMatch:
    score: int
    path: Path
    match_type: MatchType
    root: Path
    indices: list[int] | None = None

    def full_path(self) -> Path:
        return self.root / self.path

    def to_json(self) -> dict[str, Any]:
        value: dict[str, Any] = {
            "score": self.score,
            "path": str(self.path),
            "match_type": self.match_type.value,
            "root": str(self.root),
        }
        if self.indices is not None:
            value["indices"] = list(self.indices)
        return value


def file_name_from_path(path: str) -> str:
    name = Path(path).name
    return name if name else path


@dataclass(frozen=True)
class FileSearchResults:
    matches: list[FileMatch]
    total_match_count: int


@dataclass(frozen=True)
class FileSearchSnapshot:
    query: str = ""
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

    def __post_init__(self) -> None:
        if int(self.limit) <= 0:
            raise ValueError("limit must be non-zero")
        if int(self.threads) <= 0:
            raise ValueError("threads must be non-zero")
        object.__setattr__(self, "limit", int(self.limit))
        object.__setattr__(self, "threads", int(self.threads))


class SessionReporter(Protocol):
    def on_update(self, snapshot: FileSearchSnapshot) -> None: ...

    def on_complete(self) -> None: ...


class Reporter(Protocol):
    def report_match(self, file_match: FileMatch) -> None: ...

    def warn_matches_truncated(self, total_match_count: int, shown_match_count: int) -> None: ...

    def warn_no_search_pattern(self, search_directory: Path) -> None: ...


class FileSearchSession:
    def __init__(
        self,
        search_directories: Sequence[Path | str],
        options: FileSearchOptions,
        reporter: SessionReporter,
        cancel_flag: Any | None = None,
    ) -> None:
        if not search_directories:
            raise ValueError("at least one search directory is required")
        self.search_directories = [Path(path) for path in search_directories]
        self.options = options
        self.reporter = reporter
        self.cancel_flag = cancel_flag
        self._closed = False
        self._entries = _walk_entries(
            self.search_directories,
            exclude=options.exclude,
            respect_gitignore=options.respect_gitignore,
            cancel_flag=cancel_flag,
        )

    def update_query(self, pattern_text: str) -> None:
        if self._closed:
            return
        snapshot = _snapshot_for_query(
            str(pattern_text),
            self.search_directories,
            self._entries,
            self.options,
            walk_complete=True,
        )
        self.reporter.on_update(snapshot)
        self.reporter.on_complete()

    def close(self) -> None:
        self._closed = True
        self.reporter.on_complete()

    def __enter__(self) -> "FileSearchSession":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


def create_session(
    search_directories: Sequence[Path | str],
    options: FileSearchOptions | None,
    reporter: SessionReporter,
    cancel_flag: Any | None = None,
) -> FileSearchSession:
    return FileSearchSession(search_directories, options or FileSearchOptions(), reporter, cancel_flag)


def run(
    pattern_text: str,
    roots: Sequence[Path | str],
    options: FileSearchOptions | None = None,
    cancel_flag: Any | None = None,
) -> FileSearchResults:
    reporter = _RunReporter()
    session = create_session(roots, options or FileSearchOptions(), reporter, cancel_flag)
    session.update_query(pattern_text)
    snapshot = reporter.snapshot
    return FileSearchResults(matches=snapshot.matches, total_match_count=snapshot.total_match_count)


def cmp_by_score_desc_then_path_asc(item: FileMatch | tuple[int, str]) -> tuple[int, str]:
    if isinstance(item, FileMatch):
        return (-int(item.score), str(item.path))
    return (-int(item[0]), str(item[1]))


def sort_matches(matches: list[tuple[int, str]]) -> None:
    matches.sort(key=cmp_by_score_desc_then_path_asc)


@dataclass
class _RunReporter:
    snapshot: FileSearchSnapshot = field(default_factory=FileSearchSnapshot)
    completed: Event = field(default_factory=Event)

    def on_update(self, snapshot: FileSearchSnapshot) -> None:
        self.snapshot = snapshot

    def on_complete(self) -> None:
        self.completed.set()


def _snapshot_for_query(
    query: str,
    roots: Sequence[Path],
    entries: Sequence[tuple[Path, Path, MatchType]],
    options: FileSearchOptions,
    *,
    walk_complete: bool,
) -> FileSearchSnapshot:
    matches: list[FileMatch] = []
    for root, relative, match_type in entries:
        score_indices = _fuzzy_score(str(relative), query)
        if score_indices is None:
            continue
        score, indices = score_indices
        matches.append(
            FileMatch(
                score=score,
                path=relative,
                match_type=match_type,
                root=root,
                indices=indices if options.compute_indices else None,
            )
        )
    matches.sort(key=cmp_by_score_desc_then_path_asc)
    total = len(matches)
    return FileSearchSnapshot(
        query=query,
        matches=matches[: options.limit],
        total_match_count=total,
        scanned_file_count=len(entries),
        walk_complete=walk_complete,
    )


def _walk_entries(
    roots: Sequence[Path],
    *,
    exclude: Sequence[str],
    respect_gitignore: bool,
    cancel_flag: Any | None,
) -> list[tuple[Path, Path, MatchType]]:
    entries: list[tuple[Path, Path, MatchType]] = []
    for root in roots:
        root = root.resolve()
        gitignore = _load_gitignore(root) if respect_gitignore and (root / ".git").exists() else _GitIgnore.empty()
        for current, dirs, files in os.walk(root, followlinks=True):
            if _cancelled(cancel_flag):
                return []
            current_path = Path(current)
            rel_dir = _relative_path(current_path, root)
            kept_dirs = []
            for dirname in dirs:
                rel_path = rel_dir / dirname if str(rel_dir) != "." else Path(dirname)
                if _excluded(rel_path, exclude) or gitignore.ignored(rel_path, True):
                    continue
                kept_dirs.append(dirname)
                entries.append((root, rel_path, MatchType.DIRECTORY))
            dirs[:] = kept_dirs
            for filename in files:
                rel_path = rel_dir / filename if str(rel_dir) != "." else Path(filename)
                if _excluded(rel_path, exclude) or gitignore.ignored(rel_path, False):
                    continue
                entries.append((root, rel_path, MatchType.FILE))
    return entries


def _relative_path(path: Path, root: Path) -> Path:
    try:
        return path.relative_to(root)
    except ValueError:
        return path


def _excluded(path: Path, patterns: Sequence[str]) -> bool:
    text = path.as_posix()
    return any(path.match(pattern) or text == pattern or text.startswith(pattern.rstrip("/") + "/") for pattern in patterns)


def _fuzzy_score(haystack: str, query: str) -> tuple[int, list[int]] | None:
    if not query:
        return (0, [])
    lower_haystack = haystack.lower()
    positions: list[int] = []
    start = 0
    for char in query.lower():
        pos = lower_haystack.find(char, start)
        if pos < 0:
            return None
        positions.append(pos)
        start = pos + 1
    compactness = positions[-1] - positions[0] + 1 if positions else 0
    basename_bonus = 100 if Path(haystack).name.lower().startswith(query.lower()[:1]) else 0
    exact_bonus = 1000 if query.lower() in lower_haystack else 0
    score = exact_bonus + basename_bonus + max(0, 10_000 - compactness * 10 - positions[0])
    return (score, sorted(set(positions)))


def _cancelled(flag: Any | None) -> bool:
    if flag is None:
        return False
    if hasattr(flag, "is_set"):
        return bool(flag.is_set())
    if hasattr(flag, "load"):
        return bool(flag.load())
    return bool(flag)


@dataclass(frozen=True)
class _GitIgnore:
    ignored_patterns: tuple[str, ...] = ()
    allowed_patterns: tuple[str, ...] = ()

    @classmethod
    def empty(cls) -> "_GitIgnore":
        return cls()

    def ignored(self, path: Path, is_dir: bool) -> bool:
        text = path.as_posix()
        ignored = False
        for pattern in self.ignored_patterns:
            if _gitignore_match(text, pattern, is_dir):
                ignored = True
        for pattern in self.allowed_patterns:
            if _gitignore_match(text, pattern, is_dir):
                ignored = False
        return ignored


def _load_gitignore(root: Path) -> _GitIgnore:
    path = root / ".gitignore"
    if not path.exists():
        return _GitIgnore.empty()
    ignored: list[str] = []
    allowed: list[str] = []
    for raw_line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("!"):
            allowed.append(line[1:])
        else:
            ignored.append(line)
    return _GitIgnore(tuple(ignored), tuple(allowed))


def _gitignore_match(text: str, pattern: str, is_dir: bool) -> bool:
    pattern = pattern.strip()
    if not pattern:
        return False
    if pattern.endswith("/"):
        pattern = pattern.rstrip("/")
        return is_dir and (text == pattern or text.startswith(pattern + "/"))
    if pattern.endswith("/*"):
        base = pattern[:-2].rstrip("/")
        return text.startswith(base + "/") and text != base
    return Path(text).match(pattern) or text == pattern or text.endswith("/" + pattern)


__all__ = [
    "Cli",
    "FileMatch",
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
    "sort_matches",
]
