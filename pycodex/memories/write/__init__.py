"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path

def memory_root(codex_home: str | Path) -> Path:
    return Path(codex_home) / 'memories'


def rollout_summaries_dir(root: str | Path) -> Path:
    return Path(root) / artifacts.ROLLOUT_SUMMARIES_SUBDIR


def memory_extensions_root(root: str | Path) -> Path:
    return Path(root) / artifacts.EXTENSIONS_SUBDIR


def raw_memories_file(root: str | Path) -> Path:
    return Path(root) / artifacts.RAW_MEMORIES_FILENAME


async def ensure_layout(root: str | Path) -> None:
    rollout_summaries_dir(root).mkdir(parents=True, exist_ok=True)


from . import artifacts

from .control import clear_memory_roots_contents
from .extensions import prune_old_extension_resources
from .prompts import build_consolidation_prompt, build_stage_one_input_message
from .start import start_memories_startup_task
from .storage import (
    rebuild_raw_memories_file_from_memories,
    rollout_summary_file_stem,
    sync_rollout_summaries_from_memories,
)

__all__ = [
    "build_consolidation_prompt",
    "build_stage_one_input_message",
    "clear_memory_roots_contents",
    "ensure_layout",
    "memory_extensions_root",
    "memory_root",
    "prune_old_extension_resources",
    "raw_memories_file",
    "rebuild_raw_memories_file_from_memories",
    "rollout_summaries_dir",
    "rollout_summary_file_stem",
    "start_memories_startup_task",
    "sync_rollout_summaries_from_memories",
]
