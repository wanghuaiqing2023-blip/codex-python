from pathlib import Path

from pycodex.app_server_protocol.turn import TextElement as AppServerTextElement
from pycodex.app_server_protocol.turn import UserInput as AppServerUserInput
from pycodex.protocol.user_input import ByteRange, TextElement
from pycodex.tui.bottom_pane import LocalImageAttachment, MentionBinding
from pycodex.tui.bottom_pane.chat_composer import QueuedInputAction
from pycodex.tui.chatwidget.user_messages import (
    ChatWidget,
    PendingSteerCompareKey,
    QueuedUserMessage,
    ThreadComposerState,
    UserMessage,
    UserMessageHistoryRecord,
    app_server_text_elements,
    create_initial_user_message,
    merge_user_messages,
    merge_user_messages_with_history_record,
    remap_placeholders_for_message,
    user_message_display_for_history,
    user_message_preview_text,
)


def element(start: int, end: int, placeholder: str | None = None) -> TextElement:
    return TextElement.new(ByteRange(start, end), placeholder)


def test_create_initial_user_message_labels_local_images_like_rust() -> None:
    # Rust: codex-tui::chatwidget::user_messages::create_initial_user_message.
    assert create_initial_user_message(None, [], []) is None

    message = create_initial_user_message("hi", [Path("a.png"), Path("b.png")], [element(0, 2)])

    assert message is not None
    assert message.text == "hi"
    assert [(image.placeholder, image.path) for image in message.local_images] == [
        ("[Image #1]", Path("a.png")),
        ("[Image #2]", Path("b.png")),
    ]
    assert message.remote_image_urls == []
    assert message.text_elements == [element(0, 2)]
    assert message.mention_bindings == []


def test_thread_composer_state_has_content_matches_all_rust_fields() -> None:
    # Rust: ThreadComposerState::has_content checks every visible/pending field.
    assert not ThreadComposerState().has_content()
    assert ThreadComposerState(text="x").has_content()
    assert ThreadComposerState(local_images=[LocalImageAttachment("[Image #1]", "a.png")]).has_content()
    assert ThreadComposerState(remote_image_urls=["data:image/png;base64,..."]).has_content()
    assert ThreadComposerState(text_elements=[element(0, 1)]).has_content()
    assert ThreadComposerState(mention_bindings=[MentionBinding("@repo", "/repo")]).has_content()
    assert ThreadComposerState(pending_pastes=[("id", "pending")]).has_content()


def test_queued_user_message_plain_from_and_into_user_message() -> None:
    # Rust: From<UserMessage> for QueuedUserMessage and into_user_message.
    message = UserMessage("hello")
    queued = QueuedUserMessage.from_user_message(message)

    assert queued.action is QueuedInputAction.Plain
    assert queued.into_user_message() == message
    assert QueuedUserMessage.new(message, QueuedInputAction.RunShell).action is QueuedInputAction.RunShell


def test_remap_placeholders_for_message_relabels_local_images_and_text_elements() -> None:
    # Rust: remap_placeholders_for_message remaps labels in attachment order.
    message = UserMessage(
        text="[Image #2] before [Image #1]",
        local_images=[
            LocalImageAttachment("[Image #1]", "first.png"),
            LocalImageAttachment("[Image #2]", "second.png"),
        ],
        text_elements=[
            element(0, len("[Image #2]"), "[Image #2]"),
            element(len("[Image #2] before "), len("[Image #2] before [Image #1]"), "[Image #1]"),
        ],
    )

    remapped, next_label = remap_placeholders_for_message(message, 1)

    assert next_label == 3
    assert [(image.placeholder, image.path) for image in remapped.local_images] == [
        ("[Image #1]", Path("first.png")),
        ("[Image #2]", Path("second.png")),
    ]
    assert remapped.text == "[Image #2] before [Image #1]"
    assert [elem.placeholder_for_conversion_only() for elem in remapped.text_elements] == [
        "[Image #2]",
        "[Image #1]",
    ]


