"""Memory search implementation from Rust ``local/search.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..backend import MemoriesBackendError
from ..backend import MemorySearchMatch
from ..backend import SearchMatchMode
from ..backend import SearchMatchModeKind
from ..backend import SearchMemoriesRequest
from ..backend import SearchMemoriesResponse
from .path import display_relative_path

MAX_SEARCH_RESULTS = 200


@dataclass(frozen=True)
class SearchComparison:
    case_sensitive: bool
    normalized: bool

    @classmethod
    def new(cls, case_sensitive: bool, normalized: bool) -> "SearchComparison":
        return cls(case_sensitive, normalized)

    def prepare(self, value: str) -> str:
        prepared = value if self.case_sensitive else value.lower()
        if self.normalized:
            prepared = "".join(char for char in prepared if char.isalnum())
        return prepared


@dataclass(frozen=True)
class SearchMatcher:
    queries: tuple[str, ...]
    prepared_queries: tuple[str, ...]
    comparison: SearchComparison
    match_mode: SearchMatchMode

    @classmethod
    def new(
        cls,
        queries: tuple[str, ...] | list[str],
        match_mode: SearchMatchMode,
        case_sensitive: bool,
        normalized: bool,
    ) -> "SearchMatcher":
        comparison = SearchComparison.new(case_sensitive, normalized)
        values = tuple(queries)
        prepared = tuple(comparison.prepare(query) for query in values)
        if any(not query for query in prepared):
            raise MemoriesBackendError(
                "queries must not be empty or contain empty strings"
            )
        return cls(values, prepared, comparison, match_mode)

    def matched_query_flags(self, line: str) -> tuple[bool, ...]:
        prepared_line = self.comparison.prepare(line)
        return tuple(query in prepared_line for query in self.prepared_queries)

    def matched_queries(self, flags: tuple[bool, ...] | list[bool]) -> tuple[str, ...]:
        return tuple(query for query, matched in zip(self.queries, flags) if matched)


def build_search_match(
    root: Path,
    path: Path,
    lines: list[str],
    match_start_index: int,
    match_end_index: int,
    context_lines: int,
    matched_queries: tuple[str, ...],
) -> MemorySearchMatch:
    content_start = max(0, match_start_index - context_lines)
    content_end = min(len(lines), match_end_index + context_lines + 1)
    return MemorySearchMatch(
        path=display_relative_path(root, path),
        match_line_number=match_start_index + 1,
        content_start_line_number=content_start + 1,
        content="\n".join(lines[content_start:content_end]),
        matched_queries=matched_queries,
    )


def _matches_for_file(
    root: Path,
    path: Path,
    matcher: SearchMatcher,
    context_lines: int,
) -> list[MemorySearchMatch]:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except UnicodeDecodeError:
        return []
    flags = [matcher.matched_query_flags(line) for line in lines]
    results: list[MemorySearchMatch] = []
    mode = matcher.match_mode.kind
    if mode in (SearchMatchModeKind.ANY, SearchMatchModeKind.ALL_ON_SAME_LINE):
        for index, line_flags in enumerate(flags):
            matched = (
                any(line_flags)
                if mode is SearchMatchModeKind.ANY
                else all(line_flags)
            )
            if matched:
                results.append(
                    build_search_match(
                        root,
                        path,
                        lines,
                        index,
                        index,
                        context_lines,
                        matcher.matched_queries(line_flags),
                    )
                )
        return results

    line_count = matcher.match_mode.line_count or 0
    if line_count <= 0:
        raise MemoriesBackendError(
            "all_within_lines.line_count must be a positive integer"
        )
    windows: list[tuple[int, int, tuple[bool, ...]]] = []
    for start in range(len(lines)):
        if not any(flags[start]):
            continue
        combined = [False] * len(matcher.queries)
        for end in range(start, min(len(lines), start + line_count)):
            combined = [
                previous or current
                for previous, current in zip(combined, flags[end])
            ]
            if all(combined):
                windows.append((start, end, tuple(combined)))
                break
    for index, (start, end, combined) in enumerate(windows):
        if any(
            index != other_index
            and start <= other_start
            and end >= other_end
            and (start, end) != (other_start, other_end)
            for other_index, (other_start, other_end, _) in enumerate(windows)
        ):
            continue
        results.append(
            build_search_match(
                root,
                path,
                lines,
                start,
                end,
                context_lines,
                matcher.matched_queries(combined),
            )
        )
    return results


async def search(
    backend: object, request: SearchMemoriesRequest
) -> SearchMemoriesResponse:
    queries = tuple(query.strip() for query in request.queries)
    if not queries or any(not query for query in queries):
        raise MemoriesBackendError("queries must not be empty or contain empty strings")
    if (
        request.match_mode.kind is SearchMatchModeKind.ALL_WITHIN_LINES
        and request.match_mode.line_count == 0
    ):
        raise MemoriesBackendError(
            "all_within_lines.line_count must be a positive integer"
        )
    try:
        start_index = int(request.cursor) if request.cursor is not None else 0
        if start_index < 0:
            raise ValueError
    except ValueError as exc:
        raise MemoriesBackendError.invalid_cursor(
            request.cursor or "", "must be a non-negative integer"
        ) from exc
    start = backend.resolve_scoped_path(request.path)
    if not start.exists():
        raise MemoriesBackendError(f"path '{request.path or ''}' was not found")
    if start.is_symlink():
        raise MemoriesBackendError.invalid_path(
            display_relative_path(backend.root, start), "must not be a symlink"
        )
    matcher = SearchMatcher.new(
        queries, request.match_mode, request.case_sensitive, request.normalized
    )
    files: list[Path]
    if start.is_file():
        files = [start]
    else:
        files = sorted(
            path
            for path in start.rglob("*")
            if path.is_file()
            and not path.is_symlink()
            and not any(part.startswith(".") for part in path.relative_to(start).parts)
        )
    matches = [
        match
        for path in files
        for match in _matches_for_file(
            backend.root, path, matcher, request.context_lines
        )
    ]
    matches.sort(key=lambda match: (match.path, match.match_line_number))
    if start_index > len(matches):
        raise MemoriesBackendError.invalid_cursor(
            str(start_index), "exceeds result count"
        )
    end = min(start_index + min(request.max_results, MAX_SEARCH_RESULTS), len(matches))
    next_cursor = str(end) if end < len(matches) else None
    return SearchMemoriesResponse(
        queries,
        request.match_mode,
        request.path,
        tuple(matches[start_index:end]),
        next_cursor,
        next_cursor is not None,
    )


__all__ = ["SearchComparison", "SearchMatcher", "build_search_match", "search"]
