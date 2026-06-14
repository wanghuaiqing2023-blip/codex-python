"""Parity tests for ``codex-tui`` multi-select picker state behavior.

Rust source: codex/codex-rs/tui/src/bottom_pane/multi_select_picker.rs
"""

from pycodex.tui.bottom_pane.multi_select_picker import (
    Direction,
    MultiSelectItem,
    MultiSelectPicker,
    SECTION_BREAK_ROW,
    match_item,
)


def _item(id: str, *, enabled=False, orderable=True, section=False):
    return MultiSelectItem(
        id=id,
        name=id,
        enabled=enabled,
        orderable=orderable,
        section_break_after=section,
    )


def _picker(items):
    return MultiSelectPicker.builder("Test", None, []).items(items).enable_ordering().build()


def test_non_orderable_items_cannot_move_or_be_crossed():
    picker = _picker(
        [
            _item("theme-colors", orderable=False, section=True),
            _item("model"),
            _item("branch"),
        ]
    )

    picker.move_selected_item(Direction.DOWN)
    assert [item.id for item in picker.items] == ["theme-colors", "model", "branch"]

    picker.move_down()
    picker.move_selected_item(Direction.UP)
    assert [item.id for item in picker.items] == ["theme-colors", "model", "branch"]


def test_orderable_items_can_move_and_callbacks_fire():
    changed = []
    picker = (
        MultiSelectPicker.builder("Test", None, [])
        .items([_item("model"), _item("branch")])
        .enable_ordering()
        .on_change(lambda items, _tx: changed.append([item.id for item in items]))
        .build()
    )

    picker.move_selected_item(Direction.DOWN)
    assert [item.id for item in picker.items] == ["branch", "model"]
    assert picker.state.selected_idx == 1

    picker.move_selected_item(Direction.UP)
    assert [item.id for item in picker.items] == ["model", "branch"]
    assert changed[-1] == ["model", "branch"]


def test_reordering_is_disabled_while_search_query_is_active():
    # Rust source: move_selected_item returns immediately when search_query is
    # non-empty, so filtered/reordered views cannot reorder the backing list.
    picker = _picker([_item("model"), _item("branch")])
    picker.search_query = "model"
    picker.apply_filter()

    picker.move_selected_item(Direction.DOWN)

    assert [item.id for item in picker.items] == ["model", "branch"]
    assert picker.filtered_indices == [0]


def test_section_break_after_item_builds_separator_row():
    picker = _picker([_item("theme-colors", orderable=False, section=True), _item("model")])

    rows = picker.build_rows()

    assert [row.name for row in rows.rows] == ["> [ ] theme-colors", SECTION_BREAK_ROW, "  [ ] model"]
    assert rows.state.selected_idx == 0


def test_searchable_plain_character_updates_query_instead_of_navigating():
    picker = _picker([_item("alpha"), _item("jupiter")])

    picker.handle_key_event("j")

    assert picker.search_query == "j"
    assert picker.filtered_indices == [1]
    assert picker.state.selected_idx == 0


def test_toggle_confirm_cancel_and_preview_callbacks():
    previews = []
    confirmed = []
    cancelled = []
    picker = (
        MultiSelectPicker.builder("Test", "Subtitle", [])
        .items([_item("a"), _item("b", enabled=True)])
        .on_preview(lambda items: ",".join(item.id for item in items if item.enabled))
        .on_confirm(lambda ids, _tx: confirmed.append(ids))
        .on_cancel(lambda _tx: cancelled.append(True))
        .build()
    )

    assert picker.preview_line == "b"
    picker.toggle_selected()
    assert picker.items[0].enabled is True
    assert picker.preview_line == "a,b"

    picker.confirm_selection()
    assert picker.complete is True
    assert confirmed == [["a", "b"]]

    picker.confirm_selection()
    assert confirmed == [["a", "b"]]

    other = MultiSelectPicker.builder("Test", None, []).items([_item("x")]).on_cancel(lambda _tx: cancelled.append(True)).build()
    other.close()
    assert other.complete is True
    assert cancelled == [True]


def test_navigation_page_jump_and_rows_width_height():
    picker = _picker([_item(f"item-{idx}") for idx in range(12)])

    assert picker.rows_width(20) == 18
    assert picker.rows_height(picker.build_rows()) == 8

    picker.page_down()
    assert picker.state.selected_idx == 8
    picker.page_up()
    assert picker.state.selected_idx == 0
    picker.jump_bottom()
    assert picker.state.selected_idx == 11
    picker.jump_top()
    assert picker.state.selected_idx == 0


def test_match_item_display_then_canonical_fallback():
    assert match_item("jp", "jupiter", "jupiter")[0] == [0, 2]
    assert match_item("sk", "Pretty Name", "skill-name")[0] is None
    assert match_item("zz", "Pretty Name", "skill-name") is None
