"""Parity tests for ``codex-tui`` command popup behavior.

Rust source: codex/codex-rs/tui/src/bottom_pane/command_popup.rs
"""

import os

from pycodex.tui.bottom_pane.command_popup import CommandItem, CommandPopup, CommandPopupFlags, from_
from pycodex.tui.bottom_pane.slash_commands import ServiceTierCommand
from pycodex.tui.bottom_pane.terminal_frame import (
    TerminalBottomPaneState,
    terminal_bottom_pane_frame,
    terminal_bottom_pane_frame_buffer,
)
from pycodex.tui.ratatui_bridge import Color as RatatuiColor
from pycodex.tui.slash_command import SlashCommand


def _names(popup: CommandPopup) -> list[str]:
    return [item.command() for item in popup.filtered_items()]


def test_filter_prefix_exact_and_presentation_order():
    popup = CommandPopup.new(CommandPopupFlags(), [])

    popup.on_composer_text_change("/in")
    assert "init" in _names(popup)

    popup.on_composer_text_change("/init")
    assert popup.selected_item() == CommandItem.builtin(SlashCommand.INIT)

    popup.on_composer_text_change("/mo")
    assert popup.filtered_items()[0] == CommandItem.builtin(SlashCommand.MODEL)

    popup.on_composer_text_change("/m")
    assert _names(popup) == ["model", "memories", "mention", "mcp"]

    popup.on_composer_text_change("/ac")
    assert "compact" not in _names(popup)


def test_alias_commands_hidden_only_for_empty_filter():
    popup = CommandPopup.new(CommandPopupFlags(), [])

    popup.on_composer_text_change("/")
    assert CommandItem.builtin(SlashCommand.QUIT) not in popup.filtered_items()
    assert CommandItem.builtin(SlashCommand.BTW) not in popup.filtered_items()

    popup.on_composer_text_change("/qu")
    assert CommandItem.builtin(SlashCommand.QUIT) in popup.filtered_items()

    popup.on_composer_text_change("/bt")
    assert CommandItem.builtin(SlashCommand.BTW) in popup.filtered_items()


def test_service_tier_uses_catalog_name_description_and_feature_gate():
    tier = ServiceTierCommand(
        id="priority",
        name="fast",
        description="Fastest inference with increased plan usage",
    )
    popup = CommandPopup.new(CommandPopupFlags(service_tier_commands_enabled=True), [tier])

    popup.on_composer_text_change("/fa")

    assert popup.selected_item() == CommandItem.service_tier(tier)
    rows = popup.rows_from_matches(popup.filtered())
    assert rows[0].name == "/fast"
    assert rows[0].description == "Fastest inference with increased plan usage"

    disabled = CommandPopup.new(CommandPopupFlags(service_tier_commands_enabled=False), [tier])
    disabled.on_composer_text_change("/fa")
    assert disabled.selected_item() is None


def test_feature_gated_commands_and_popup_hidden_commands():
    popup = CommandPopup.new(CommandPopupFlags(), [])
    popup.on_composer_text_change("/")
    assert "plan" not in _names(popup)
    assert not any(name.startswith("debug") for name in _names(popup))
    assert "apps" not in _names(popup)

    plan = CommandPopup.new(CommandPopupFlags(collaboration_modes_enabled=True), [])
    plan.on_composer_text_change("/plan")
    assert plan.selected_item() == CommandItem.builtin(SlashCommand.PLAN)

    personality_hidden = CommandPopup.new(CommandPopupFlags(personality_command_enabled=False), [])
    personality_hidden.on_composer_text_change("/pers")
    assert "personality" not in _names(personality_hidden)

    personality_visible = CommandPopup.new(CommandPopupFlags(personality_command_enabled=True), [])
    personality_visible.on_composer_text_change("/personality")
    assert personality_visible.selected_item() == CommandItem.builtin(SlashCommand.PERSONALITY)

    settings_hidden = CommandPopup.new(
        CommandPopupFlags(
            personality_command_enabled=True,
            realtime_conversation_enabled=True,
            audio_device_selection_enabled=False,
        ),
        [],
    )
    settings_hidden.on_composer_text_change("/aud")
    assert "settings" not in _names(settings_hidden)


