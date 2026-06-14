"""Built-in pet catalog.

Upstream source: ``codex/codex-rs/tui/src/pets/catalog.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="pets::catalog",
    source="codex/codex-rs/tui/src/pets/catalog.rs",
)

DEFAULT_FRAME_WIDTH = 192
DEFAULT_FRAME_HEIGHT = 208
DEFAULT_FRAME_COLUMNS = 8
DEFAULT_FRAME_ROWS = 9
SPRITESHEET_WIDTH = DEFAULT_FRAME_WIDTH * DEFAULT_FRAME_COLUMNS
SPRITESHEET_HEIGHT = DEFAULT_FRAME_HEIGHT * DEFAULT_FRAME_ROWS


@dataclass(frozen=True)
class BuiltinPet:
    id: str
    display_name: str
    description: str
    spritesheet_file: str


BUILTIN_PETS = (
    BuiltinPet(
        id="codex",
        display_name="Codex",
        description="The original Codex companion",
        spritesheet_file="codex-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="dewey",
        display_name="Dewey",
        description="A tidy duck for calm workspace days",
        spritesheet_file="dewey-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="fireball",
        display_name="Fireball",
        description="Hot path energy for fast iteration",
        spritesheet_file="fireball-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="rocky",
        display_name="Rocky",
        description="A steady rock when the diff gets large",
        spritesheet_file="rocky-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="seedy",
        display_name="Seedy",
        description="Small green shoots for new ideas",
        spritesheet_file="seedy-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="stacky",
        display_name="Stacky",
        description="A balanced stack for deep work",
        spritesheet_file="stacky-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="bsod",
        display_name="BSOD",
        description="A tiny blue-screen gremlin",
        spritesheet_file="bsod-spritesheet-v4.webp",
    ),
    BuiltinPet(
        id="null-signal",
        display_name="Null Signal",
        description="Quiet signal from the void",
        spritesheet_file="null-signal-spritesheet-v4.webp",
    ),
)


def builtin_pet(id: str) -> BuiltinPet | None:
    return next((pet for pet in BUILTIN_PETS if pet.id == id), None)


def write_test_spritesheet(path: str | Path) -> None:
    """Write a deterministic lightweight marker for test-pack installation.

    Rust writes an actual WebP via the `image` crate. The catalog module's
    contract is that callers get a file at the requested path for every
    built-in pet; WebP encoding itself is a dependency boundary outside this
    pure catalog table.
    """

    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"test spritesheet {SPRITESHEET_WIDTH}x{SPRITESHEET_HEIGHT}\n",
        encoding="utf-8",
    )


__all__ = [
    "BUILTIN_PETS",
    "BuiltinPet",
    "DEFAULT_FRAME_COLUMNS",
    "DEFAULT_FRAME_HEIGHT",
    "DEFAULT_FRAME_ROWS",
    "DEFAULT_FRAME_WIDTH",
    "RUST_MODULE",
    "SPRITESHEET_HEIGHT",
    "SPRITESHEET_WIDTH",
    "builtin_pet",
    "write_test_spritesheet",
]
