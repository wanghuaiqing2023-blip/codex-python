"""Porting surface for Rust crate ``codex-memories-read``."""

from __future__ import annotations

from pathlib import Path

from pycodex.utils.absolute_path import AbsolutePathBuf

from .citations import parse_memory_citation, thread_ids_from_memory_citation
from .usage import MEMORIES_USAGE_METRIC, MemoriesUsageKind, memories_usage_kinds_from_command


def memory_root(codex_home: AbsolutePathBuf | str | Path) -> AbsolutePathBuf:
    """Return the Codex memories directory below ``codex_home``."""

    base = (
        codex_home
        if isinstance(codex_home, AbsolutePathBuf)
        else AbsolutePathBuf.from_absolute_path_checked(codex_home)
    )
    return base.join("memories")


__all__ = [
    "MEMORIES_USAGE_METRIC",
    "MemoriesUsageKind",
    "memory_root",
    "memories_usage_kinds_from_command",
    "parse_memory_citation",
    "thread_ids_from_memory_citation",
]
