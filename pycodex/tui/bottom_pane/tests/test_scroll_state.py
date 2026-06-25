"""Parity tests for Rust ``codex-tui::bottom_pane::scroll_state``."""

from pycodex.tui.bottom_pane.scroll_state import ScrollState


def test_wrap_navigation_and_visibility() -> None:
    # Rust test: wrap_navigation_and_visibility.
    state = ScrollState.new()
    length = 10
    visible = 5

    state.clamp_selection(length)
    assert state.selected_idx == 0
    state.ensure_visible(length, visible)
    assert state.scroll_top == 0

    state.move_up_wrap(length)
    state.ensure_visible(length, visible)
    assert state.selected_idx == length - 1
    assert state.scroll_top <= state.selected_idx

    state.move_down_wrap(length)
    state.ensure_visible(length, visible)
    assert state.selected_idx == 0
    assert state.scroll_top == 0


def test_page_and_jump_navigation_clamps() -> None:
    # Rust test: page_and_jump_navigation_clamps.
    state = ScrollState.new()
    length = 10
    visible = 4

    state.clamp_selection(length)
    state.page_down_clamped(length, visible)
    assert state.selected_idx == 4
    assert state.scroll_top == 1

    state.page_down_clamped(length, visible)
    assert state.selected_idx == 8
    assert state.scroll_top == 5

    state.page_down_clamped(length, visible)
    assert state.selected_idx == 9
    assert state.scroll_top == 6

    state.page_up_clamped(length, visible)
    assert state.selected_idx == 5
    assert state.scroll_top == 5

    state.jump_top(length, visible)
    assert state.selected_idx == 0
    assert state.scroll_top == 0

    state.jump_bottom(length, visible)
    assert state.selected_idx == 9
    assert state.scroll_top == 6


def test_empty_and_zero_visible_rows_reset_scroll_boundaries() -> None:
    state = ScrollState(selected_idx=3, scroll_top=2)

    assert state.clear_if_empty(0) is True
    assert state.selected_idx is None
    assert state.scroll_top == 0

    state.selected_idx = 3
    state.scroll_top = 2
    state.ensure_visible(10, 0)
    assert state.selected_idx == 3
    assert state.scroll_top == 0


def test_clamp_selection_and_reset_match_source_contract() -> None:
    state = ScrollState(selected_idx=12, scroll_top=7)

    state.clamp_selection(5)
    assert state.selected_idx == 4
    assert state.scroll_top == 7

    state.reset()
    assert state.selected_idx is None
    assert state.scroll_top == 0


def test_none_selection_initializes_like_rust_for_navigation_methods() -> None:
    # Rust source: move_up_wrap/move_down_wrap/page_* all treat None as the
    # first row instead of preserving None when len is non-empty.
    up = ScrollState.new()
    up.move_up_wrap(4)
    assert up.selected_idx == 0

    down = ScrollState.new()
    down.move_down_wrap(4)
    assert down.selected_idx == 0

    page_up = ScrollState.new()
    page_up.page_up_clamped(4, 2)
    assert page_up.selected_idx == 0
    assert page_up.scroll_top == 0

    page_down = ScrollState.new()
    page_down.page_down_clamped(4, 2)
    assert page_down.selected_idx == 2
    assert page_down.scroll_top == 1