def test_filter_extraction_selection_movement_and_rows():
    popup = CommandPopup.new(CommandPopupFlags(), [])

    popup.on_composer_text_change("/clear something")
    assert popup.command_filter == "clear"
    assert popup.selected_item() == CommandItem.builtin(SlashCommand.CLEAR)

    popup.on_composer_text_change("not slash")
    assert popup.command_filter == ""

    popup.on_composer_text_change("/m")
    first = popup.selected_item()
    popup.move_down()
    second = popup.selected_item()
    assert first != second
    popup.move_up()
    assert popup.selected_item() == first

    rows = popup.rows_from_matches(popup.filtered())
    assert rows[0].name.startswith("/")
    assert rows[0].match_indices == [1]
    assert isinstance(popup.calculate_required_height(40), int)


def test_terminal_lines_project_filtered_rows_and_selection_style():
    # Rust owner: codex-tui::bottom_pane::command_popup owns slash command
    # filtering and selected-row projection before terminal_surface adapts rows
    # to the live viewport.
    popup = CommandPopup.new(CommandPopupFlags(), [])
    popup.on_composer_text_change("/m")

    first = popup.terminal_lines(width=80)
    popup.move_down()
    second = popup.terminal_lines(width=80)

    assert first[0].text.startswith("/model")
    assert first[0].selected is True
    assert first[1].text.startswith("/memories")
    assert first[1].selected is False
    assert second[0].selected is False
    assert second[1].selected is True


def test_command_popup_projects_through_terminal_frame_buffer():
    # Rust owners: bottom_pane::command_popup owns slash command rows,
    # chatwidget::rendering owns the bottom-pane frame, and custom_terminal
    # consumes the frame Buffer.  terminal_runtime/surface must not hand-render
    # slash popup rows.
    popup = CommandPopup.new(CommandPopupFlags(), [])
    popup.on_composer_text_change("/m")

    frame = terminal_bottom_pane_frame(
        os.terminal_size((100, 16)),
        TerminalBottomPaneState(
            draft="/m",
            footer_text="gpt-test high",
            popup_lines=tuple(popup.terminal_lines(width=99)),
        ),
    )
    buffer = terminal_bottom_pane_frame_buffer(os.terminal_size((100, 16)), frame)

    selected_writes = [write for write in frame.writes if write.selected]
    assert selected_writes
    assert selected_writes[0].text.startswith("/model")
    assert "\u203a /m" in buffer.plain()
    assert "/model" in buffer.plain()
    assert "/memories" in buffer.plain()
    assert buffer.cell(0, selected_writes[0].row - 1).style.fg == RatatuiColor.LightBlue


def test_filter_extraction_uses_first_line_and_trims_after_slash():
    # Rust source: on_composer_text_change reads only the first line, strips
    # the leading '/', trims leading whitespace after it, then takes the first
    # non-whitespace token as the active filter.
    popup = CommandPopup.new(CommandPopupFlags(), [])

    popup.on_composer_text_change("/   model extra\n/init")

    assert popup.command_filter == "model"
    assert popup.selected_item() == CommandItem.builtin(SlashCommand.MODEL)


def test_flags_convert_to_builtin_command_flags():
    flags = CommandPopupFlags(
        collaboration_modes_enabled=True,
        connectors_enabled=True,
        plugins_command_enabled=True,
        service_tier_commands_enabled=True,
        goal_command_enabled=True,
        personality_command_enabled=True,
        realtime_conversation_enabled=True,
        audio_device_selection_enabled=True,
        windows_degraded_sandbox_active=True,
        side_conversation_active=True,
    )

    builtin = from_(flags)

    assert builtin.collaboration_modes_enabled is True
    assert builtin.connectors_enabled is True
    assert builtin.plugins_command_enabled is True
    assert builtin.service_tier_commands_enabled is True
    assert builtin.goal_command_enabled is True
    assert builtin.personality_command_enabled is True
    assert builtin.realtime_conversation_enabled is True
    assert builtin.audio_device_selection_enabled is True
    assert builtin.allow_elevate_sandbox is True
    assert builtin.side_conversation_active is True
