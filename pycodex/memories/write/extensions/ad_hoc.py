"""Rust-aligned owner for ``codex-memories-write`` module items."""

from __future__ import annotations

from pathlib import Path

INSTRUCTIONS = (
    Path(__file__).resolve().parents[5]
    / "codex"
    / "codex-rs"
    / "memories"
    / "write"
    / "templates"
    / "extensions"
    / "ad_hoc"
    / "instructions.md"
).read_text(encoding="utf-8")

async def seed_instructions(memory_root_path: str | Path) -> None:
    extension_root = memory_extensions_root(memory_root_path) / 'ad_hoc'
    instructions_path = extension_root / 'instructions.md'
    extension_root.mkdir(parents=True, exist_ok=True)
    try:
        with instructions_path.open('x', encoding='utf-8') as file:
            file.write(INSTRUCTIONS)
    except FileExistsError:
        return


from pycodex.memories.write import memory_extensions_root
