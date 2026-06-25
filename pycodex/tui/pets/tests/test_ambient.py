"""Parity tests for ``codex-tui/src/pets/ambient.rs``."""

from __future__ import annotations

from pathlib import Path

from pycodex.tui.pets.ambient import (
    AmbientPet,
    PetNotification,
    PetNotificationKind,
    composer_gap_rows,
    current_animation_frame,
    notification_height,
    test_ambient_pet as make_ambient_pet,
    test_animation as make_animation,
)
from pycodex.tui.pets import catalog
from pycodex.tui.pets.model import Animation, AnimationFrame, Pet


def test_notification_labels_match_codex_app_vocabulary():
    assert PetNotificationKind.Running.label() == "Running"
    assert PetNotificationKind.Waiting.label() == "Needs input"
    assert PetNotificationKind.Review.label() == "Ready"
    assert PetNotificationKind.Failed.label() == "Blocked"
    assert PetNotificationKind.Running.fallback_body() == "Thinking"
    assert PetNotificationKind.Waiting.animation_name() == "waiting"


def test_notification_lifetimes_and_height_match_rust_semantics():
    notification = PetNotification.new(PetNotificationKind.Running, now=10.0)
    assert notification.body == "Thinking"
    assert not notification.is_expired(10.0 + 179.9)
    assert notification.is_expired(10.0 + 180.0)
    assert notification_height(PetNotification.new(PetNotificationKind.Review, now=0.0)) == 1
    assert notification_height(notification) == 2


def test_animation_frame_uses_per_frame_duration():
    tick = current_animation_frame(make_animation(), 0.015)
    assert tick is not None
    assert tick.sprite_index == 1
    assert round(tick.delay or 0, 3) == 0.005


def test_non_looping_animation_settles_on_last_frame_then_fallback_in_pet():
    one_shot = Animation(
        frames=(AnimationFrame(1, 0.1), AnimationFrame(2, 0.1)),
        loop_start=None,
        fallback="idle",
    )
    tick = current_animation_frame(one_shot, 1.0)
    assert tick is not None
    assert tick.sprite_index == 2
    assert tick.delay is None

    pet = Pet(
        id="test",
        display_name="Test",
        description="",
        spritesheet_path=Path("spritesheet.webp"),
        frame_width=192,
        frame_height=208,
        columns=8,
        rows=9,
        frame_count_value=72,
        animations={"idle": make_animation(), "running": one_shot},
    )
    ambient = AmbientPet(
        pet=pet,
        support="Kitty",
        frames=[Path("frame-0.png"), Path("frame-1.png"), Path("frame-2.png")],
        sixel_dir=Path("sixel"),
        animation_started_at=0.0,
    )
    ambient.set_notification(PetNotificationKind.Running, now=0.0)
    assert ambient.current_animation(now=1.0) == pet.animations["idle"]


def test_reduced_motion_uses_stable_first_frame_and_schedules_no_follow_up():
    pet = make_ambient_pet(animations_enabled=False)
    assert pet.current_frame_path() == Path("frame-0.png")
    assert pet.next_frame_delay() is None


def test_draw_request_anchors_above_composer_and_preview_centers():
    pet = make_ambient_pet(animations_enabled=False)
    assert pet.image_enabled()
    assert pet.image_columns() == 9
    draw = pet.draw_request((0, 0, 20, 20), composer_bottom_y=12)
    assert draw is not None
    assert draw.protocol == "Kitty"
    assert draw.x == 11
    assert draw.y == 6
    assert draw.clear_top_y == 0
    assert draw.columns == 9
    assert draw.rows == 5
    assert draw.height_px == 75

    preview = pet.preview_draw_request({"x": 0, "y": 0, "width": 21, "height": 15})
    assert preview is not None
    assert preview.x == 6
    assert preview.y == 5
    assert preview.clear_top_y == 5
    assert preview.frame == Path("frame-0.png")


def test_draw_request_rejects_unsupported_or_too_small_layout():
    pet = make_ambient_pet()
    pet.set_image_support_for_tests(None)
    assert pet.draw_request((0, 0, 20, 20), composer_bottom_y=12) is None

    pet.set_image_support_for_tests("Kitty")
    assert pet.draw_request((0, 0, 8, 20), composer_bottom_y=12) is None
    assert pet.draw_request((0, 0, 20, 20), composer_bottom_y=4) is None
    assert composer_gap_rows() == 1


def test_ambient_pet_load_resolves_pet_and_frame_cache_paths(tmp_path):
    pet_dir = tmp_path / "pets" / "chefito"
    pet_dir.mkdir(parents=True)
    (pet_dir / "pet.json").write_text(
        '{"id":"chefito","displayName":"Chefito","spritesheetPath":"spritesheet.webp"}',
        encoding="utf-8",
    )
    catalog.write_test_spritesheet(pet_dir / "spritesheet.webp")
    calls = []

    def preparer(pet, frame_dir):
        calls.append((pet.id, frame_dir))
        return [frame_dir / "frame_000.png"]

    ambient = AmbientPet.load(
        "chefito",
        tmp_path,
        frame_requester=None,
        animations_enabled=False,
        now=123.0,
        support="Kitty",
        frame_preparer=preparer,
    )

    assert ambient.pet.id == "chefito"
    assert ambient.frames == [calls[0][1] / "frame_000.png"]
    assert calls[0][1].parts[-1] == "frames"
    assert calls[0][1].parts[-3] == "chefito"
    assert ambient.sixel_dir == calls[0][1].parent / "sixel"
    assert ambient.animation_started_at == 123.0
    assert ambient.image_enabled()
