"""Memory citation parsing helpers.

Python port of ``codex/codex-rs/memories/read/src/citations.rs``.
"""

from __future__ import annotations

from collections.abc import Iterable

from pycodex.protocol import MemoryCitation, MemoryCitationEntry, ThreadId


def parse_memory_citation(citations: Iterable[str]) -> MemoryCitation | None:
    """Parse memory citation XML-ish blocks emitted by memory summaries."""

    entries: list[MemoryCitationEntry] = []
    rollout_ids: list[str] = []
    seen_rollout_ids: set[str] = set()

    for citation in citations:
        entries_block = _extract_block(citation, "<citation_entries>", "</citation_entries>")
        if entries_block is not None:
            for line in entries_block.splitlines():
                entry = _parse_memory_citation_entry(line)
                if entry is not None:
                    entries.append(entry)

        ids_block = _extract_ids_block(citation)
        if ids_block is not None:
            for line in ids_block.splitlines():
                rollout_id = line.strip()
                if rollout_id and rollout_id not in seen_rollout_ids:
                    seen_rollout_ids.add(rollout_id)
                    rollout_ids.append(rollout_id)

    if not entries and not rollout_ids:
        return None
    return MemoryCitation(entries=tuple(entries), rollout_ids=tuple(rollout_ids))


def thread_ids_from_memory_citation(memory_citation: MemoryCitation) -> list[ThreadId]:
    """Return rollout IDs that parse as Rust ``ThreadId`` values."""

    thread_ids: list[ThreadId] = []
    for rollout_id in memory_citation.rollout_ids:
        try:
            thread_ids.append(ThreadId.from_string(rollout_id))
        except (TypeError, ValueError):
            continue
    return thread_ids


def _parse_memory_citation_entry(line: str) -> MemoryCitationEntry | None:
    line = line.strip()
    if not line:
        return None

    location, separator, note_part = line.rpartition("|note=[")
    if not separator or not note_part.endswith("]"):
        return None
    note = note_part[:-1].strip()

    path, separator, line_range = location.rpartition(":")
    if not separator:
        return None
    line_start, separator, line_end = line_range.partition("-")
    if not separator:
        return None

    try:
        start = int(line_start.strip())
        end = int(line_end.strip())
    except ValueError:
        return None

    return MemoryCitationEntry(
        path=path.strip(),
        line_start=start,
        line_end=end,
        note=note,
    )


def _extract_block(text: str, open_marker: str, close_marker: str) -> str | None:
    before, separator, rest = text.partition(open_marker)
    del before
    if not separator:
        return None
    body, separator, after = rest.partition(close_marker)
    del after
    if not separator:
        return None
    return body


def _extract_ids_block(text: str) -> str | None:
    return _extract_block(text, "<rollout_ids>", "</rollout_ids>") or _extract_block(
        text,
        "<thread_ids>",
        "</thread_ids>",
    )


__all__ = [
    "parse_memory_citation",
    "thread_ids_from_memory_citation",
]
