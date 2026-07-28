"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from .ad_hoc import seed_instructions


async def seed_extension_instructions(memory_root: str | Path) -> None:
    await seed_instructions(memory_root)


from .prune import prune_old_extension_resources

__all__ = ["prune_old_extension_resources"]
