"""Filtering for Rust bottom_pane/mentions_v2/filter.rs."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ..._porting import RustTuiModule
from .candidate import Candidate, MentionType, SearchResult, Selection
from .search_mode import SearchMode

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::mentions_v2::filter",
    source="codex/codex-rs/tui/src/bottom_pane/mentions_v2/filter.rs",
)


@dataclass(frozen=True)
class FileMatch:
    path: Path | str
    match_type: str = "File"
    indices: list[int] | None = None
    score: int = 0


def filtered_candidates(
    candidates: Iterable[Candidate],
    file_matches: Iterable[Any],
    query: str,
    search_mode: SearchMode,
    show_file_matches: bool,
) -> list[SearchResult]:
    filter_text = query.strip()
    out: list[SearchResult] = []
    mode = SearchMode(search_mode)

    for candidate in candidates:
        if not mode.accepts(candidate.mention_type):
            continue
        if not filter_text:
            out.append(candidate.to_result(None, 0))
            continue
        match = best_tool_match(candidate, filter_text)
        if match is not None:
            indices, score = match
            out.append(candidate.to_result(indices, score))

    if show_file_matches:
        for file_match in file_matches:
            row = file_match_to_row(file_match)
            if mode.accepts(row.mention_type):
                out.append(row)

    sort_rows(out, filter_text)
    return out


def best_tool_match(candidate: Candidate, filter_text: str) -> tuple[list[int] | None, int] | None:
    display = fuzzy_match(candidate.display_name, filter_text)
    if display is not None:
        return display[0], display[1]
    scores: list[int] = []
    for term in candidate.search_terms:
        if term == candidate.display_name:
            continue
        match = fuzzy_match(term, filter_text)
        if match is not None:
            scores.append(match[1])
    if not scores:
        return None
    return None, min(scores)


def sort_rows(rows: list[SearchResult], filter_text: str) -> None:
    rows.sort(key=lambda row: (_type_order(row.mention_type), _within_rank_key(row, filter_text), row.display_name))


def compare_within_rank(a: SearchResult, b: SearchResult, filter_text: str) -> int:
    ka = _within_rank_key(a, filter_text)
    kb = _within_rank_key(b, filter_text)
    return (ka > kb) - (ka < kb)


def file_match_to_row(file_match: Any) -> SearchResult:
    match_type = _get(file_match, "match_type", "File")
    mention_type = MentionType.DIRECTORY if _match_type_name(match_type) == "Directory" else MentionType.FILE
    path = _get(file_match, "path", "")
    indices = _get(file_match, "indices", None)
    score = int(_get(file_match, "score", 0))
    path_obj = Path(path)
    display_path = str(path_obj).replace("\\", "/")
    return SearchResult(
        display_name=display_path,
        description=None,
        mention_type=mention_type,
        selection=Selection.File(path_obj),
        match_indices=None if indices is None else [int(index) for index in indices],
        score=score,
    )


def fuzzy_match(candidate: str, query: str) -> tuple[list[int], int] | None:
    if not query:
        return [], 0
    lowered = candidate.lower()
    indices: list[int] = []
    start = 0
    for char in query.lower():
        found = lowered.find(char, start)
        if found < 0:
            return None
        indices.append(found)
        start = found + 1
    gaps = indices[-1] - indices[0] if indices else 0
    prefix_penalty = indices[0] if indices else 0
    return indices, gaps + len(indices) + prefix_penalty


def _type_order(mention_type: MentionType) -> int:
    mention_type = MentionType(mention_type)
    if mention_type is MentionType.PLUGIN:
        return 0
    if mention_type is MentionType.SKILL:
        return 1
    return 2


def _within_rank_key(row: SearchResult, filter_text: str) -> tuple[int, int]:
    if row.mention_type.is_filesystem():
        return (0, -row.score)
    if not filter_text:
        return (0, 0)
    return (1 if row.match_indices is None else 0, row.score)


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _match_type_name(value: Any) -> str:
    raw = getattr(value, "value", value)
    text = str(raw).split(".")[-1]
    normalized = text.replace("_", "").replace("-", "").lower()
    if normalized in {"directory", "dir"}:
        return "Directory"
    return "File"


__all__ = [
    "FileMatch",
    "RUST_MODULE",
    "best_tool_match",
    "compare_within_rank",
    "file_match_to_row",
    "filtered_candidates",
    "fuzzy_match",
    "sort_rows",
]
