from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest

from pycodex.memories.write import clear_memory_root_contents


def test_clear_memory_root_contents_preserves_root_directory(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/control.rs::tests::clear_memory_root_contents_preserves_root_directory
    # Contract: clearing removes files and nested directories under the memory root but leaves the root directory itself.
    root = tmp_path / "memories"
    nested_dir = root / "rollout_summaries"
    nested_dir.mkdir(parents=True)
    (root / "MEMORY.md").write_text("stale memory index\n", encoding="utf-8")
    (nested_dir / "rollout.md").write_text("stale rollout\n", encoding="utf-8")

    asyncio.run(clear_memory_root_contents(root))

    assert root.exists()
    assert root.is_dir()
    assert list(root.iterdir()) == []


@pytest.mark.skipif(os.name != "posix", reason="Rust symlinked-root rejection test is cfg(unix)")
def test_clear_memory_root_contents_rejects_symlinked_root(tmp_path: Path) -> None:
    # Rust crate: codex-memories-write
    # Rust module/test: src/control.rs::tests::clear_memory_root_contents_rejects_symlinked_root
    # Contract: a symlinked memory root is rejected before any target contents are removed.
    target = tmp_path / "outside"
    target.mkdir()
    target_file = target / "keep.txt"
    target_file.write_text("keep\n", encoding="utf-8")

    root = tmp_path / "memories"
    root.symlink_to(target, target_is_directory=True)

    with pytest.raises(OSError):
        asyncio.run(clear_memory_root_contents(root))

    assert target_file.exists()