def test_merge_user_messages_starts_local_labels_after_remote_images_and_rebases_elements() -> None:
    # Rust: merge_user_messages uses total remote image count as the local label offset.
    first = UserMessage(
        text="remote",
        remote_image_urls=["https://example.test/image.png"],
        text_elements=[element(0, 6)],
    )
    second = UserMessage(
        text="[Image #1]",
        local_images=[LocalImageAttachment("[Image #1]", "local.png")],
        text_elements=[element(0, len("[Image #1]"), "[Image #1]")],
    )

    merged = merge_user_messages([first, second])

    assert merged.text == "remote\n[Image #2]"
    assert merged.remote_image_urls == ["https://example.test/image.png"]
    assert [(image.placeholder, image.path) for image in merged.local_images] == [
        ("[Image #2]", Path("local.png"))
    ]
    assert [(elem.byte_range.start, elem.byte_range.end) for elem in merged.text_elements] == [
        (0, 6),
        (7, 17),
    ]


def test_merge_user_messages_with_history_record_uses_non_empty_overrides() -> None:
    # Rust: merge_user_messages_with_history_record builds an override if any segment has one.
    message = UserMessage("agent text", text_elements=[element(0, 5)])
    override = UserMessageHistoryRecord.Override("visible text", [element(0, 7)])

    merged, history = merge_user_messages_with_history_record([(message, override)])

    assert merged.text == "agent text"
    assert history.kind == "Override"
    assert history.override is not None
    assert history.override.text == "visible text"
    assert user_message_preview_text(merged, history) == "visible text"


def test_user_message_display_for_history_restores_override_and_strips_prompt_context() -> None:
    # Rust: ChatWidget::user_message_display_from_parts uses ide_context prompt stripping.
    message = UserMessage(
        text="context\n## My request for Codex:\n  visible",
        local_images=[LocalImageAttachment("[Image #1]", "a.png")],
        remote_image_urls=["https://example.test/remote.png"],
        text_elements=[element(len("context\n## My request for Codex:\n  "), len("context\n## My request for Codex:\n  visible"))],
    )

    display = user_message_display_for_history(message, UserMessageHistoryRecord.user_message_text())

    assert display.message == "visible"
    assert display.local_images == [Path("a.png")]
    assert display.remote_image_urls == ["https://example.test/remote.png"]
    assert [(elem.byte_range.start, elem.byte_range.end) for elem in display.text_elements] == [(0, 7)]


def test_app_server_input_display_and_pending_compare_key_ignore_skills_and_mentions() -> None:
    # Rust: user_message_display_from_inputs and pending_steer_compare_key_from_items.
    items = [
        AppServerUserInput.text("hello ", [AppServerTextElement.new({"start": 0, "end": 5}, "hello")]),
        AppServerUserInput.image("https://example.test/image.png"),
        AppServerUserInput.local_image("local.png"),
        AppServerUserInput.skill("skill", "/tmp/skill"),
        AppServerUserInput.mention("@repo", "/repo"),
        AppServerUserInput.text("world"),
    ]

    display = ChatWidget.user_message_display_from_inputs(items)
    compare_key = ChatWidget.pending_steer_compare_key_from_items(items)

    assert display.message == "hello world"
    assert display.remote_image_urls == ["https://example.test/image.png"]
    assert display.local_images == [Path("local.png")]
    assert [(elem.byte_range.start, elem.byte_range.end) for elem in display.text_elements] == [(0, 5)]
    assert compare_key == PendingSteerCompareKey(message="hello world", image_count=2)


def test_app_server_text_elements_preserve_byte_range_and_placeholder() -> None:
    # Rust: app_server_text_elements clones protocol TextElement values into app-server DTOs.
    converted = app_server_text_elements([element(2, 5, "abc")])

    assert len(converted) == 1
    assert converted[0].byte_range.start == 2
    assert converted[0].byte_range.end == 5
    assert converted[0].placeholder == "abc"
