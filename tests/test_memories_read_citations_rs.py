from __future__ import annotations

from pycodex.memories.read.citations import (
    parse_memory_citation,
    thread_ids_from_memory_citation,
)
from pycodex.protocol import ThreadId


def test_parse_memory_citation_supports_legacy_thread_ids():
    # Rust crate/module: codex-memories-read src/citations.rs. Rust test:
    # parse_memory_citation_supports_legacy_thread_ids.
    first = ThreadId.new()
    second = ThreadId.new()
    citations = [
        (
            "<memory_citation>\n"
            "<citation_entries>\n"
            "MEMORY.md:1-2|note=[x]\n"
            "</citation_entries>\n"
            "<thread_ids>\n"
            f"{first}\n"
            "not-a-uuid\n"
            f"{second}\n"
            "</thread_ids>\n"
            "</memory_citation>"
        )
    ]

    parsed = parse_memory_citation(citations)

    assert parsed is not None
    assert thread_ids_from_memory_citation(parsed) == [first, second]


def test_parse_memory_citation_supports_rollout_ids():
    # Rust crate/module: codex-memories-read src/citations.rs. Rust test:
    # parse_memory_citation_supports_rollout_ids.
    thread_id = ThreadId.new()
    citations = [
        (
            "<memory_citation>\n"
            "<rollout_ids>\n"
            f"{thread_id}\n"
            "</rollout_ids>\n"
            "</memory_citation>"
        )
    ]

    parsed = parse_memory_citation(citations)

    assert parsed is not None
    assert thread_ids_from_memory_citation(parsed) == [thread_id]


def test_parse_memory_citation_extracts_entries_and_rollout_ids():
    # Rust crate/module: codex-memories-read src/citations.rs. Rust test:
    # parse_memory_citation_extracts_entries_and_rollout_ids.
    first = ThreadId.new()
    second = ThreadId.new()
    citations = [
        (
            "<citation_entries>\n"
            "MEMORY.md:1-2|note=[summary]\n"
            "rollout_summaries/foo.md:10-12|note=[details]\n"
            "</citation_entries>\n"
            "<rollout_ids>\n"
            f"{first}\n"
            f"{second}\n"
            f"{first}\n"
            "</rollout_ids>"
        )
    ]

    parsed = parse_memory_citation(citations)

    assert parsed is not None
    assert [
        (entry.path, entry.line_start, entry.line_end, entry.note)
        for entry in parsed.entries
    ] == [
        ("MEMORY.md", 1, 2, "summary"),
        ("rollout_summaries/foo.md", 10, 12, "details"),
    ]
    assert parsed.rollout_ids == (str(first), str(second))


def test_parse_memory_citation_returns_none_for_empty_or_malformed_input():
    # Rust source contract: no parsed entries and no rollout IDs returns None.
    assert parse_memory_citation([]) is None
    assert parse_memory_citation(["<citation_entries>\nmissing note\n</citation_entries>"]) is None
