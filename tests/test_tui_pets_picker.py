"""Parity tests for ``codex-tui/src/pets/picker.rs``."""

from __future__ import annotations

import json

from pycodex.tui.pets import catalog
from pycodex.tui.pets.picker import (
    DISABLED_PET_ID,
    PET_PICKER_VIEW_ID,
    build_pet_picker_params,
)
from pycodex.tui.pets.preview import PetPickerPreviewState


def _write_pet(root, folder_name, display_name):
    pet_dir = root / "pets" / folder_name
    pet_dir.mkdir(parents=True)
    (pet_dir / "pet.json").write_text(
        json.dumps(
            {
                "id": folder_name,
                "displayName": display_name,
                "description": "custom pet",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )
    catalog.write_test_spritesheet(pet_dir / "spritesheet.webp")


def _write_legacy_avatar(root, folder_name, display_name):
    avatar_dir = root / "avatars" / folder_name
    avatar_dir.mkdir(parents=True)
    (avatar_dir / "avatar.json").write_text(
        json.dumps(
            {
                "displayName": display_name,
                "description": "legacy custom pet",
                "spritesheetPath": "spritesheet.webp",
            }
        ),
        encoding="utf-8",
    )
    catalog.write_test_spritesheet(avatar_dir / "spritesheet.webp")


def test_picker_lists_app_bundled_and_custom_pets(tmp_path):
    _write_pet(tmp_path, "chefito", "Chefito")

    params = build_pet_picker_params("chefito", tmp_path, PetPickerPreviewState())

    assert params.view_id == PET_PICKER_VIEW_ID
    assert [item.name for item in params.items] == [
        "Disable terminal pets",
        "BSOD",
        "Chefito",
        "Codex",
        "Dewey",
        "Fireball",
        "Null Signal",
        "Rocky",
        "Seedy",
        "Stacky",
    ]
    assert params.initial_selected_idx == 2
    assert params.items[2].search_value == "custom:chefito"
    assert params.items[2].actions[0].event == "PetSelected"
    assert params.items[2].actions[0].payload == {"pet_id": "custom:chefito"}
    assert params.selection_changed_event(2).payload == {"pet_id": "custom:chefito"}


def test_picker_preselects_codex_without_marking_it_current_when_no_pet_is_configured(tmp_path):
    params = build_pet_picker_params(None, tmp_path, PetPickerPreviewState())

    assert params.initial_selected_idx == 2
    assert params.items[2].name == "Codex"
    assert not params.items[2].is_current
    assert params.title == "Select Pet"
    assert params.subtitle == "Choose a pet to wake in the terminal."
    assert params.is_searchable
    assert params.search_placeholder == "Type to filter pets..."
    assert params.side_content_width == ("fixed", 30)
    assert params.side_content_min_width == 28
    assert params.stacked_side_content
    assert params.preserve_side_content_bg


def test_picker_marks_disabled_pet_as_current(tmp_path):
    params = build_pet_picker_params(DISABLED_PET_ID, tmp_path, PetPickerPreviewState())

    assert params.initial_selected_idx == 0
    assert params.items[0].name == "Disable terminal pets"
    assert params.items[0].description is None
    assert params.items[0].is_current
    assert params.items[0].search_value == "disable disabled hide hidden off none"
    assert params.items[0].actions[0].event == "PetDisabled"
    assert params.selection_changed_event(0).payload == {"pet_id": "disabled"}


def test_picker_imports_legacy_avatar_manifests(tmp_path):
    _write_legacy_avatar(tmp_path, "legacy", "Legacy")

    params = build_pet_picker_params("custom:legacy", tmp_path, PetPickerPreviewState())
    legacy = next(item for item in params.items if item.name == "Legacy")

    assert legacy.is_current
    assert legacy.search_value == "custom:legacy"


def test_custom_pet_entries_skip_reserved_and_invalid_manifests(tmp_path):
    _write_pet(tmp_path, "custom:bad", "Bad")
    _write_pet(tmp_path, "disabled", "Disabled")
    invalid_dir = tmp_path / "pets" / "broken"
    invalid_dir.mkdir(parents=True)
    (invalid_dir / "pet.json").write_text("{}", encoding="utf-8")

    params = build_pet_picker_params(None, tmp_path, PetPickerPreviewState())

    names = [item.name for item in params.items]
    assert "Bad" not in names
    assert "Disabled" not in names
    assert "broken" not in names
