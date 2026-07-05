# Rust owner: codex-tui::chatwidget::slash_dispatch.
from pycodex.tui.chatwidget.slash_dispatch import (
    ByteRange,
    GOAL_USAGE,
    GOAL_USAGE_HINT,
    RAW_USAGE,
    SIDE_SLASH_COMMAND_UNAVAILABLE_HINT,
    SIDE_STARTING_CONTEXT_LABEL,
    GuardResult,
    PreparedSlashCommandArgs,
    QueueDrain,
    SlashCommandDispatchSource,
    TextElement,
    ensure_side_command_allowed_outside_review,
    ensure_slash_command_allowed_in_side_conversation,
    keymap_arg_action,
    mcp_detail_arg,
    pets_disable_arg,
    prepared_inline_user_message,
    queued_command_drain_result,
    raw_output_mode_arg,
    slash_command_args_elements,
)
from pycodex.tui.slash_command import SlashCommand


def test_constants_match_rust_user_facing_text() -> None:
    assert SIDE_STARTING_CONTEXT_LABEL == "Side starting..."
    assert SIDE_SLASH_COMMAND_UNAVAILABLE_HINT == "Press Ctrl+C to return to the main thread first."
    assert GOAL_USAGE == "Usage: /goal <objective>"
    assert GOAL_USAGE_HINT == "Example: /goal improve benchmark coverage"
    assert RAW_USAGE == "Usage: /raw [on|off]"


def test_side_conversation_guard_allows_only_side_safe_commands() -> None:
    assert ensure_slash_command_allowed_in_side_conversation(False, SlashCommand.MODEL) == GuardResult(True)
    assert ensure_slash_command_allowed_in_side_conversation(True, SlashCommand.RAW) == GuardResult(True)

    denied = ensure_slash_command_allowed_in_side_conversation(True, SlashCommand.MODEL)
    assert denied.allowed is False
    assert denied.drain_pending_submission is True
    assert denied.error_message == "'/model' is unavailable in side conversations. Press Ctrl+C to return to the main thread first."


def test_side_command_rejected_while_review_running() -> None:
    assert ensure_side_command_allowed_outside_review(True, SlashCommand.MODEL) == GuardResult(True)

    denied = ensure_side_command_allowed_outside_review(True, SlashCommand.SIDE)
    assert denied.allowed is False
    assert denied.drain_pending_submission is True
    assert denied.error_message == "'/side' is unavailable while code review is running."


def test_queued_command_drain_result_matches_rust_command_sets() -> None:
    assert queued_command_drain_result(SlashCommand.STATUS) is QueueDrain.CONTINUE
    assert queued_command_drain_result(SlashCommand.RAW) is QueueDrain.CONTINUE
    assert queued_command_drain_result(SlashCommand.MODEL) is QueueDrain.STOP
    assert queued_command_drain_result(SlashCommand.STATUS, user_turn_pending_or_running=True) is QueueDrain.STOP
    assert queued_command_drain_result(SlashCommand.STATUS, no_modal_or_popup_active=False) is QueueDrain.STOP


def test_slash_command_args_elements_remaps_overlapping_byte_ranges() -> None:
    elements = [
        TextElement(ByteRange(0, 4), "before"),
        TextElement(ByteRange(7, 12), "first"),
        TextElement(ByteRange(13, 20), "second"),
        TextElement(ByteRange(30, 40), "after"),
    ]

    remapped = slash_command_args_elements("hello world", 7, elements)

    assert remapped == [
        TextElement(ByteRange(0, 5), "first"),
        TextElement(ByteRange(6, 11), "second"),
    ]


def test_prepared_inline_user_message_preserves_payloads() -> None:
    prepared = PreparedSlashCommandArgs(
        args="hello",
        text_elements=("text",),
        local_images=("local",),
        remote_image_urls=("https://example.com/a.png",),
        mention_bindings=("mention",),
        source=SlashCommandDispatchSource.QUEUED,
    )

    message = prepared_inline_user_message(prepared)

    assert message.text == "hello"
    assert message.text_elements == ("text",)
    assert message.local_images == ("local",)
    assert message.remote_image_urls == ("https://example.com/a.png",)
    assert message.mention_bindings == ("mention",)


def test_inline_argument_classifiers_for_raw_mcp_keymap_and_pets() -> None:
    assert raw_output_mode_arg("ON") is True
    assert raw_output_mode_arg("off") is False
    assert raw_output_mode_arg("maybe") is None
    assert mcp_detail_arg(" verbose ") == "full"
    assert mcp_detail_arg("tools") is None
    assert keymap_arg_action("") == "picker"
    assert keymap_arg_action("debug") == "debug"
    assert keymap_arg_action("bad") is None
    assert pets_disable_arg("hidden") is True
    assert pets_disable_arg("codex") is False
