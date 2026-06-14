from pycodex.tui.keymap_setup.actions import (
    KEYMAP_ACTIONS,
    KeymapActionFilter,
    KeymapDebugBindingSource,
    action_label,
    binding_slot,
    bindings_for_action,
    debug_binding_source,
    format_binding_summary,
    matching_actions_for_key_event,
)


def descriptor(context: str, action: str):
    for item in KEYMAP_ACTIONS:
        if item.context == context and item.action == action:
            return item
    raise AssertionError(f"missing descriptor: {context}.{action}")


def test_action_label_matches_rust_word_capitalization() -> None:
    assert action_label("open_transcript") == "Open Transcript"
    assert action_label("toggle_raw_output") == "Toggle Raw Output"
    assert action_label("a__b") == "A  B"


def test_fast_mode_filter_controls_gated_action_visibility() -> None:
    toggle_fast_mode = descriptor("global", "toggle_fast_mode")

    assert not toggle_fast_mode.is_visible(KeymapActionFilter())
    assert toggle_fast_mode.is_visible(KeymapActionFilter(fast_mode_enabled=True))


def test_catalog_contains_representative_contexts() -> None:
    assert descriptor("global", "open_transcript").context_label == "Global"
    assert descriptor("composer", "submit").description == "Submit the current composer draft."
    assert descriptor("approval", "cancel").context_label == "Approval"


def test_binding_slot_and_debug_source_follow_custom_then_global_then_default() -> None:
    submit = descriptor("composer", "submit")

    direct_config = {"composer": {"submit": ["enter"]}, "global": {}}
    assert binding_slot(direct_config, "composer", "submit").value == ["enter"]
    assert debug_binding_source(direct_config, submit) is KeymapDebugBindingSource.CUSTOM

    fallback_config = {"composer": {}, "global": {"submit": ["ctrl+j"]}}
    assert debug_binding_source(fallback_config, submit) is KeymapDebugBindingSource.CUSTOM_GLOBAL

    empty_config = {"composer": {}, "global": {}}
    assert debug_binding_source(empty_config, submit) is KeymapDebugBindingSource.DEFAULT


def test_bindings_for_action_reads_runtime_global_from_app_context() -> None:
    runtime_keymap = {"app": {"copy": ["ctrl+c"]}, "composer": {"submit": ["enter"]}}

    assert bindings_for_action(runtime_keymap, "global", "copy") == ["ctrl+c"]
    assert bindings_for_action(runtime_keymap, "composer", "submit") == ["enter"]
    assert bindings_for_action(runtime_keymap, "composer", "missing") is None


def test_format_binding_summary_dedupes_and_sorts_specs() -> None:
    assert format_binding_summary(["ctrl+x", "ctrl+x", {"spec": "alt+a"}]) == "ctrl+x, alt+a"
    assert format_binding_summary([]) == "unbound"


def test_matching_actions_for_key_event_reports_label_description_and_source() -> None:
    runtime_keymap = {"composer": {"submit": ["enter"]}}
    keymap_config = {"composer": {"submit": ["enter"]}}

    matches = matching_actions_for_key_event(runtime_keymap, keymap_config, "enter")

    assert matches == [
        matches[0]
    ]
    match = matches[0]
    assert match.context == "composer"
    assert match.action == "submit"
    assert match.label == "Submit"
    assert match.description == "Submit the current composer draft."
    assert match.source is KeymapDebugBindingSource.CUSTOM

def test_action_catalog_uses_rust_ui_descriptions_for_representative_actions() -> None:
    assert descriptor("global", "open_transcript").description == "Open the transcript overlay."
    assert descriptor("editor", "delete_backward").description == "Delete one grapheme to the left."
    assert descriptor("vim_text_object", "big_word").description == "Target the current WORD."
    assert descriptor("approval", "deny").description == "Choose the explicit deny option when available."


def test_binding_summary_preserves_runtime_order_while_deduping() -> None:
    assert format_binding_summary(["b", "a", "b", "c"]) == "b, a, c"


def test_matching_actions_accepts_binding_is_press_objects_and_default_source() -> None:
    class Binding:
        def __init__(self, spec):
            self.spec = spec

        def is_press(self, event):
            return event == self.spec

    runtime_keymap = {"app": {"copy": [Binding("ctrl+c")]}}
    matches = matching_actions_for_key_event(runtime_keymap, {}, "ctrl+c")

    assert len(matches) == 1
    assert matches[0].context == "global"
    assert matches[0].action == "copy"
    assert matches[0].description == "Copy the last agent response to the clipboard."
    assert matches[0].source is KeymapDebugBindingSource.DEFAULT

