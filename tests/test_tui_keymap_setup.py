import pytest

from pycodex.tui.app_event import KeymapEditIntent
from pycodex.tui.keymap import RuntimeKeymap
from pycodex.tui.keymap_setup import (
    KEYMAP_ACTION_MENU_VIEW_ID,
    KEYMAP_REPLACE_BINDING_MENU_VIEW_ID,
    KeymapCaptureView,
    active_binding_specs,
    build_keymap_action_menu_params,
    build_keymap_capture_view,
    build_keymap_replace_binding_menu_params,
    has_custom_binding,
    key_event_to_config_key_spec,
    keymap_with_bindings,
    keymap_with_edit,
    keymap_with_replacement,
    keymap_without_custom_binding,
)


def test_key_capture_serializes_modifier_order_for_config() -> None:
    # Rust: codex-tui/src/keymap_setup.rs::tests::key_capture_serializes_modifier_order_for_config.
    assert key_event_to_config_key_spec(("K", {"CONTROL", "ALT"})) == "ctrl-alt-shift-k"


def test_key_capture_serializes_special_and_c0_keys() -> None:
    # Rust: codex-tui/src/keymap_setup.rs::{key_capture_serializes_special_keys,
    # key_capture_serializes_c0_control_chars_as_ctrl_bindings}.
    assert key_event_to_config_key_spec(("PageDown", {"SHIFT"})) == "shift-page-down"
    assert key_event_to_config_key_spec("\u000a") == "ctrl-j"
    assert key_event_to_config_key_spec("\u0015") == "ctrl-u"
    assert key_event_to_config_key_spec("\u0010") == "ctrl-p"


def test_key_capture_serializes_minus_as_named_key() -> None:
    # Rust: codex-tui/src/keymap_setup.rs::tests::key_capture_serializes_minus_as_named_key.
    assert key_event_to_config_key_spec("-") == "minus"
    assert key_event_to_config_key_spec(("-", {"ALT"})) == "alt-minus"
    assert key_event_to_config_key_spec(("-", {"CONTROL", "ALT"})) == "ctrl-alt-minus"


def test_replacement_sets_single_binding_and_clear_removes_custom_binding() -> None:
    # Rust: keymap_with_replacement/keymap_without_custom_binding preserve the
    # root `tui.keymap.<context>.<action>` slot semantics.
    keymap = keymap_with_replacement({}, "composer", "submit", "ctrl-enter")
    assert keymap == {"composer": {"submit": "ctrl-enter"}}
    assert has_custom_binding(keymap, "composer", "submit") is True

    cleared = keymap_without_custom_binding(keymap, "composer", "submit")
    assert cleared == {"composer": {}}
    assert has_custom_binding(cleared, "composer", "submit") is False


def test_replace_all_collapses_multi_binding_to_single() -> None:
    # Rust: codex-tui/src/keymap_setup.rs::tests::replace_all_collapses_multi_binding_to_single.
    keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "alt-shift-enter"])
    runtime = RuntimeKeymap.from_config(keymap)

    outcome = keymap_with_edit(
        keymap,
        runtime,
        "composer",
        "submit",
        "ctrl-shift-enter",
        KeymapEditIntent.replace_all(),
    )

    assert outcome.kind == "Updated"
    assert outcome.bindings == ("ctrl-shift-enter",)
    assert outcome.keymap_config == {"composer": {"submit": "ctrl-shift-enter"}}


def test_add_alternate_grows_defaults_and_duplicate_is_noop() -> None:
    # Rust: add_alternate_grows_single_binding, add_alternate_grows_default_multi_binding,
    # and add_alternate_duplicate_is_noop.
    single = keymap_with_edit({}, RuntimeKeymap.defaults(), "composer", "submit", "ctrl-enter", KeymapEditIntent.add_alternate())
    assert single.bindings == ("enter", "ctrl-enter")
    assert single.keymap_config == {"composer": {"submit": ["enter", "ctrl-enter"]}}

    multi = keymap_with_edit({}, RuntimeKeymap.defaults(), "editor", "move_left", "ctrl-shift-b", KeymapEditIntent.add_alternate())
    assert multi.bindings == ("left", "ctrl-b", "ctrl-shift-b")

    duplicate = keymap_with_edit({}, RuntimeKeymap.defaults(), "composer", "submit", "enter", KeymapEditIntent.add_alternate())
    assert duplicate.kind == "Unchanged"
    assert duplicate.message == "No change: `composer.submit` already uses `enter`."


