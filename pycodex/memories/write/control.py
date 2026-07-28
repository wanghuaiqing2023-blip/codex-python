"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path
import shutil

async def clear_memory_roots_contents(codex_home: str | Path) -> None:
    codex_home = Path(codex_home)
    for root in (codex_home / 'memories', codex_home / 'memories_extensions'):
        await clear_memory_root_contents(root)


async def clear_memory_root_contents(memory_root_path: str | Path) -> None:
    memory_root_path = Path(memory_root_path)
    if memory_root_path.is_symlink():
        raise OSError(f'refusing to clear symlinked memory root {memory_root_path}')
    memory_root_path.mkdir(parents=True, exist_ok=True)
    for child in list(memory_root_path.iterdir()):
        if child.is_dir() and (not child.is_symlink()):
            shutil.rmtree(child)
        else:
            child.unlink()
