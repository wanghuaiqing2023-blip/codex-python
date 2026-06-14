import pytest

from pycodex.tui.external_agent_config_migration import (
    ActionMenuOption,
    ExternalAgentConfigMigrationOutcome,
    ExternalAgentConfigMigrationScreen,
    FocusArea,
    FrameRequesterStub,
    MigrationDetails,
    PluginsMigration,
    is_ctrl_exit_combo,
    render_screen,
    sample_items,
    sample_plugin_details,
    sample_project_path,
    sample_project_root,
)


def new_screen(items=None, selected_items=None, error=None):
    items = sample_items() if items is None else items
    selected_items = items if selected_items is None else selected_items
    return ExternalAgentConfigMigrationScreen.new(FrameRequesterStub(), items, selected_items, error)


def test_display_description_reformats_project_paths_and_plugin_counts():
    items = sample_items()

    assert ExternalAgentConfigMigrationScreen.display_description(items[0]) == items[0].description
    assert ExternalAgentConfigMigrationScreen.display_description(items[1]) == (
        "Migrate enabled plugins from .claude/settings.json (4 marketplaces, 6 plugins)"
    )
    assert ExternalAgentConfigMigrationScreen.display_description(items[2]) == "Migrate CLAUDE.md to AGENTS.md"


def test_plugin_detail_lines_cap_plugins_and_marketplaces_matches_rust():
    lines = ExternalAgentConfigMigrationScreen.plugin_detail_lines(sample_plugin_details().plugins)

    assert lines == [
        "      - acme-tools: deployer, formatter, +1 more",
        "      - team-marketplace: asana",
        "      - debug: sample",
        "      - +1 more marketplaces",
    ]


def test_proceed_returns_selected_items_matches_rust():
    items = sample_items()
    screen = new_screen(items, items)

    screen.handle_key("down")
    screen.handle_key("down")
    screen.handle_key("down")
    screen.handle_key("enter")

    assert screen.is_done()
    assert screen.outcome() == ExternalAgentConfigMigrationOutcome.Proceed(items)


def test_toggle_item_then_proceed_keeps_remaining_selection_matches_rust():
    items = sample_items()
    screen = new_screen(items, items)

    screen.handle_key(" ")
    screen.handle_key("down")
    screen.handle_key("down")
    screen.handle_key("down")
    screen.handle_key("enter")

    assert screen.is_done()
    assert screen.outcome() == ExternalAgentConfigMigrationOutcome.Proceed([items[1], items[2]])


def test_escape_skips_prompt_matches_rust():
    screen = new_screen()

    screen.handle_key("esc")

    assert screen.is_done()
    assert screen.outcome() == ExternalAgentConfigMigrationOutcome.Skip()


def test_skip_forever_returns_skip_forever_outcome_matches_rust():
    screen = new_screen()

    screen.move_down()
    screen.move_down()
    screen.move_down()
    screen.move_down()
    screen.move_down()
    screen.confirm_selection()

    assert screen.outcome() == ExternalAgentConfigMigrationOutcome.SkipForever()


def test_proceed_requires_at_least_one_selected_item_matches_rust():
    screen = new_screen()

    screen.handle_key("n")
    screen.handle_key("1")

    assert not screen.is_done()
    assert screen.highlighted_action is ActionMenuOption.PROCEED
    rendered = render_screen(screen)
    assert "Select at least one item or choose a skip option." in rendered


def test_proceed_action_is_skipped_when_no_items_are_selected_matches_rust():
    screen = new_screen()

    screen.handle_key("n")
    screen.handle_key("down")
    screen.handle_key("down")
    screen.handle_key("down")

    assert screen.focus is FocusArea.ACTIONS
    assert screen.highlighted_action is ActionMenuOption.SKIP


def test_numeric_shortcuts_choose_actions_matches_rust():
    items = sample_items()
    proceed_screen = new_screen(items, items)
    proceed_screen.handle_key("1")
    assert proceed_screen.outcome() == ExternalAgentConfigMigrationOutcome.Proceed(items)

    skip_screen = new_screen(items, items)
    skip_screen.handle_key("2")
    assert skip_screen.outcome() == ExternalAgentConfigMigrationOutcome.Skip()

    skip_forever_screen = new_screen(items, items)
    skip_forever_screen.handle_key("3")
    assert skip_forever_screen.outcome() == ExternalAgentConfigMigrationOutcome.SkipForever()


def test_action_navigation_wraps_between_items_and_actions():
    screen = new_screen()
    screen.move_up()
    assert screen.focus is FocusArea.ACTIONS
    assert screen.highlighted_action is ActionMenuOption.SKIP_FOREVER

    screen.move_down()
    assert screen.focus is FocusArea.ITEMS
    assert screen.selected_item_idx == 0


def test_set_all_enabled_clears_error_normalizes_action_and_schedules_frame():
    screen = new_screen()
    screen.error = "boom"
    screen.set_all_enabled(False)

    assert screen.selected_count() == 0
    assert screen.error is None
    assert screen.highlighted_action is ActionMenuOption.SKIP
    assert screen.request_frame.scheduled == 1


def test_build_render_lines_groups_home_and_project_sections():
    screen = new_screen()
    lines = screen.build_render_lines()
    texts = [line.text for line in lines]

    assert "Home" in texts
    assert f"Project: {sample_project_root()}" in texts
    assert any("[x]" in text for text in texts)
    assert any("acme-tools" in text for text in texts)


def test_ctrl_exit_combo_and_release_key_handling():
    assert is_ctrl_exit_combo({"code": "c", "modifiers": {"CONTROL"}})
    assert is_ctrl_exit_combo({"code": "d", "modifiers": "ctrl"})
    assert not is_ctrl_exit_combo({"code": "x", "modifiers": {"CONTROL"}})

    screen = new_screen()
    screen.handle_key({"code": "down", "kind": "release"})
    assert screen.selected_item_idx == 0
    screen.handle_key({"code": "c", "modifiers": {"CONTROL"}})
    assert screen.outcome() == ExternalAgentConfigMigrationOutcome.Exit()


def test_interactive_prompt_runtime_boundary_is_explicit():
    from pycodex.tui.external_agent_config_migration import run_external_agent_config_migration_prompt

    with pytest.raises(NotImplementedError):
        import asyncio

        asyncio.run(run_external_agent_config_migration_prompt(None, [], [], None))
