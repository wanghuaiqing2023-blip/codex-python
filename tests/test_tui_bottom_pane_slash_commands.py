"""Parity tests for Rust ``codex-tui::bottom_pane::slash_commands``."""

from dataclasses import replace

from pycodex.tui.bottom_pane.slash_commands import (
    ServiceTierCommand,
    SlashCommandItem,
    all_enabled_flags,
    builtins_for_input,
    commands_for_input,
    find_builtin_command,
    find_slash_command,
    has_slash_command_prefix,
)
from pycodex.tui.slash_command import SlashCommand


def test_builtin_dispatch_lookup_resolves_visible_and_alias_commands() -> None:
    # Rust tests: debug_command_still_resolves_for_dispatch,
    # clear_command_resolves_for_dispatch, stop_command_resolves_for_dispatch,
    # clean_command_alias_resolves_for_dispatch.
    flags = all_enabled_flags()

    assert find_builtin_command("debug-config", flags) is SlashCommand.DEBUG_CONFIG
    assert find_builtin_command("clear", flags) is SlashCommand.CLEAR
    assert find_builtin_command("stop", flags) is SlashCommand.STOP
    assert find_builtin_command("clean", flags) is SlashCommand.STOP


def test_service_tier_commands_are_hidden_when_disabled() -> None:
    # Rust test: service_tier_commands_are_hidden_when_disabled.
    flags = replace(all_enabled_flags(), service_tier_commands_enabled=False)
    commands = [ServiceTierCommand(id="priority", name="fast", description="fastest inference")]

    assert find_slash_command("fast", flags, commands) is None


def test_all_service_tiers_are_exposed_as_commands_after_model() -> None:
    # Rust test: all_service_tiers_are_exposed_as_commands_after_model.
    commands = [
        ServiceTierCommand(id="priority", name="fast", description="fastest inference"),
        ServiceTierCommand(id="batch", name="slow", description="slower inference with lower priority"),
    ]

    items = commands_for_input(all_enabled_flags(), commands)
    model_index = items.index(SlashCommandItem.builtin(SlashCommand.MODEL))

    assert items[model_index + 1 : model_index + 1 + len(commands)] == [
        SlashCommandItem.service_tier(command) for command in commands
    ]


def test_feature_gated_builtin_commands_are_hidden() -> None:
    # Rust tests: goal/realtime/settings hidden when their feature flags are disabled.
    flags = all_enabled_flags()

    assert find_builtin_command("goal", replace(flags, goal_command_enabled=False)) is None
    assert find_builtin_command("realtime", replace(flags, realtime_conversation_enabled=False)) is None
    assert (
        find_builtin_command(
            "settings",
            replace(flags, realtime_conversation_enabled=False, audio_device_selection_enabled=False),
        )
        is None
    )
    assert find_builtin_command("settings", replace(flags, audio_device_selection_enabled=False)) is None


def test_side_conversation_hides_commands_without_side_flag() -> None:
    # Rust test: side_conversation_hides_commands_without_side_flag.
    flags = replace(all_enabled_flags(), side_conversation_active=True)

    assert [command for _, command in builtins_for_input(flags)] == [
        SlashCommand.IDE,
        SlashCommand.COPY,
        SlashCommand.RAW,
        SlashCommand.DIFF,
        SlashCommand.MENTION,
        SlashCommand.STATUS,
    ]


def test_side_conversation_exact_lookup_still_resolves_hidden_commands_for_dispatch_error() -> None:
    # Rust test: side_conversation_exact_lookup_still_resolves_hidden_commands_for_dispatch_error.
    flags = replace(all_enabled_flags(), side_conversation_active=True)

    assert find_builtin_command("review", flags) is SlashCommand.REVIEW


def test_side_conversation_exact_lookup_still_resolves_service_tier_commands_for_dispatch_error() -> None:
    # Rust test: side_conversation_exact_lookup_still_resolves_service_tier_commands_for_dispatch_error.
    command = ServiceTierCommand(id="priority", name="fast", description="fastest inference")
    flags = replace(all_enabled_flags(), side_conversation_active=True)

    assert find_slash_command("fast", flags, [command]) == SlashCommandItem.service_tier(command)


def test_slash_command_item_delegates_builtin_methods_and_service_tiers_are_not_inline_or_side_safe() -> None:
    builtin = SlashCommandItem.builtin(SlashCommand.RAW)
    tier = SlashCommandItem.service_tier(
        ServiceTierCommand(id="priority", name="fast", description="fastest inference")
    )

    assert builtin.command() == "raw"
    assert builtin.supports_inline_args() is True
    assert builtin.available_in_side_conversation() is True
    assert builtin.available_during_task() is True

    assert tier.command() == "fast"
    assert tier.supports_inline_args() is False
    assert tier.available_in_side_conversation() is False
    assert tier.available_during_task() is False


def test_has_slash_command_prefix_uses_visible_command_items() -> None:
    tier = ServiceTierCommand(id="priority", name="fast", description="fastest inference")

    assert has_slash_command_prefix("mdl", all_enabled_flags(), [tier]) is True
    assert has_slash_command_prefix("fst", all_enabled_flags(), [tier]) is True
    assert has_slash_command_prefix("fst", replace(all_enabled_flags(), service_tier_commands_enabled=False), [tier]) is False
