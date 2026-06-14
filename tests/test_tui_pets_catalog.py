from __future__ import annotations

from pycodex.tui.pets.catalog import (
    BUILTIN_PETS,
    DEFAULT_FRAME_COLUMNS,
    DEFAULT_FRAME_HEIGHT,
    DEFAULT_FRAME_ROWS,
    DEFAULT_FRAME_WIDTH,
    SPRITESHEET_HEIGHT,
    SPRITESHEET_WIDTH,
    BuiltinPet,
    builtin_pet,
    write_test_spritesheet,
)


def test_spritesheet_dimensions_match_rust_constants() -> None:
    assert DEFAULT_FRAME_WIDTH == 192
    assert DEFAULT_FRAME_HEIGHT == 208
    assert DEFAULT_FRAME_COLUMNS == 8
    assert DEFAULT_FRAME_ROWS == 9
    assert SPRITESHEET_WIDTH == 1536
    assert SPRITESHEET_HEIGHT == 1872


def test_builtin_pet_catalog_order_and_fields() -> None:
    assert BUILTIN_PETS == (
        BuiltinPet("codex", "Codex", "The original Codex companion", "codex-spritesheet-v4.webp"),
        BuiltinPet("dewey", "Dewey", "A tidy duck for calm workspace days", "dewey-spritesheet-v4.webp"),
        BuiltinPet("fireball", "Fireball", "Hot path energy for fast iteration", "fireball-spritesheet-v4.webp"),
        BuiltinPet("rocky", "Rocky", "A steady rock when the diff gets large", "rocky-spritesheet-v4.webp"),
        BuiltinPet("seedy", "Seedy", "Small green shoots for new ideas", "seedy-spritesheet-v4.webp"),
        BuiltinPet("stacky", "Stacky", "A balanced stack for deep work", "stacky-spritesheet-v4.webp"),
        BuiltinPet("bsod", "BSOD", "A tiny blue-screen gremlin", "bsod-spritesheet-v4.webp"),
        BuiltinPet("null-signal", "Null Signal", "Quiet signal from the void", "null-signal-spritesheet-v4.webp"),
    )


def test_builtin_pet_finds_by_id() -> None:
    assert builtin_pet("dewey") == BuiltinPet(
        "dewey",
        "Dewey",
        "A tidy duck for calm workspace days",
        "dewey-spritesheet-v4.webp",
    )
    assert builtin_pet("missing") is None


def test_write_test_spritesheet_creates_requested_file(tmp_path) -> None:
    path = tmp_path / "pet.webp"

    write_test_spritesheet(path)

    assert path.read_text(encoding="utf-8") == "test spritesheet 1536x1872\n"
