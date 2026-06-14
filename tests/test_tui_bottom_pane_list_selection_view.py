"""Parity tests for ``codex-tui`` list-selection-view state behavior.

Rust source: codex/codex-rs/tui/src/bottom_pane/list_selection_view.rs
"""

from pycodex.tui.bottom_pane.list_selection_view import (
    ListSelectionView,
    SelectionItem,
    SelectionToggle,
    SelectionViewParams,
    SideContentWidth,
    popup_content_width,
    side_by_side_layout_widths,
)
from pycodex.tui.bottom_pane.selection_tabs import SelectionTab


def _view(items, **kwargs):
    return ListSelectionView.new(SelectionViewParams(items=list(items), **kwargs), app_event_tx=[])


def test_popup_content_and_side_by_side_width_contracts():
    assert popup_content_width(120) == 116
    assert popup_content_width(2) == 0
    assert side_by_side_layout_widths(120, SideContentWidth.fixed(30), 10) == (88, 30)
    assert side_by_side_layout_widths(120, SideContentWidth.fixed(0), 0) is None
    assert side_by_side_layout_widths(120, SideContentWidth.half(), 10) == (59, 59)
    assert side_by_side_layout_widths(80, SideContentWidth.half(), 50) is None


def test_initial_selection_prefers_current_then_initial_then_first_enabled():
    view = _view(
        [
            SelectionItem(name="disabled", is_current=True, is_disabled=True),
            SelectionItem(name="current", is_current=True),
            SelectionItem(name="other"),
        ]
    )
    assert view.selected_actual_idx() == 1

    view = _view([SelectionItem(name="zero"), SelectionItem(name="one")], initial_selected_idx=1)
    assert view.selected_actual_idx() == 1

    view = _view([SelectionItem(name="disabled", is_disabled=True), SelectionItem(name="first enabled")])
    assert view.selected_actual_idx() == 1


def test_search_filter_maps_visible_to_actual_indices_and_notifies_callback():
    seen = []
    view = ListSelectionView.new(
        SelectionViewParams(
            is_searchable=True,
            items=[
                SelectionItem(name="Alpha", search_value="alpha"),
                SelectionItem(name="Beta", search_value="beta"),
                SelectionItem(name="Gamma", search_value=None),
            ],
            on_selection_changed=lambda idx, _tx: seen.append(idx),
        ),
        app_event_tx=[],
    )

    view.set_search_query("et")

    assert view.filtered_indices == [1]
    assert view.selected_actual_idx() == 1
    assert seen[-1] == 1

    view.set_search_query("missing")
    assert view.filtered_indices == []
    assert view.selected_actual_idx() is None


def test_navigation_skips_disabled_rows_and_page_jump_clamp():
    view = _view(
        [
            SelectionItem(name="0"),
            SelectionItem(name="1", is_disabled=True),
            SelectionItem(name="2", disabled_reason="nope"),
            SelectionItem(name="3"),
        ]
    )

    assert view.selected_actual_idx() == 0
    view.move_down()
    assert view.selected_actual_idx() == 3
    view.move_down()
    assert view.selected_actual_idx() == 0
    view.move_up()
    assert view.selected_actual_idx() == 3

    view.page_up()
    assert view.selected_actual_idx() == 0
    view.jump_bottom()
    assert view.selected_actual_idx() == 3
    view.jump_top()
    assert view.selected_actual_idx() == 0


def test_toggle_accept_cancel_and_completion_flags():
    toggled = []
    acted = []
    cancelled = []
    view = ListSelectionView.new(
        SelectionViewParams(
            items=[
                SelectionItem(
                    name="toggle",
                    toggle=SelectionToggle(False, lambda is_on, _tx: toggled.append(is_on)),
                    actions=[lambda _tx: acted.append("ran")],
                    dismiss_on_select=True,
                    dismiss_parent_on_child_accept=True,
                )
            ],
            on_cancel=lambda _tx: cancelled.append(True),
        ),
        app_event_tx=[],
    )

    assert view.selected_item_has_toggle()
    view.toggle_selected()
    assert toggled == [True]
    assert view.active_items()[0].toggle.is_on is True

    view.accept()
    assert acted == ["ran"]
    assert view.completion() == "Submitted"
    assert view.dismiss_after_child_accept()
    view.clear_dismiss_after_child_accept()
    assert not view.dismiss_after_child_accept()

    empty = _view([], on_cancel=lambda _tx: cancelled.append(True))
    empty.accept()
    assert empty.completion() == "Cancelled"
    assert cancelled == [True]


def test_tabs_switch_visible_items_and_clear_search():
    tabs = [
        SelectionTab(id="a", label="A", items=[SelectionItem(name="Alpha", search_value="alpha")]),
        SelectionTab(id="b", label="B", items=[SelectionItem(name="Beta", search_value="beta")]),
    ]
    view = ListSelectionView.new(
        SelectionViewParams(tabs=tabs, initial_tab_id="b", is_searchable=True),
        app_event_tx=[],
    )

    assert view.active_tab_id() == "b"
    assert view.active_items()[0].name == "Beta"
    view.set_search_query("bet")
    assert view.search_query == "bet"

    view.switch_tab(0)

    assert view.active_tab_id() == "a"
    assert view.search_query == ""
    assert view.active_items()[0].name == "Alpha"
    assert view.selected_actual_idx() == 0


def test_build_rows_marks_selection_current_default_and_disabled():
    view = _view(
        [
            SelectionItem(name="current", is_current=True, description="desc"),
            SelectionItem(name="default", is_default=True, disabled_reason="blocked"),
        ]
    )

    rows = view.build_rows()

    assert rows[0].name.startswith("> 1. * current")
    assert rows[0].description == "desc"
    assert rows[0].is_disabled is False
    assert rows[1].is_disabled is True
    assert rows[1].disabled_reason == "blocked"
