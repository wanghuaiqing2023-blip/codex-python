from pycodex.protocol import ModeKind
from pycodex.tui.collaboration_modes import (
    default_mask,
    default_mode_mask,
    filtered_presets,
    make_mask,
    mask_for_kind,
    next_mask,
    plan_mask,
)


def masks(*modes):
    return [make_mask(str(mode), mode) for mode in modes]


def test_filtered_presets_keeps_only_tui_visible_modes():
    # Rust: codex-tui, collaboration_modes.rs, filtered_presets.
    presets = masks(ModeKind.PLAN, ModeKind.DEFAULT, ModeKind.PAIR_PROGRAMMING, ModeKind.EXECUTE, None)

    assert [mask.mode for mask in filtered_presets(None, presets=presets)] == [ModeKind.PLAN, ModeKind.DEFAULT]


def test_default_mask_prefers_default_mode_then_first_visible():
    # Rust: codex-tui, collaboration_modes.rs, default_mask.
    presets = masks(ModeKind.PLAN, ModeKind.DEFAULT)
    assert default_mask(None, presets=presets).mode is ModeKind.DEFAULT

    fallback = default_mask(None, presets=masks(ModeKind.PLAN))
    assert fallback.mode is ModeKind.PLAN
    assert default_mask(None, presets=[]) is None


def test_mask_for_kind_rejects_non_tui_visible_modes():
    # Rust: codex-tui, collaboration_modes.rs, mask_for_kind.
    presets = masks(ModeKind.PLAN, ModeKind.DEFAULT, ModeKind.EXECUTE)

    assert mask_for_kind(None, ModeKind.PLAN, presets=presets).mode is ModeKind.PLAN
    assert mask_for_kind(None, "default", presets=presets).mode is ModeKind.DEFAULT
    assert mask_for_kind(None, ModeKind.EXECUTE, presets=presets) is None
    assert mask_for_kind(None, ModeKind.PAIR_PROGRAMMING, presets=presets) is None


def test_next_mask_cycles_by_visible_preset_order():
    # Rust: codex-tui, collaboration_modes.rs, next_mask.
    presets = masks(ModeKind.PLAN, ModeKind.DEFAULT)

    assert next_mask(None, None, presets=presets).mode is ModeKind.PLAN
    assert next_mask(None, presets[0], presets=presets).mode is ModeKind.DEFAULT
    assert next_mask(None, presets[1], presets=presets).mode is ModeKind.PLAN
    assert next_mask(None, make_mask("missing", ModeKind.PAIR_PROGRAMMING), presets=presets).mode is ModeKind.PLAN
    assert next_mask(None, None, presets=[]) is None


def test_default_and_plan_helpers_delegate_to_mask_for_kind():
    presets = masks(ModeKind.PLAN, ModeKind.DEFAULT)

    assert default_mode_mask(None, presets=presets).mode is ModeKind.DEFAULT
    assert plan_mask(None, presets=presets).mode is ModeKind.PLAN


def test_returned_masks_are_cloned_like_rust() -> None:
    # Rust returns cloned CollaborationModeMask values from filtered/default/next helpers.
    presets = masks(ModeKind.PLAN, ModeKind.DEFAULT)

    filtered = filtered_presets(None, presets=presets)
    assert filtered[0] == presets[0]
    assert filtered[0] is not presets[0]

    assert default_mask(None, presets=presets) is not presets[1]
    assert mask_for_kind(None, ModeKind.PLAN, presets=presets) is not presets[0]
    assert next_mask(None, presets[0], presets=presets) is not presets[1]
