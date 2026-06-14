"""Parity tests for ``codex-tui`` slash-input local behavior.

Rust source: codex/codex-rs/tui/src/bottom_pane/chat_composer/slash_input.rs
"""

from pycodex.protocol.user_input import ByteRange, TextElement
from pycodex.tui.bottom_pane.chat_composer.slash_input import (
    QueuedInputAction,
    SlashInput,
    SubmissionValidation,
    args_elements,
    command_popup_filter_text,
    command_under_cursor,
    prepared_args,
    queued_input_action,
    selected_command_completion,
    selected_command_dispatches_immediately_on_tab,
)
from pycodex.tui.bottom_pane.slash_commands import BuiltinCommandFlags, SlashCommandItem
from pycodex.tui.slash_command import SlashCommand


def _slash_input(**kwargs):
    flags = kwargs.pop("flags", BuiltinCommandFlags())
    return SlashInput.new(
        enabled=kwargs.pop("enabled", True),
        is_bash_mode=kwargs.pop("is_bash_mode", False),
        command_flags=flags,
        service_tier_commands=kwargs.pop("service_tier_commands", ()),
    )


def test_validate_submission_and_command_modes():
    slash = _slash_input()

    assert slash.validate_submission("hello", False) is SubmissionValidation.VALID
    assert slash.validate_submission(" /wat", True) is SubmissionValidation.VALID
    assert slash.validate_submission("/a/b", False) is SubmissionValidation.VALID
    assert slash.validate_submission("/model", False) is SubmissionValidation.VALID

    unknown = slash.validate_submission("/wat", False)
    assert unknown.kind == "UnknownCommand"
    assert unknown.command == "wat"

    assert _slash_input(enabled=False).validate_submission("/wat", False) is SubmissionValidation.VALID


def test_bare_and_inline_command_detection():
    slash = _slash_input()

    assert slash.bare_command("/model").command() == "model"
    assert slash.bare_command("/model rest") is None
    assert slash.bare_command("/review\nsecond line").command() == "review"
    assert slash.bare_command("/review args") is None
    assert _slash_input(is_bash_mode=True).bare_command("/model") is None

    inline = slash.inline_command("/review inspect this")
    assert inline is not None
    assert inline.command.command() == "review"
    assert inline.rest == "inspect this"
    assert inline.rest_offset == len("/review ".encode("utf-8"))

    assert slash.inline_command(" /review inspect") is None
    assert slash.inline_command("/model gpt") is None
    assert slash.inline_command("/a/b rest") is None


def test_dequeue_action_matches_rust_ordering():
    assert queued_input_action("/review", True) is QueuedInputAction.PARSE_SLASH
    assert queued_input_action("/review", False) is QueuedInputAction.PLAIN
    assert queued_input_action("!echo hi", True) is QueuedInputAction.RUN_SHELL
    assert queued_input_action("plain", True) is QueuedInputAction.PLAIN

    slash = _slash_input()
    assert slash.should_parse_on_dequeue("  /review") is False
    assert slash.should_parse_on_dequeue("\n/review") is True
    assert _slash_input(enabled=False).should_parse_on_dequeue("/review") is False


def test_command_element_range_and_command_under_cursor_use_byte_offsets():
    slash = _slash_input()

    assert slash.command_element_range("/model ", 6) == (0, 6)
    assert slash.command_element_range("/model", 6) is None
    assert slash.command_element_range("/model ", 2) is None
    assert slash.command_element_range("/a/b ", 5) is None
    assert _slash_input(is_bash_mode=True).command_element_range("/model ", 6) is None

    assert command_under_cursor("/review args", 3) == ("re", "view args")
    assert command_under_cursor("/review args", 0) == ("review", " args")
    assert command_under_cursor("/review args", 1) == ("review", " args")
    assert command_under_cursor("/review args", 8) is None
    assert command_under_cursor("review", 2) is None
    assert command_under_cursor("/écho args", 2) is None


def test_editing_command_name_and_popup_filter_text():
    slash = _slash_input()

    assert slash.is_editing_command_name("/re", 3) is True
    assert slash.is_editing_command_name("/", 1) is True
    assert slash.is_editing_command_name("/unknown", 8) is False
    assert _slash_input(enabled=False).is_editing_command_name("/re", 3) is False

    assert command_popup_filter_text("/review args", 0) == "/review"
    assert command_popup_filter_text("/review args", 3) == "/re"
    assert command_popup_filter_text("/review args", 8) is None


def test_completion_dispatch_and_prepared_args():
    skills = SlashCommandItem.builtin(SlashCommand.SKILLS)
    review = SlashCommandItem.builtin(SlashCommand.REVIEW)

    assert selected_command_dispatches_immediately_on_tab(skills) is True
    assert selected_command_dispatches_immediately_on_tab(review) is False
    assert selected_command_completion("/re", review) == "/review "
    assert selected_command_completion("  /review", review) is None

    assert prepared_args("/review inspect this") == ("inspect this", len("/review ".encode("utf-8")))
    assert prepared_args("plain") is None


def test_args_elements_translate_full_text_ranges_to_argument_ranges():
    rest = "open file"
    rest_offset = len("/review ".encode("utf-8"))
    before = TextElement.new(ByteRange(0, 3), "cmd")
    overlaps = TextElement.new(ByteRange(rest_offset - 2, rest_offset + 4), "overlap")
    inside = TextElement.new(ByteRange(rest_offset + 5, rest_offset + 9), "file")
    after = TextElement.new(ByteRange(rest_offset + len(rest.encode("utf-8")), rest_offset + 20), "after")

    shifted = args_elements(rest, rest_offset, [before, overlaps, inside, after])

    assert [element.byte_range for element in shifted] == [ByteRange(0, 4), ByteRange(5, 9)]
    assert [element.placeholder_for_conversion_only() for element in shifted] == ["overlap", "file"]
