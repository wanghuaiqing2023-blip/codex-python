"""Memory read telemetry classification helpers.

Python port of ``codex/codex-rs/memories/read/src/usage.rs``.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from enum import Enum

from pycodex.shell_command import is_known_safe_command, parse_command

MEMORIES_USAGE_METRIC = "codex.memories.usage"


class MemoriesUsageKind(str, Enum):
    MemoryMd = "memory_md"
    MemorySummary = "memory_summary"
    RawMemories = "raw_memories"
    RolloutSummaries = "rollout_summaries"
    Skills = "skills"

    def as_tag(self) -> str:
        return self.value


def memories_usage_kinds_from_command(command: Sequence[str]) -> list[MemoriesUsageKind]:
    """Classify safe shell commands that read or search memory paths."""

    if isinstance(command, str) or not isinstance(command, Sequence):
        raise TypeError("command must be a sequence of strings")
    argv = tuple(command)
    if not all(isinstance(token, str) for token in argv):
        raise TypeError("command must contain strings")

    if not is_known_safe_command(argv):
        return []

    kinds: list[MemoriesUsageKind] = []
    for parsed in parse_command(argv):
        if parsed.type == "read":
            kind = _get_memory_kind(str(parsed.path))
        elif parsed.type == "search":
            kind = _get_memory_kind(parsed.path) if parsed.path is not None else None
            if kind is None:
                kind = _get_memory_kind(_search_path_from_command_display(parsed.cmd))
        else:
            kind = None
        if kind is not None:
            kinds.append(kind)
    return kinds


def _get_memory_kind(path: str) -> MemoriesUsageKind | None:
    path = path.replace("\\", "/")
    if "memories/MEMORY.md" in path:
        return MemoriesUsageKind.MemoryMd
    if "memories/memory_summary.md" in path:
        return MemoriesUsageKind.MemorySummary
    if "memories/raw_memories.md" in path:
        return MemoriesUsageKind.RawMemories
    if "memories/rollout_summaries/" in path:
        return MemoriesUsageKind.RolloutSummaries
    if "memories/skills/" in path:
        return MemoriesUsageKind.Skills
    return None


def _search_path_from_command_display(command: str) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return ""
    return tokens[-1] if len(tokens) >= 2 else ""


__all__ = [
    "MEMORIES_USAGE_METRIC",
    "MemoriesUsageKind",
    "memories_usage_kinds_from_command",
]
