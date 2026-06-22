from __future__ import annotations

from pycodex.memories.read.usage import (
    MEMORIES_USAGE_METRIC,
    MemoriesUsageKind,
    memories_usage_kinds_from_command,
)


def test_memories_usage_kind_as_tag_matches_rust_tags():
    # Rust crate/module: codex-memories-read src/usage.rs.
    assert MEMORIES_USAGE_METRIC == "codex.memories.usage"
    assert MemoriesUsageKind.MemoryMd.as_tag() == "memory_md"
    assert MemoriesUsageKind.MemorySummary.as_tag() == "memory_summary"
    assert MemoriesUsageKind.RawMemories.as_tag() == "raw_memories"
    assert MemoriesUsageKind.RolloutSummaries.as_tag() == "rollout_summaries"
    assert MemoriesUsageKind.Skills.as_tag() == "skills"


def test_memories_usage_kinds_from_safe_read_command():
    # Rust crate/module: codex-memories-read src/usage.rs. Behavior contract:
    # safe read commands classify ParsedCommand::Read.path.
    assert memories_usage_kinds_from_command(["cat", "/home/me/memories/MEMORY.md"]) == [
        MemoriesUsageKind.MemoryMd
    ]
    assert memories_usage_kinds_from_command(["cat", "/home/me/memories/memory_summary.md"]) == [
        MemoriesUsageKind.MemorySummary
    ]
    assert memories_usage_kinds_from_command(["cat", "/home/me/memories/raw_memories.md"]) == [
        MemoriesUsageKind.RawMemories
    ]
    assert memories_usage_kinds_from_command(["cat", "/home/me/memories/rollout_summaries/a.md"]) == [
        MemoriesUsageKind.RolloutSummaries
    ]
    assert memories_usage_kinds_from_command(["cat", "/home/me/memories/skills/python.md"]) == [
        MemoriesUsageKind.Skills
    ]


def test_memories_usage_kinds_rejects_unsafe_command():
    # Rust first calls is_known_safe_command, so unsafe commands emit no kinds
    # even if a memory path appears in the command text.
    assert (
        memories_usage_kinds_from_command(
            ["bash", "-lc", "cat /home/me/memories/MEMORY.md && rm -rf /tmp/x"]
        )
        == []
    )


def test_memories_usage_kinds_search_uses_path_not_query():
    # Rust maps ParsedCommand::Search.path through get_memory_kind, not query.
    assert memories_usage_kinds_from_command(["bash", "-lc", "rg memories/MEMORY.md /tmp/project"]) == []
    assert memories_usage_kinds_from_command(
        ["bash", "-lc", "rg TODO /home/me/memories/skills/python.md"]
    ) == [MemoriesUsageKind.Skills]


def test_memories_usage_kinds_ignores_list_files_unknown_and_non_memory_paths():
    # Rust ignores ParsedCommand::ListFiles and ParsedCommand::Unknown.
    assert memories_usage_kinds_from_command(["ls", "/home/me/memories"]) == []
    assert memories_usage_kinds_from_command(["python", "-c", "print('memories/MEMORY.md')"]) == []
    assert memories_usage_kinds_from_command(["cat", "/tmp/README.md"]) == []