def test_replace_one_preserves_deduplicates_and_rejects_stale_old_key() -> None:
    # Rust: replace_one_preserves_other_bindings, replace_one_deduplicates_replacement,
    # and replace_one_rejects_stale_old_key.
    keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "alt-shift-enter"])
    runtime = RuntimeKeymap.from_config(keymap)

    outcome = keymap_with_edit(
        keymap,
        runtime,
        "composer",
        "submit",
        "ctrl-shift-enter",
        KeymapEditIntent.replace_one("ctrl-enter"),
    )
    assert outcome.bindings == ("ctrl-shift-enter", "alt-shift-enter")

    dedup_keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "ctrl-shift-enter"])
    dedup_runtime = RuntimeKeymap.from_config(dedup_keymap)
    dedup = keymap_with_edit(
        dedup_keymap,
        dedup_runtime,
        "composer",
        "submit",
        "ctrl-shift-enter",
        KeymapEditIntent.replace_one("ctrl-enter"),
    )
    assert dedup.bindings == ("ctrl-shift-enter",)

    with pytest.raises(ValueError, match="composer\\.submit.*alt-enter"):
        keymap_with_edit({}, RuntimeKeymap.defaults(), "composer", "submit", "ctrl-enter", KeymapEditIntent.replace_one("alt-enter"))


def test_action_menu_items_follow_active_binding_count_and_custom_clear_state() -> None:
    # Rust: build_keymap_action_menu_params constructs different menu rows for
    # unbound, single-binding, multi-binding, and custom-clear states.
    unbound = build_keymap_action_menu_params("global", "toggle_vim_mode", RuntimeKeymap.defaults(), {})
    assert unbound.view_id == KEYMAP_ACTION_MENU_VIEW_ID
    assert [item.name for item in unbound.items[:2]] == ["Set key", "Remove custom binding"]
    assert unbound.items[1].disabled_reason is not None

    single_custom_keymap = keymap_with_replacement({}, "composer", "submit", "ctrl-enter")
    single = build_keymap_action_menu_params("composer", "submit", RuntimeKeymap.from_config(single_custom_keymap), single_custom_keymap)
    assert [item.name for item in single.items[:3]] == ["Replace binding", "Add alternate binding", "Remove custom binding"]
    assert single.items[2].disabled_reason is None

    multi_keymap = keymap_with_bindings({}, "composer", "submit", ["ctrl-enter", "alt-shift-enter"])
    multi = build_keymap_action_menu_params("composer", "submit", RuntimeKeymap.from_config(multi_keymap), multi_keymap)
    assert [item.name for item in multi.items[:3]] == ["Replace one binding...", "Replace all bindings", "Add alternate binding"]


def test_replace_binding_menu_and_capture_view_emit_expected_events() -> None:
    # Rust: build_keymap_replace_binding_menu_params and KeymapCaptureView emit
    # OpenKeymapCapture/KeymapCaptured app events while the parent picker stack remains owned by app code.
    runtime = RuntimeKeymap.defaults()
    params = build_keymap_replace_binding_menu_params("composer", "submit", runtime)
    assert params.view_id == KEYMAP_REPLACE_BINDING_MENU_VIEW_ID
    assert params.items[0].name == "enter"
    assert params.items[0].action_events[0].kind == "OpenKeymapCapture"
    assert params.items[0].action_events[0].payload["intent"] == KeymapEditIntent.replace_one("enter")

    sent = []
    view = build_keymap_capture_view("composer", "submit", KeymapEditIntent.replace_all(), runtime, sent)
    assert isinstance(view, KeymapCaptureView)
    assert active_binding_specs(runtime, "composer", "submit") == ["enter"]
    view.handle_key_event(("K", {"CONTROL"}))
    assert view.is_complete() is True
    assert sent[0].kind == "KeymapCaptured"
    assert sent[0].payload["key"] == "ctrl-shift-k"


def test_replacement_rejects_unknown_action() -> None:
    # Rust: codex-tui/src/keymap_setup.rs::tests::replacement_rejects_unknown_action.
    with pytest.raises(ValueError, match="composer\\.nope"):
        keymap_with_replacement({}, "composer", "nope", "ctrl-enter")
