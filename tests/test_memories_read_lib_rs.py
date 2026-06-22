from __future__ import annotations

from pathlib import Path

import pytest

from pycodex.memories.read import (
    MEMORIES_USAGE_METRIC,
    MemoriesUsageKind,
    memory_root,
    memories_usage_kinds_from_command,
    parse_memory_citation,
    thread_ids_from_memory_citation,
)
from pycodex.utils.absolute_path import AbsolutePathBuf


def test_memory_root_joins_memories_directory(tmp_path: Path):
    # Rust crate/module: codex-memories-read src/lib.rs. Behavior contract:
    # memory_root(codex_home) returns codex_home.join("memories").
    codex_home = AbsolutePathBuf.from_absolute_path_checked(tmp_path)

    assert memory_root(codex_home) == codex_home.join("memories")


def test_memory_root_accepts_absolute_path_like_input(tmp_path: Path):
    # Python adapter for the Rust API: callers may provide an absolute path-like
    # value, which is coerced to AbsolutePathBuf before applying Rust join.
    assert memory_root(str(tmp_path)) == AbsolutePathBuf.from_absolute_path_checked(tmp_path).join(
        "memories"
    )


def test_memory_root_rejects_relative_path():
    # Rust API receives AbsolutePathBuf; the Python adapter enforces that
    # invariant when a raw path-like value is supplied.
    with pytest.raises(ValueError):
        memory_root("relative/home")


def test_crate_root_reexports_public_modules():
    # Rust crate root publicly exposes citations and usage modules.
    assert callable(parse_memory_citation)
    assert callable(thread_ids_from_memory_citation)
    assert MEMORIES_USAGE_METRIC == "codex.memories.usage"
    assert MemoriesUsageKind.MemoryMd.as_tag() == "memory_md"
    assert memories_usage_kinds_from_command(["cat", "/tmp/README.md"]) == []
