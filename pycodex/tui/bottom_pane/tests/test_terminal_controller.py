import io
import os

from pycodex.tui.bottom_pane.list_selection_view import SelectionItem, SelectionViewParams
from pycodex.tui.bottom_pane.terminal_controller import (
    TerminalBottomPaneSurfaceWriter,
    draft_command_name,
    terminal_command_popup_visible_for_draft,
    terminal_popup_key,
)
from pycodex.tui.chatwidget.status_surfaces import TerminalLiveStatusSurface


def _surface(
    *,
    open_model_view=None,
    on_selection_events=None,
) -> TerminalBottomPaneSurfaceWriter:
    return TerminalBottomPaneSurfaceWriter(
        io.StringIO(),
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((80, 24)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
        open_model_view=open_model_view,
        on_selection_events=on_selection_events,
    )


def test_terminal_controller_maps_rust_like_key_payloads() -> None:
    # Rust owner: codex-tui::bottom_pane::chat_composer handles popup key
    # routing after tui::event_stream has normalized key payloads.
    assert terminal_popup_key("down") == "down"
    assert terminal_popup_key("key", "up") == "up"
    assert terminal_popup_key("text", "\t") == "tab"
    assert terminal_popup_key("text", "\r") == "enter"
    assert terminal_popup_key("text", "你") == ""


def test_terminal_controller_tracks_slash_command_visibility_and_name() -> None:
    # Rust owner: bottom_pane::chat_composer::sync_command_popup opens the
    # slash-command popup while editing the first-line command name.
    assert terminal_command_popup_visible_for_draft("/") is True
    assert terminal_command_popup_visible_for_draft("/m") is True
    assert terminal_command_popup_visible_for_draft("/model ") is False
    assert terminal_command_popup_visible_for_draft("hello /m") is False
    assert draft_command_name("/model high") == "model"


def test_terminal_controller_moves_slash_highlight_and_tabs_selection() -> None:
    # Rust owner: command_popup owns filtering/selection while chat_composer
    # owns Tab completion of the highlighted command.
    surface = _surface()

    assert surface.handle_composer_key("/m", "down") == "/m"
    assert surface.command_popup.selected_item().command() == "memories"
    assert surface.handle_composer_key("/m", "tab") == "/memories "


def test_terminal_controller_model_command_opens_active_selection_view() -> None:
    # Rust owner: chatwidget::model_popups creates the view and
    # bottom_pane::bottom_pane_view owns active view navigation.
    params = SelectionViewParams(
        title="Select Model",
        items=(
            SelectionItem(name="gpt-5.5", description="frontier"),
            SelectionItem(name="gpt-5.4", description="strong"),
        ),
    )
    surface = _surface(open_model_view=lambda: params)

    assert surface.handle_composer_key("/model", "enter") == ""
    assert surface.active_view is not None
    assert surface.handle_composer_key("", "down") == ""
    assert surface.active_view.selected_index() == 1


def test_terminal_controller_reset_buffer_state_forces_next_live_pane_repaint() -> None:
    # Rust owner: codex-tui::custom_terminal invalidates previous buffer state
    # when external resize/history repaint work changes the visible terminal.
    writer = io.StringIO()
    surface = TerminalBottomPaneSurfaceWriter(
        writer,
        stdin_is_terminal=lambda: True,
        layout_active=lambda: True,
        live_status=TerminalLiveStatusSurface.inactive,
        terminal_size=lambda: os.terminal_size((40, 12)),
        resize=lambda: None,
        footer_text=lambda: "gpt-test high",
    )
    surface.apply_draft("hello")

    assert surface.render(check_resize=False) is True
    writer.seek(0)
    writer.truncate(0)
    assert surface.render(check_resize=False) is True
    assert "\x1b[10;1H\u203a hello" not in writer.getvalue()

    surface.reset_buffer_state()
    writer.seek(0)
    writer.truncate(0)
    assert surface.render(check_resize=False) is True
    assert "\x1b[10;1H\u203a hello" in writer.getvalue()
