from __future__ import annotations

from pycodex.tui.keymap_setup.actions import KEYMAP_ACTIONS, KeymapActionFilter
from pycodex.tui.keymap_setup.picker import (
    KEYMAP_ALL_TAB_ID,
    KEYMAP_DEBUG_TAB_ID,
    KEYMAP_PICKER_VIEW_ID,
    action_count_line,
    build_keymap_picker_params,
    build_keymap_picker_params_with_filter,
    build_keymap_rows,
    keymap_common_rows,
    keymap_debug_tab,
    keymap_debug_hint_line,
    keymap_picker_hint_line,
    keymap_row_prefix,
    keymap_selection_item,
    keymap_selection_items,
    _display_width,
)


def test_build_keymap_rows_filters_fast_mode_and_marks_custom_unbound() -> None:
    runtime_keymap = {"app": {"open_transcript": ["ctrl-t"]}, "composer": {"submit": ["enter"]}}
    keymap_config = {"global": {"open_transcript": ["ctrl-shift-t"]}}

    rows = build_keymap_rows(runtime_keymap, keymap_config, KeymapActionFilter())

    assert not any(row.action == "toggle_fast_mode" for row in rows)
    open_transcript = next(row for row in rows if row.context == "global" and row.action == "open_transcript")
    assert open_transcript.binding_summary == "ctrl-t"
    assert open_transcript.custom_binding is True
    assert keymap_row_prefix(open_transcript)[1].text == "*"
    assert keymap_row_prefix(open_transcript)[1].style == "accent"
    unbound = next(row for row in rows if row.binding_summary == "unbound")
    assert unbound.is_unbound()
    assert keymap_row_prefix(unbound)[1].text == "-"


def test_build_keymap_picker_params_matches_rust_picker_surface_shape() -> None:
    params = build_keymap_picker_params({}, {"composer": {"submit": ["ctrl-enter"]}})

    assert params.view_id == KEYMAP_PICKER_VIEW_ID
    assert params.initial_tab_id == KEYMAP_ALL_TAB_ID
    assert params.is_searchable is True
    assert params.search_placeholder == "Type to search shortcuts"
    assert params.col_width_mode == "AutoAllRows"
    assert params.row_display == "SingleLine"
    assert params.tabs[0].id == KEYMAP_ALL_TAB_ID
    assert params.tabs[-1].id == KEYMAP_DEBUG_TAB_ID
    assert params.tab_footer_hints[0][0] == KEYMAP_DEBUG_TAB_ID
    all_header = params.tabs[0].header
    assert all_header is not None
    assert all_header.lines[0] == "Keymap"
    assert "customized" in all_header.lines[2]


def test_fast_mode_filter_selected_action_and_common_rows_follow_rust_order() -> None:
    params = build_keymap_picker_params_with_filter({}, {}, KeymapActionFilter(fast_mode_enabled=True))
    all_rows = build_keymap_rows({}, {}, KeymapActionFilter(fast_mode_enabled=True))
    common = keymap_common_rows(all_rows)

    assert any(row.action == "toggle_fast_mode" for row in all_rows)
    assert [row.action for row in common[:4]] == ["submit", "interrupt_turn", "insert_newline", "queue"]

    selected = build_keymap_picker_params_with_filter({}, {}, KeymapActionFilter(fast_mode_enabled=True))
    manual = build_keymap_picker_params_with_filter({}, {}, KeymapActionFilter(fast_mode_enabled=True))
    assert selected.initial_selected_idx == manual.initial_selected_idx


def test_selected_action_starts_on_matching_all_tab_row() -> None:
    from pycodex.tui.keymap_setup.picker import build_keymap_picker_params_for_selected_action_with_filter

    params = build_keymap_picker_params_for_selected_action_with_filter(
        {},
        {},
        KeymapActionFilter(fast_mode_enabled=True),
        "global",
        "toggle_fast_mode",
    )
    rows = build_keymap_rows({}, {}, KeymapActionFilter(fast_mode_enabled=True))
    expected = next(idx for idx, row in enumerate(rows) if row.context == "global" and row.action == "toggle_fast_mode")
    assert params.initial_selected_idx == expected


def test_selection_item_and_debug_tab_emit_semantic_events() -> None:
    row = build_keymap_rows({"composer": {"submit": ["enter"]}}, {}, KeymapActionFilter())[0]
    item = keymap_selection_item(row)
    sent: list[object] = []
    item.actions[0](sent)
    assert sent == [{"type": "OpenKeymapActionMenu", "context": row.context, "action": row.action}]
    assert row.label in item.search_value

    debug = keymap_debug_tab()
    sent.clear()
    debug.items[0].actions[0](sent)
    assert sent == ["OpenKeymapDebug"]
    assert debug.items[0].search_value == "debug inspect keypress key terminal detected actions"


def test_action_count_line_and_picker_inventory_are_stable() -> None:
    assert action_count_line(1) == "1 action."
    assert action_count_line(2) == "2 actions."
    assert len(build_keymap_rows({}, {}, KeymapActionFilter(fast_mode_enabled=True))) == len(KEYMAP_ACTIONS)

def test_picker_hint_lines_match_rust_visible_copy() -> None:
    assert [span.text for span in keymap_picker_hint_line()] == [
        "left/right",
        " group 路 ",
        "enter",
        " edit shortcut 路 ",
        "*",
        " custom 路 ",
        "-",
        " unbound 路 ",
        "esc",
        " close",
    ]
    assert [span.text for span in keymap_debug_hint_line()] == [
        "enter",
        " start inspector 路 ",
        "esc",
        " close",
    ]


def test_empty_selection_items_use_rust_disabled_empty_row_shape() -> None:
    items = keymap_selection_items([], "No shortcuts available", "No configurable shortcuts are available.")

    assert len(items) == 1
    assert items[0].name == "No shortcuts available"
    assert items[0].description == "No configurable shortcuts are available."
    assert items[0].is_disabled is True
    assert items[0].actions == []


def test_name_column_width_uses_display_width_like_rust_unicode_width() -> None:
    assert len("宽") == 1
    assert _display_width("宽") == 2
    assert _display_width("a宽") == 3


