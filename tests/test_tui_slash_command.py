import pytest

from pycodex.tui.slash_command import SlashCommand, built_in_slash_commands


def test_stop_command_is_canonical_name_and_clean_alias_parses() -> None:
    # Rust source: slash_command.rs::tests::{stop_command_is_canonical_name,clean_alias_parses_to_stop_command}.
    assert SlashCommand.STOP.command() == "stop"
    assert SlashCommand.parse("clean") is SlashCommand.STOP


def test_pet_alias_parses_to_pets_command() -> None:
    assert SlashCommand.PETS.command() == "pets"
    assert SlashCommand.parse("pet") is SlashCommand.PETS


def test_certain_commands_are_available_during_task() -> None:
    assert SlashCommand.GOAL.available_during_task()
    assert SlashCommand.IDE.available_during_task()
    assert SlashCommand.TITLE.available_during_task()
    assert SlashCommand.STATUSLINE.available_during_task()
    assert SlashCommand.RAW.available_during_task()
    assert SlashCommand.RAW.available_in_side_conversation()
    assert SlashCommand.RAW.supports_inline_args()


def test_auto_review_command_is_approve() -> None:
    assert SlashCommand.AUTO_REVIEW.command() == "approve"
    assert SlashCommand.parse("approve") is SlashCommand.AUTO_REVIEW


def test_command_descriptions_and_negative_availability_match_source() -> None:
    assert SlashCommand.NEW.description() == "start a new chat during a conversation"
    assert SlashCommand.QUIT.description() == "exit Codex"
    assert SlashCommand.EXIT.description() == "exit Codex"
    assert SlashCommand.SANDBOX_READ_ROOT.description() == "let sandbox read a directory: /sandbox-add-read-dir <absolute_path>"
    assert not SlashCommand.NEW.available_during_task()
    assert not SlashCommand.THEME.available_during_task()
    assert not SlashCommand.PETS.available_during_task()
    assert not SlashCommand.COPY.supports_inline_args()
    assert not SlashCommand.QUIT.available_in_side_conversation()


def test_parse_accepts_leading_slash_and_rejects_unknown() -> None:
    assert SlashCommand.parse("/model") is SlashCommand.MODEL
    assert SlashCommand.MULTI_AGENTS.command() == "subagents"
    assert SlashCommand.parse("subagents") is SlashCommand.MULTI_AGENTS
    assert SlashCommand.parse("multi-agents") is SlashCommand.MULTI_AGENTS
    with pytest.raises(ValueError):
        SlashCommand.parse("missing")


def test_built_in_slash_commands_preserve_presentation_order() -> None:
    commands = built_in_slash_commands()
    command_names = [name for name, _command in commands]
    assert command_names[:5] == ["model", "ide", "permissions", "keymap", "vim"]
    assert ("stop", SlashCommand.STOP) in commands
    assert all(name == command.command() for name, command in commands)
