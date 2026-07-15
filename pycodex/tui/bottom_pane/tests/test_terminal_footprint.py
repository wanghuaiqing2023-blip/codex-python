import os

from pycodex.tui.bottom_pane.terminal_footprint import (
    TerminalBottomPaneFootprint,
    bottom_pane_height,
    bottom_pane_rows_for_size,
    composer_row,
    footer_row,
    status_row,
    terminal_bottom_pane_layout_rows,
    terminal_bottom_pane_clear_request,
)
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface


def test_terminal_footprint_rows_reserve_idle_status_and_popup_space() -> None:
    # Rust owners: codex-tui::bottom_pane::chat_composer desired_height and
    # BottomPaneView desired_height determine the live-pane footprint consumed
    # by tui and custom_terminal.
    size = os.terminal_size((80, 24))

    assert bottom_pane_height(live_status_active=False) == 4
    assert bottom_pane_height(live_status_active=True) == 6
    assert bottom_pane_height(live_status_active=False, popup_height=3) == 5
    assert bottom_pane_height(live_status_active=True, popup_height=3) == 6
    assert bottom_pane_height(live_status_active=False, composer_height=3) == 6
    assert bottom_pane_rows_for_size(size, live_status_active=False) == [21, 22, 23, 24]
    assert bottom_pane_rows_for_size(size, live_status_active=True) == [19, 20, 21, 22, 23, 24]
    assert bottom_pane_rows_for_size(size, live_status_active=False, popup_height=3) == [20, 21, 22, 23, 24]
    assert bottom_pane_rows_for_size(size, live_status_active=False, composer_height=3) == [19, 20, 21, 22, 23, 24]


def test_terminal_footprint_from_live_status_surface() -> None:
    # Rust owners: codex-tui::chatwidget::status_surfaces determines whether
    # the status surface expands the bottom-pane footprint; tui consumes the
    # resulting compact desired-height value.
    inactive = TerminalLiveStatusSurface.inactive()
    active_without_text = TerminalLiveStatusSurface.active_status()
    active_with_text = TerminalLiveStatusSurface.active_status("\u2022 Working")

    assert TerminalBottomPaneFootprint.from_surface(inactive) == TerminalBottomPaneFootprint()
    assert TerminalBottomPaneFootprint.from_surface(active_without_text) == TerminalBottomPaneFootprint()
    assert TerminalBottomPaneFootprint.from_surface(active_with_text) == TerminalBottomPaneFootprint(
        live_status_active=True
    )
    assert TerminalBottomPaneFootprint.from_surface(active_with_text, popup_height=2).popup_height == 2


def test_terminal_footprint_projects_clear_request_for_custom_terminal() -> None:
    # Rust owners: bottom_pane owns the live-pane footprint and
    # custom_terminal consumes the generic clear request. Terminal frame/surface
    # adapters should not compute clear rows themselves.
    size = os.terminal_size((80, 24))

    idle = terminal_bottom_pane_clear_request(size, live_status_active=False)
    active = terminal_bottom_pane_clear_request(size, live_status_active=True)
    popup = terminal_bottom_pane_clear_request(size, live_status_active=False, popup_height=3)
    active_tail = terminal_bottom_pane_clear_request(
        size,
        live_status_active=False,
        active_tail_height=3,
        composer_height=2,
    )

    assert idle.rows == (21, 22, 23, 24)
    assert active.rows == (19, 20, 21, 22, 23, 24)
    assert popup.rows == (20, 21, 22, 23, 24)
    assert active_tail.rows == (17, 18, 19, 20, 21, 22, 23, 24)


def test_terminal_footprint_owns_standard_bottom_pane_rows() -> None:
    # Rust owners: bottom_pane desired-height/layout decisions reserve the
    # status, composer, and footer rows consumed by chatwidget::rendering.
    # chatwidget.rendering should consume these row helpers rather than defining its
    # own live-pane row reservation policy.
    size = os.terminal_size((80, 24))

    assert status_row(size, live_status_active=False) is None
    assert status_row(size, live_status_active=True) == 19
    assert composer_row(size) == 22
    assert footer_row(size) == 24


def test_terminal_footprint_owns_popup_layout_rows() -> None:
    # Rust owners: bottom_pane desired-height/layout and
    # chat_composer::layout_areas assign status, composer, popup, and footer
    # rows before chatwidget::rendering writes frame content.
    size = os.terminal_size((80, 24))

    popup = terminal_bottom_pane_layout_rows(size, live_status_active=False, popup_height=3)
    active_popup = terminal_bottom_pane_layout_rows(size, live_status_active=True, popup_height=3)
    clearing_taller_previous_popup = terminal_bottom_pane_layout_rows(
        size,
        live_status_active=False,
        popup_height=1,
        clear_popup_height=3,
    )

    assert popup.clear_rows == (20, 21, 22, 23, 24)
    assert popup.live_status_row is None
    assert popup.composer_row == 20
    assert popup.popup_rows == (21, 22, 23)
    assert popup.footer_row == 24

    assert active_popup.clear_rows == (19, 20, 21, 22, 23, 24)
    assert active_popup.live_status_row == 19
    assert active_popup.composer_row == 20
    assert active_popup.popup_rows == (21, 22, 23)
    assert active_popup.footer_row == 24

    assert clearing_taller_previous_popup.clear_rows == (20, 21, 22, 23, 24)
    assert clearing_taller_previous_popup.composer_row == 21
    assert clearing_taller_previous_popup.popup_rows == (22,)


def test_terminal_footprint_assigns_and_clears_wrapped_composer_rows() -> None:
    # Fixed Rust owners: chat_composer::desired_height and tui::draw_with_resize_reflow.
    size = os.terminal_size((80, 24))

    wrapped = terminal_bottom_pane_layout_rows(
        size,
        live_status_active=False,
        composer_height=3,
    )
    shrinking = terminal_bottom_pane_layout_rows(
        size,
        live_status_active=False,
        composer_height=1,
        clear_composer_height=3,
    )

    assert wrapped.clear_rows == (19, 20, 21, 22, 23, 24)
    assert wrapped.composer_rows == (20, 21, 22)
    assert wrapped.composer_row == 22
    assert shrinking.clear_rows == (19, 20, 21, 22, 23, 24)
    assert shrinking.composer_rows == (22,)
