"""Semantic port of Rust ``codex-tui::chatwidget::user_messages``.

The Rust module owns user-message draft models, local-image placeholder remap
logic, history override projection, and app-server input display helpers.  The
Python port keeps the same module boundary with standard-library data models
and existing protocol DTOs.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, List, Optional, Sequence

from pycodex.app_server_protocol.turn import TextElement as AppServerTextElement
from pycodex.app_server_protocol.turn import UserInput as AppServerUserInput
from pycodex.protocol.models import local_image_label_text
from pycodex.protocol.user_input import ByteRange, TextElement

from .._porting import RustTuiModule
from ..bottom_pane import LocalImageAttachment, MentionBinding
from ..bottom_pane.chat_composer import QueuedInputAction
from ..ide_context.prompt import extract_prompt_request_with_offset


RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::user_messages",
    source="codex/codex-rs/tui/src/chatwidget/user_messages.rs",
    status="complete",
)


@dataclass
class UserMessage:
    text: str = ""
    local_images: List[LocalImageAttachment] = field(default_factory=list)
    remote_image_urls: List[str] = field(default_factory=list)
    text_elements: List[TextElement] = field(default_factory=list)
    mention_bindings: List[MentionBinding] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> "UserMessage":
        return cls(text=str(text))


@dataclass(frozen=True)
class UserMessageHistoryOverride:
    text: str = ""
    text_elements: tuple[TextElement, ...] = ()


@dataclass(frozen=True)
class UserMessageHistoryRecord:
    kind: str
    override: Optional[UserMessageHistoryOverride] = None

    @classmethod
    def user_message_text(cls) -> "UserMessageHistoryRecord":
        return cls("UserMessageText")

    @classmethod
    def Override(
        cls, value: UserMessageHistoryOverride | str, text_elements: Iterable[TextElement] = ()
    ) -> "UserMessageHistoryRecord":
        if isinstance(value, UserMessageHistoryOverride):
            override = value
        else:
            override = UserMessageHistoryOverride(str(value), tuple(deepcopy(list(text_elements))))
        return cls("Override", override)


class ShellEscapePolicy(Enum):
    Allow = "Allow"
    Disallow = "Disallow"


@dataclass
class QueuedUserMessage:
    user_message: UserMessage
    action: QueuedInputAction = QueuedInputAction.Plain

    @classmethod
    def new(cls, user_message: UserMessage, action: QueuedInputAction) -> "QueuedUserMessage":
        return cls(deepcopy(user_message), QueuedInputAction(action))

    @classmethod
    def from_user_message(cls, user_message: UserMessage) -> "QueuedUserMessage":
        return cls.new(user_message, QueuedInputAction.Plain)

    def into_user_message(self) -> UserMessage:
        return self.user_message


def from_(user_message: UserMessage) -> QueuedUserMessage:
    return QueuedUserMessage.from_user_message(user_message)


Target = UserMessage


def deref(queued: QueuedUserMessage) -> UserMessage:
    return queued.user_message


class QueueDrain(Enum):
    Continue = "Continue"
    Stop = "Stop"


@dataclass
class ThreadComposerState:
    text: str = ""
    local_images: List[LocalImageAttachment] = field(default_factory=list)
    remote_image_urls: List[str] = field(default_factory=list)
    text_elements: List[TextElement] = field(default_factory=list)
    mention_bindings: List[MentionBinding] = field(default_factory=list)
    pending_pastes: List[tuple[str, str]] = field(default_factory=list)

    def has_content(self) -> bool:
        return bool(
            self.text
            or self.local_images
            or self.remote_image_urls
            or self.text_elements
            or self.mention_bindings
            or self.pending_pastes
        )


@dataclass
class ThreadInputState:
    composer: Optional[ThreadComposerState] = None
    pending_steers: List[UserMessage] = field(default_factory=list)
    pending_steer_history_records: List[UserMessageHistoryRecord] = field(default_factory=list)
    pending_steer_compare_keys: List["PendingSteerCompareKey"] = field(default_factory=list)
    rejected_steers_queue: List[UserMessage] = field(default_factory=list)
    rejected_steer_history_records: List[UserMessageHistoryRecord] = field(default_factory=list)
    queued_user_messages: List[QueuedUserMessage] = field(default_factory=list)
    queued_user_message_history_records: List[UserMessageHistoryRecord] = field(default_factory=list)
    user_turn_pending_start: bool = False
    current_collaboration_mode: object | None = None
    active_collaboration_mask: object | None = None
    task_running: bool = False
    agent_turn_running: bool = False


@dataclass
class PendingSteer:
    user_message: UserMessage
    history_record: UserMessageHistoryRecord
    compare_key: "PendingSteerCompareKey"


def create_initial_user_message(
    text: str | None,
    local_image_paths: Iterable[Path | str],
    text_elements: Iterable[TextElement],
) -> Optional[UserMessage]:
    message_text = text or ""
    paths = list(local_image_paths)
    if not message_text and not paths:
        return None
    return UserMessage(
        text=message_text,
        local_images=[
            LocalImageAttachment(local_image_label_text(idx + 1), Path(path))
            for idx, path in enumerate(paths)
        ],
        remote_image_urls=[],
        text_elements=list(deepcopy(list(text_elements))),
        mention_bindings=[],
    )


def append_text_with_rebased_elements(
    target_text: str,
    target_text_elements: list[TextElement],
    text: str,
    text_elements: Iterable[TextElement],
) -> str:
    offset = len(target_text.encode("utf-8"))
    target_text += text
    for element in text_elements:
        target_text_elements.append(
            TextElement.new(
                ByteRange(
                    element.byte_range.start + offset,
                    element.byte_range.end + offset,
                ),
                element.placeholder_for_conversion_only(),
            )
        )
    return target_text


def app_server_text_elements(elements: Sequence[TextElement]) -> list[AppServerTextElement]:
    return [
        AppServerTextElement.new(
            {"start": element.byte_range.start, "end": element.byte_range.end},
            element.placeholder_for_conversion_only(),
        )
        for element in elements
    ]


def build_placeholder_mapping(
    local_images: Iterable[LocalImageAttachment], next_label: int
) -> tuple[dict[str, str], list[LocalImageAttachment], int]:
    mapping: dict[str, str] = {}
    remapped_images: list[LocalImageAttachment] = []
    for attachment in local_images:
        new_placeholder = local_image_label_text(next_label)
        next_label += 1
        mapping[attachment.placeholder] = new_placeholder
        remapped_images.append(LocalImageAttachment(new_placeholder, attachment.path))
    return mapping, remapped_images, next_label


def remap_placeholders_in_text(
    text: str, text_elements: Iterable[TextElement], mapping: dict[str, str]
) -> tuple[str, list[TextElement]]:
    elements = sorted(deepcopy(list(text_elements)), key=lambda elem: elem.byte_range.start)
    if not mapping:
        return text, elements

    cursor = 0
    rebuilt = ""
    rebuilt_elements: list[TextElement] = []
    text_len = len(text.encode("utf-8"))
    for element in elements:
        start = min(element.byte_range.start, text_len)
        end = min(element.byte_range.end, text_len)
        rebuilt += _slice_by_byte_range(text, cursor, start)

        original = _slice_by_byte_range(text, start, end)
        placeholder = element.placeholder(text)
        replacement = mapping.get(placeholder or "", original)

        elem_start = len(rebuilt.encode("utf-8"))
        rebuilt += replacement
        elem_end = len(rebuilt.encode("utf-8"))

        rebuilt_elements.append(TextElement.new(ByteRange(elem_start, elem_end), replacement if placeholder in mapping else element.placeholder_for_conversion_only()))
        cursor = end
    rebuilt += _slice_by_byte_range(text, cursor, text_len)
    return rebuilt, rebuilt_elements


def remap_placeholders_for_message_and_history_record(
    message: UserMessage,
    history_record: UserMessageHistoryRecord,
    next_label: int,
) -> tuple[UserMessage, UserMessageHistoryRecord, int]:
    mapping, remapped_images, next_label = build_placeholder_mapping(message.local_images, next_label)
    text, text_elements = remap_placeholders_in_text(message.text, message.text_elements, mapping)

    remapped_record = history_record
    if (
        history_record.kind == "Override"
        and history_record.override is not None
        and history_record.override.text
    ):
        history_text, history_elements = remap_placeholders_in_text(
            history_record.override.text,
            history_record.override.text_elements,
            mapping,
        )
        remapped_record = UserMessageHistoryRecord.Override(
            UserMessageHistoryOverride(history_text, tuple(history_elements))
        )

    return (
        UserMessage(
            text=text,
            local_images=remapped_images,
            remote_image_urls=list(message.remote_image_urls),
            text_elements=text_elements,
            mention_bindings=list(deepcopy(message.mention_bindings)),
        ),
        remapped_record,
        next_label,
    )


def remap_placeholders_for_message(message: UserMessage, next_label: int) -> tuple[UserMessage, int]:
    remapped, _, next_label = remap_placeholders_for_message_and_history_record(
        message, UserMessageHistoryRecord.user_message_text(), next_label
    )
    return remapped, next_label


def remap_user_messages_with_history_records(
    messages: Iterable[tuple[UserMessage, UserMessageHistoryRecord]]
) -> list[tuple[UserMessage, UserMessageHistoryRecord]]:
    message_list = list(messages)
    next_label = sum(len(message.remote_image_urls) for message, _ in message_list) + 1
    remapped: list[tuple[UserMessage, UserMessageHistoryRecord]] = []
    for message, record in message_list:
        remapped_message, remapped_record, next_label = remap_placeholders_for_message_and_history_record(
            message, record, next_label
        )
        remapped.append((remapped_message, remapped_record))
    return remapped


def merge_user_messages(messages: Iterable[UserMessage]) -> UserMessage:
    remapped = remap_user_messages_with_history_records(
        (message, UserMessageHistoryRecord.user_message_text()) for message in messages
    )
    return merge_remapped_user_messages(message for message, _ in remapped)


def merge_remapped_user_messages(messages: Iterable[UserMessage]) -> UserMessage:
    combined = UserMessage()
    for idx, message in enumerate(messages):
        if idx > 0:
            combined.text += "\n"
        combined.text = append_text_with_rebased_elements(
            combined.text,
            combined.text_elements,
            message.text,
            message.text_elements,
        )
        combined.local_images.extend(deepcopy(message.local_images))
        combined.remote_image_urls.extend(message.remote_image_urls)
        combined.mention_bindings.extend(deepcopy(message.mention_bindings))
    return combined


def user_message_for_restore(
    message: UserMessage, history_record: UserMessageHistoryRecord
) -> UserMessage:
    if history_record.kind == "Override" and history_record.override is not None and history_record.override.text:
        restored = deepcopy(message)
        restored.text = history_record.override.text
        restored.text_elements = list(deepcopy(history_record.override.text_elements))
        return restored
    return message


def user_message_preview_text(
    message: UserMessage, history_record: Optional[UserMessageHistoryRecord]
) -> str:
    if history_record and history_record.kind == "Override" and history_record.override and history_record.override.text:
        return history_record.override.text
    return message.text


def user_message_display_for_history(
    message: UserMessage, history_record: UserMessageHistoryRecord
) -> "UserMessageDisplay":
    restored = user_message_for_restore(message, history_record)
    return ChatWidget.user_message_display_from_parts(
        restored.text,
        restored.text_elements,
        [image.path for image in restored.local_images],
        restored.remote_image_urls,
    )


def merge_user_messages_with_history_record(
    messages: Iterable[tuple[UserMessage, UserMessageHistoryRecord]]
) -> tuple[UserMessage, UserMessageHistoryRecord]:
    remapped = remap_user_messages_with_history_records(messages)
    if all(record == UserMessageHistoryRecord.user_message_text() for _, record in remapped):
        history_record = UserMessageHistoryRecord.user_message_text()
    else:
        history_text = ""
        history_elements: list[TextElement] = []
        segment_count = 0
        for message, record in remapped:
            if record.kind == "Override" and record.override is not None:
                if record.override.text:
                    if segment_count:
                        history_text += "\n"
                    history_text = append_text_with_rebased_elements(
                        history_text,
                        history_elements,
                        record.override.text,
                        record.override.text_elements,
                    )
                    segment_count += 1
                elif not message.text:
                    continue
                else:
                    if segment_count:
                        history_text += "\n"
                    history_text = append_text_with_rebased_elements(
                        history_text,
                        history_elements,
                        message.text,
                        message.text_elements,
                    )
                    segment_count += 1
            else:
                if segment_count:
                    history_text += "\n"
                history_text = append_text_with_rebased_elements(
                    history_text,
                    history_elements,
                    message.text,
                    message.text_elements,
                )
                segment_count += 1
        history_record = UserMessageHistoryRecord.Override(
            UserMessageHistoryOverride(history_text, tuple(history_elements))
        )
    return merge_remapped_user_messages(message for message, _ in remapped), history_record


@dataclass
class UserMessageDisplay:
    message: str = ""
    remote_image_urls: List[str] = field(default_factory=list)
    local_images: List[Path] = field(default_factory=list)
    text_elements: List[TextElement] = field(default_factory=list)


@dataclass(frozen=True)
class PendingSteerCompareKey:
    message: str
    image_count: int


class ChatWidget:
    @staticmethod
    def user_message_display_from_parts(
        message: str,
        text_elements: Iterable[TextElement],
        local_images: Iterable[Path | str],
        remote_image_urls: Iterable[str],
    ) -> UserMessageDisplay:
        visible, prompt_request_offset = extract_prompt_request_with_offset(message)
        prompt_request_end = prompt_request_offset + len(visible.encode("utf-8"))
        shifted_elements: list[TextElement] = []
        for element in text_elements:
            range_ = element.byte_range
            if range_.start < prompt_request_offset or range_.end > prompt_request_end:
                continue
            shifted_elements.append(
                TextElement.new(
                    ByteRange(
                        range_.start - prompt_request_offset,
                        range_.end - prompt_request_offset,
                    ),
                    element.placeholder_for_conversion_only(),
                )
            )
        return UserMessageDisplay(
            message=visible,
            remote_image_urls=list(remote_image_urls),
            local_images=[Path(path) for path in local_images],
            text_elements=shifted_elements,
        )

    @staticmethod
    def pending_steer_compare_key_from_items(
        items: Iterable[AppServerUserInput],
    ) -> PendingSteerCompareKey:
        message = ""
        image_count = 0
        for item in items:
            if item.type == "text":
                message += str(item.fields.get("text", ""))
            elif item.type in {"image", "localImage"}:
                image_count += 1
        return PendingSteerCompareKey(message, image_count)

    @staticmethod
    def user_message_display_from_inputs(items: Iterable[AppServerUserInput]) -> UserMessageDisplay:
        message = ""
        remote_image_urls: list[str] = []
        local_images: list[Path] = []
        text_elements: list[TextElement] = []
        for item in items:
            if item.type == "text":
                text = str(item.fields.get("text", ""))
                current = [
                    _protocol_text_element_from_app_server(raw)
                    for raw in item.fields.get("textElements", [])
                ]
                message = append_text_with_rebased_elements(message, text_elements, text, current)
            elif item.type == "image":
                remote_image_urls.append(str(item.fields.get("url", "")))
            elif item.type == "localImage":
                local_images.append(Path(str(item.fields.get("path", ""))))
        return ChatWidget.user_message_display_from_parts(
            message, text_elements, local_images, remote_image_urls
        )


def _protocol_text_element_from_app_server(value: object) -> TextElement:
    if isinstance(value, AppServerTextElement):
        return TextElement.new(
            ByteRange(value.byte_range.start, value.byte_range.end),
            value.placeholder,
        )
    if isinstance(value, dict):
        raw_range = value.get("byteRange", value.get("byte_range", {}))
        if not isinstance(raw_range, dict):
            raw_range = {}
        return TextElement.new(
            ByteRange(int(raw_range.get("start", 0)), int(raw_range.get("end", 0))),
            value.get("placeholder") if isinstance(value.get("placeholder"), str) else None,
        )
    raise TypeError("text element must be an app-server TextElement or mapping")


def _slice_by_byte_range(text: str, start: int, end: int) -> str:
    encoded = text.encode("utf-8")
    start = max(0, min(start, len(encoded)))
    end = max(start, min(end, len(encoded)))
    try:
        return encoded[start:end].decode("utf-8")
    except UnicodeDecodeError:
        return ""


__all__ = [
    "ChatWidget",
    "PendingSteer",
    "PendingSteerCompareKey",
    "QueueDrain",
    "QueuedUserMessage",
    "RUST_MODULE",
    "ShellEscapePolicy",
    "Target",
    "ThreadComposerState",
    "ThreadInputState",
    "UserMessage",
    "UserMessageDisplay",
    "UserMessageHistoryOverride",
    "UserMessageHistoryRecord",
    "app_server_text_elements",
    "append_text_with_rebased_elements",
    "build_placeholder_mapping",
    "create_initial_user_message",
    "deref",
    "from_",
    "merge_remapped_user_messages",
    "merge_user_messages",
    "merge_user_messages_with_history_record",
    "remap_placeholders_for_message",
    "remap_placeholders_for_message_and_history_record",
    "remap_placeholders_in_text",
    "remap_user_messages_with_history_records",
    "user_message_display_for_history",
    "user_message_for_restore",
    "user_message_preview_text",
]
