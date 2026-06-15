from __future__ import annotations

# Rust parity source: codex-rs/tui/src/chatwidget/keymap_picker.rs
# Behavior contract: ChatWidget-owned keymap picker routing, parse-error
# surface, submenu/capture/debug view opening, return-to-picker replace/fallback,
# and atomic live keymap cache updates after a committed edit.

from pycodex.tui.chatwidget.keymap_picker import (
    KEYMAP_ACTION_MENU_VIEW_ID,
    KEYMAP_PICKER_VIEW_ID,
    KEYMAP_REPLACE_BINDING_MENU_VIEW_ID,
    KeymapActionFilter,
    KeymapPickerWidgetState,
)


def runtime(copy="ctrl+c", edit="ctrl+e"):
    return {"app": {"copy": copy}, "chat": {"edit_queued_message": edit}}


def test_open_keymap_picker_builds_root_picker_with_current_config_and_filter():
    widget = KeymapPickerWidgetState(tui_keymap={"preset": "default"}, runtime_keymap=runtime(), fast_mode_enabled=True)

    widget.open_keymap_picker()

    assert len(widget.shown_selection_views) == 1
    view = widget.shown_selection_views[0]
    assert view.kind == "picker"
    assert view.view_id == KEYMAP_PICKER_VIEW_ID
    assert view.config == {"preset": "default"}
    assert view.runtime_keymap == runtime()
    assert view.filter == KeymapActionFilter(fast_mode_enabled=True)


def test_open_keymap_picker_reports_invalid_config_without_partial_picker():
    widget = KeymapPickerWidgetState(tui_keymap={"error": "bad binding"})

    widget.open_keymap_picker()

    assert widget.errors == ["Invalid `tui.keymap` configuration: bad binding"]
    assert widget.shown_selection_views == []


def test_open_subviews_route_to_expected_semantic_views_and_redraw_capture_debug_only():
    widget = KeymapPickerWidgetState(tui_keymap={"preset": "default"})
    keymap = runtime()

    widget.open_keymap_action_menu("chat", "submit", keymap)
    widget.open_keymap_replace_binding_menu("chat", "submit", keymap)
    widget.open_keymap_capture("chat", "submit", {"kind": "replace"}, keymap)
    widget.open_keymap_debug(keymap)

    assert [view.kind for view in widget.shown_selection_views] == ["action-menu", "replace-binding-menu"]
    assert widget.shown_selection_views[0].view_id == KEYMAP_ACTION_MENU_VIEW_ID
    assert widget.shown_selection_views[1].view_id == KEYMAP_REPLACE_BINDING_MENU_VIEW_ID
    assert [view.kind for view in widget.shown_views] == ["capture", "debug"]
    assert widget.redraws == 2


def test_return_to_keymap_picker_replaces_expected_stack_and_requests_redraw():
    widget = KeymapPickerWidgetState(tui_keymap={"preset": "default"}, fast_mode_enabled=False)
    keymap = runtime()

    widget.return_to_keymap_picker("chat", "submit", keymap)

    assert widget.replace_calls[0][0] == (
        KEYMAP_PICKER_VIEW_ID,
        KEYMAP_ACTION_MENU_VIEW_ID,
        KEYMAP_REPLACE_BINDING_MENU_VIEW_ID,
    )
    params = widget.replace_calls[0][1]
    assert params.selected_action == ("chat", "submit")
    assert params.filter == KeymapActionFilter(fast_mode_enabled=False)
    assert widget.shown_selection_views == []
    assert widget.redraws == 1


def test_return_to_keymap_picker_falls_back_to_fresh_picker_when_replace_fails():
    widget = KeymapPickerWidgetState(tui_keymap={}, replace_active_result=False)

    widget.return_to_keymap_picker("app", "copy", runtime())

    assert len(widget.replace_calls) == 1
    assert len(widget.shown_selection_views) == 1
    assert widget.shown_selection_views[0].selected_action == ("app", "copy")
    assert widget.redraws == 1


def test_apply_keymap_update_updates_all_live_caches_and_redraws_as_one_unit():
    widget = KeymapPickerWidgetState(tui_keymap={"old": True}, copy_last_response_binding="old", chat_keymap={})
    keymap = runtime(copy="alt+c", edit="alt+e")
    new_config = {"bindings": "new"}

    widget.apply_keymap_update(new_config, keymap)

    assert widget.tui_keymap == new_config
    assert widget.copy_last_response_binding == "alt+c"
    assert widget.chat_keymap == {"edit_queued_message": "alt+e"}
    assert widget.queued_message_edit_hint_binding == "alt+e"
    assert widget.bottom_pane_queued_message_edit_binding == "alt+e"
    assert widget.bottom_pane_keymap_bindings == keymap
    assert widget.redraws == 1


def test_keymap_action_filter_reflects_live_fast_mode_flag() -> None:
    widget = KeymapPickerWidgetState(fast_mode_enabled=False)
    assert widget.keymap_action_filter() == KeymapActionFilter(fast_mode_enabled=False)

    widget.fast_mode_enabled = True
    assert widget.keymap_action_filter() == KeymapActionFilter(fast_mode_enabled=True)


def test_return_to_keymap_picker_fallback_rebuilds_distinct_picker_params() -> None:
    widget = KeymapPickerWidgetState(tui_keymap={"preset": "default"}, replace_active_result=False)
    keymap = runtime()

    widget.return_to_keymap_picker("chat", "submit", keymap)

    replaced_params = widget.replace_calls[0][1]
    fallback_params = widget.shown_selection_views[0]
    assert fallback_params is not replaced_params
    assert fallback_params.selected_action == replaced_params.selected_action == ("chat", "submit")
    assert fallback_params.config == replaced_params.config == {"preset": "default"}