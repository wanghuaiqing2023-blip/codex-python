from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

from pycodex.memories.write import (
    DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
    Stage1Output,
    ensure_layout,
    raw_memories_file,
    rebuild_raw_memories_file_from_memories,
    rollout_summaries_dir,
    rollout_summary_file_stem,
    sync_rollout_summaries_from_memories,
)

FIXED_PREFIX = "2025-02-11T15-35-19-jqmb"


def stage1_output_with_slug(thread_id: str, rollout_slug: str | None) -> Stage1Output:
    return Stage1Output(
        thread_id=thread_id,
        source_updated_at=datetime.fromtimestamp(123, tz=UTC),
        raw_memory="raw memory",
        rollout_summary="summary",
        rollout_slug=rollout_slug,
        rollout_path=Path("/tmp/rollout.jsonl"),
        cwd=Path("/tmp/workspace"),
        git_branch=None,
        generated_at=datetime.fromtimestamp(124, tz=UTC),
    )


def fixed_thread_id() -> str:
    return "0194f5a6-89ab-7cde-8123-456789abcdef"


def test_rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_missing() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/storage.rs + src/storage_tests.rs::rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_missing
    # Contract: UUID timestamp plus lower-32-bit base62 short hash form the stable file prefix.
    memory = stage1_output_with_slug(fixed_thread_id(), None)

    assert rollout_summary_file_stem(memory) == FIXED_PREFIX


def test_rollout_summary_file_stem_sanitizes_and_truncates_slug() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/storage.rs + src/storage_tests.rs::rollout_summary_file_stem_sanitizes_and_truncates_slug
    # Contract: slug suffix lowercases ASCII alnum, maps other chars to _, trims trailing _, and stops at 60 bytes.
    memory = stage1_output_with_slug(
        fixed_thread_id(),
        "Unsafe Slug/With Spaces & Symbols + EXTRA_LONG_12345_67890_ABCDE_fghij_klmno",
    )

    stem = rollout_summary_file_stem(memory)
    slug = stem.removeprefix(f"{FIXED_PREFIX}-")

    assert len(slug) == 60
    assert slug == "unsafe_slug_with_spaces___symbols___extra_long_12345_67890_a"


def test_rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_is_empty() -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/storage.rs + src/storage_tests.rs::rollout_summary_file_stem_uses_uuid_timestamp_and_hash_when_slug_is_empty
    # Contract: an empty sanitized slug is omitted from the file stem.
    memory = stage1_output_with_slug(fixed_thread_id(), "")

    assert rollout_summary_file_stem(memory) == FIXED_PREFIX


def test_sync_rollout_summaries_and_raw_memories_file_keeps_latest_memories_only(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/storage.rs + src/storage_tests.rs::sync_rollout_summaries_and_raw_memories_file_keeps_latest_memories_only
    # Contract: sync prunes stale summary filenames, writes the canonical summary file, and raw_memories.md points to it.
    root = tmp_path / "memory"
    asyncio.run(ensure_layout(root))

    keep_id = "00000000-0000-0000-0000-000000000001"
    drop_id = "00000000-0000-0000-0000-000000000002"
    keep_path = rollout_summaries_dir(root) / f"{keep_id}.md"
    drop_path = rollout_summaries_dir(root) / f"{drop_id}.md"
    keep_path.write_text("keep", encoding="utf-8")
    drop_path.write_text("drop", encoding="utf-8")

    memories = [
        Stage1Output(
            thread_id=keep_id,
            source_updated_at=datetime.fromtimestamp(100, tz=UTC),
            raw_memory="raw memory",
            rollout_summary="short summary",
            rollout_slug=None,
            rollout_path=Path("/tmp/rollout-100.jsonl"),
            cwd=Path("/tmp/workspace"),
            git_branch=None,
            generated_at=datetime.fromtimestamp(101, tz=UTC),
        )
    ]

    asyncio.run(
        sync_rollout_summaries_from_memories(
            root,
            memories,
            DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
        )
    )
    asyncio.run(
        rebuild_raw_memories_file_from_memories(
            root,
            memories,
            DEFAULT_MEMORIES_MAX_RAW_MEMORIES_FOR_CONSOLIDATION,
        )
    )

    assert not keep_path.exists()
    assert not drop_path.exists()

    files = sorted(path.name for path in rollout_summaries_dir(root).iterdir())
    assert len(files) == 1
    canonical_rollout_summary_file = files[0]

    raw_memories = raw_memories_file(root).read_text(encoding="utf-8")
    assert "raw memory" in raw_memories
    assert keep_id in raw_memories
    assert "cwd: /tmp/workspace" in raw_memories
    assert "rollout_path: /tmp/rollout-100.jsonl" in raw_memories
    assert f"rollout_summary_file: {canonical_rollout_summary_file}" in raw_memories
