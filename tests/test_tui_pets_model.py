"""Parity tests for ``codex-tui/src/pets/model.rs``."""

from __future__ import annotations

import json

import pytest

from pycodex.tui.pets import asset_pack, catalog
from pycodex.tui.pets.model import (
    AnimationSpec,
    FrameSpec,
    Pet,
    app_state_animation,
    custom_pet_cache_id,
    custom_pet_selector,
    default_animations,
    default_frame_count,
    durations_ms,
    idle_animation,
    load_animations,
    path_like,
    resolve_spritesheet_path,
    validate_app_spritesheet_dimensions,
    sprite_indices,
    validate_frame_spec,
)


def _write_pet_manifest(directory, manifest):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "pet.json").write_text(json.dumps(manifest), encoding="utf-8")
    catalog.write_test_spritesheet(directory / "spritesheet.webp")


def test_default_animation_shapes_match_rust_rows():
    animations = default_animations()
    idle = animations["idle"]
    assert sprite_indices(idle) == [0, 1, 2, 3, 4, 5]
    assert durations_ms(idle) == [1680, 660, 660, 840, 840, 1920]
    assert idle.loop_start == 0

    running = animations["running"]
    primary = [56, 57, 58, 59, 60, 61]
    assert sprite_indices(running)[0:6] == primary
    assert sprite_indices(running)[6:12] == primary
    assert sprite_indices(running)[12:18] == primary
    assert sprite_indices(running)[18:] == sprite_indices(idle)
    assert durations_ms(running)[0:6] == [120, 120, 120, 120, 120, 220]
    assert running.loop_start == 18

    assert sprite_indices(animations["waiting"])[0:6] == [48, 49, 50, 51, 52, 53]
    assert sprite_indices(animations["review"])[0:6] == [64, 65, 66, 67, 68, 69]
    assert sprite_indices(animations["failed"])[0:8] == [40, 41, 42, 43, 44, 45, 46, 47]


def test_custom_animation_specs_keep_manifest_fps_and_loop_shape():
    animations = load_animations(
        {
            "custom": AnimationSpec(
                frames=(1, 2),
                fps=2.0,
                loop_animation=False,
                fallback="idle",
            )
        },
        default_frame_count(),
    )
    custom = animations["custom"]
    assert sprite_indices(custom) == [1, 2]
    assert durations_ms(custom) == [500, 500]
    assert custom.loop_start is None
    assert custom.fallback == "idle"


def test_load_builtin_and_custom_pet_manifests(tmp_path):
    codex_home = tmp_path / "home"
    for pet in catalog.BUILTIN_PETS:
        catalog.write_test_spritesheet(asset_pack.builtin_spritesheet_path(codex_home, pet.spritesheet_file))

    pet = Pet.load_with_codex_home("dewey", codex_home)
    assert pet.id == "dewey"
    assert pet.display_name == "Dewey"
    assert pet.description == "A tidy duck for calm workspace days"
    assert pet.frame_width == 192
    assert pet.frame_height == 208
    assert pet.columns == 8
    assert pet.rows == 9
    assert pet.frame_count() == 72

    pet_dir = codex_home / "pets" / "chefito"
    _write_pet_manifest(
        pet_dir,
        {
            "id": "chefito",
            "displayName": "Chefito",
            "description": "A tiny recipe-loving chef",
            "spritesheetPath": "spritesheet.webp",
        },
    )
    custom = Pet.load_with_codex_home(custom_pet_selector("chefito"), codex_home)
    assert custom.id == "custom-chefito"
    assert custom.display_name == "Chefito"
    assert custom.spritesheet_path == pet_dir / "spritesheet.webp"


def test_path_loading_and_cache_key_include_frame_spec(tmp_path):
    pet_dir = tmp_path / "chefito"
    _write_pet_manifest(
        pet_dir,
        {
            "displayName": "Chefito",
            "spritesheetPath": "spritesheet.webp",
        },
    )
    pet = Pet.load_with_codex_home(str(pet_dir), None)
    first_key = pet.frame_cache_key()

    (pet_dir / "spritesheet.webp").write_text(
        f"test spritesheet {catalog.SPRITESHEET_WIDTH}x{catalog.SPRITESHEET_HEIGHT}\nchanged",
        encoding="utf-8",
    )
    changed = Pet.load_with_codex_home(str(pet_dir / "pet.json"), None)
    assert changed.frame_cache_key() != first_key

    tall_dir = tmp_path / "tall"
    _write_pet_manifest(
        tall_dir,
        {
            "displayName": "Tall",
            "spritesheetPath": "spritesheet.webp",
            "frame": {"width": 384, "height": 104, "columns": 4, "rows": 18},
        },
    )
    tall = Pet.load_with_codex_home(str(tall_dir), None)
    assert tall.frame_cache_key() != changed.frame_cache_key()


def test_validation_errors_match_rust_contracts(tmp_path):
    with pytest.raises(ValueError, match="spritesheet path must stay inside"):
        resolve_spritesheet_path(tmp_path, "../spritesheet.webp")

    with pytest.raises(ValueError, match="pet frame dimensions and grid counts must be non-zero"):
        validate_frame_spec(FrameSpec(width=0, height=208, columns=8, rows=9), 1536, 1872)

    with pytest.raises(ValueError, match="pet frame grid must cover spritesheet exactly"):
        validate_frame_spec(FrameSpec(width=192, height=208, columns=7, rows=9), 1536, 1872)

    with pytest.raises(ValueError, match="exceeds maximum"):
        validate_frame_spec(FrameSpec(width=8, height=8, columns=192, rows=234), 1536, 1872)

    with pytest.raises(ValueError, match="animation idle must include at least one frame"):
        load_animations({"idle": {"frames": []}}, default_frame_count())

    with pytest.raises(ValueError, match="animation idle references sprite index 72"):
        load_animations({"idle": {"frames": [72]}}, default_frame_count())

    with pytest.raises(ValueError, match="fps must be finite"):
        load_animations({"idle": {"frames": [0], "fps": 120.0}}, default_frame_count())

    with pytest.raises(ValueError, match="fallback missing does not exist"):
        load_animations({"wave": {"frames": [1], "loop": False, "fallback": "missing"}}, default_frame_count())


def test_validate_app_spritesheet_dimensions_reads_real_png_header(tmp_path):
    # Rust source: validate_app_spritesheet_dimensions delegates to image::image_dimensions.
    png = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR"
        + catalog.SPRITESHEET_WIDTH.to_bytes(4, "big")
        + catalog.SPRITESHEET_HEIGHT.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
    )
    path = tmp_path / "spritesheet.png"
    path.write_bytes(png)

    assert validate_app_spritesheet_dimensions(path) == (
        catalog.SPRITESHEET_WIDTH,
        catalog.SPRITESHEET_HEIGHT,
    )


def test_selector_and_path_helpers_match_rust_boundaries():
    assert custom_pet_selector("chefito") == "custom:chefito"
    assert custom_pet_cache_id("chefito") == "custom-chefito"
    assert path_like(".")
    assert path_like("../pet")
    assert path_like("./pet")
    assert path_like("~/pet")
    assert path_like("pets/chefito")
    assert path_like("pets\\chefito")
    assert not path_like("chefito")

    assert sprite_indices(app_state_animation(1, 2, 120, 220)) == [8, 9, 8, 9, 8, 9] + sprite_indices(idle_animation())
