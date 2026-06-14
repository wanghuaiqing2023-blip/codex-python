"""Semantic Python port of Rust ``codex-tui::chatwidget::input_restore``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/input_restore.rs``.

The Rust module owns input queue restore behavior for ``ChatWidget``. Python
represents the surrounding widget state as dataclasses so queue and snapshot
transformations remain testable without ratatui or the full chat runtime.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Deque, Iterable, Sequence

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::input_restore",
    source="codex/codex-rs/tui/src/chatwidget/input_restore.rs",
)


class UserMessageHistoryRecordKind(Enum):
    USER_MESSAGE_TEXT = "UserMessageText"
    OVERRIDE = "Override"


class QueuedInputAction(Enum):
    PLAIN = "Plain"


class InterruptedTurnNoticeMode(Enum):
    NORMAL = "Normal"
    SUPPRESS = "Suppress"


@dataclass(frozen=True)
class TextElement:
    byte_range: tuple[int, int]
    kind: str = "text"
    payload: Any | None = None

    def shift(self, offset: int) -> "TextElement":
        start, end = self.byte_range
        return TextElement((start + offset, end + offset), self.kind, self.payload)


@dataclass(frozen=True)
class MentionBinding:
    value: Any


@dataclass(frozen=True)
class LocalImageAttachment:
    path: Path | str
    placeholder: str = ""


@dataclass(frozen=True)
class UserMessageHistoryOverride:
    text: str = ""
    text_elements: tuple[TextElement, ...] = ()


@dataclass(frozen=True)
class UserMessageHistoryRecord:
    kind: UserMessageHistoryRecordKind = UserMessageHistoryRecordKind.USER_MESSAGE_TEXT
    override: UserMessageHistoryOverride | None = None

    @classmethod
    def text(cls) -> "UserMessageHistoryRecord":
        return cls(UserMessageHistoryRecordKind.USER_MESSAGE_TEXT)

    @classmethod
    def override_text(
        cls,
        text: str,
        text_elements: Sequence[TextElement] = (),
    ) -> "UserMessageHistoryRecord":
        return cls(
            UserMessageHistoryRecordKind.OVERRIDE,
            UserMessageHistoryOverride(text=text, text_elements=tuple(text_elements)),
        )

    def has_non_empty_override(self) -> bool:
        return self.kind is UserMessageHistoryRecordKind.OVERRIDE and bool(
            self.override and self.override.text
        )


@dataclass
class UserMessage:
    text: str = ""
    local_images: list[LocalImageAttachment] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    text_elements: list[TextElement] = field(default_factory=list)
    mention_bindings: list[MentionBinding] = field(default_factory=list)

    @classmethod
    def from_text(cls, text: str) -> "UserMessage":
        return cls(text=text)

    def clone(self) -> "UserMessage":
        return UserMessage(
            text=self.text,
            local_images=list(self.local_images),
            remote_image_urls=list(self.remote_image_urls),
            text_elements=list(self.text_elements),
            mention_bindings=list(self.mention_bindings),
        )


@dataclass
class QueuedUserMessage:
    user_message: UserMessage
    action: QueuedInputAction = QueuedInputAction.PLAIN

    @classmethod
    def from_message(cls, message: UserMessage | str) -> "QueuedUserMessage":
        if isinstance(message, str):
            message = UserMessage.from_text(message)
        return cls(message)

    def into_user_message(self) -> UserMessage:
        return self.user_message


@dataclass(frozen=True)
class PendingSteerCompareKey:
    message: str
    image_count: int

    @classmethod
    def from_message(cls, message: UserMessage) -> "PendingSteerCompareKey":
        return cls(
            message=message.text,
            image_count=len(message.local_images) + len(message.remote_image_urls),
        )


@dataclass
class PendingSteer:
    user_message: UserMessage
    history_record: UserMessageHistoryRecord = field(default_factory=UserMessageHistoryRecord.text)
    compare_key: PendingSteerCompareKey | None = None

    def __post_init__(self) -> None:
        if self.compare_key is None:
            self.compare_key = PendingSteerCompareKey.from_message(self.user_message)


@dataclass
class ComposerDraftSnapshot:
    text: str = ""
    local_images: list[LocalImageAttachment] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    text_elements: list[TextElement] = field(default_factory=list)
    mention_bindings: list[MentionBinding] = field(default_factory=list)
    pending_pastes: list[tuple[str, str]] = field(default_factory=list)

    def to_user_message(self) -> UserMessage:
        return UserMessage(
            text=self.text,
            local_images=list(self.local_images),
            remote_image_urls=list(self.remote_image_urls),
            text_elements=list(self.text_elements),
            mention_bindings=list(self.mention_bindings),
        )


@dataclass
class ThreadComposerState:
    text: str = ""
    local_images: list[LocalImageAttachment] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)
    text_elements: list[TextElement] = field(default_factory=list)
    mention_bindings: list[MentionBinding] = field(default_factory=list)
    pending_pastes: list[tuple[str, str]] = field(default_factory=list)

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
    composer: ThreadComposerState | None = None
    pending_steers: Deque[UserMessage] = field(default_factory=deque)
    pending_steer_history_records: Deque[UserMessageHistoryRecord] = field(default_factory=deque)
    pending_steer_compare_keys: Deque[PendingSteerCompareKey] = field(default_factory=deque)
    rejected_steers_queue: Deque[UserMessage] = field(default_factory=deque)
    rejected_steer_history_records: Deque[UserMessageHistoryRecord] = field(default_factory=deque)
    queued_user_messages: Deque[QueuedUserMessage] = field(default_factory=deque)
    queued_user_message_history_records: Deque[UserMessageHistoryRecord] = field(
        default_factory=deque
    )
    user_turn_pending_start: bool = False
    current_collaboration_mode: Any | None = None
    active_collaboration_mask: Any | None = None
    task_running: bool = False
    agent_turn_running: bool = False


@dataclass
class InputQueue:
    pending_steers: Deque[PendingSteer] = field(default_factory=deque)
    rejected_steers_queue: Deque[UserMessage] = field(default_factory=deque)
    rejected_steer_history_records: Deque[UserMessageHistoryRecord] = field(default_factory=deque)
    queued_user_messages: Deque[QueuedUserMessage] = field(default_factory=deque)
    queued_user_message_history_records: Deque[UserMessageHistoryRecord] = field(
        default_factory=deque
    )
    user_turn_pending_start: bool = False
    submit_pending_steers_after_interrupt: bool = False
    suppress_queue_autosend: bool = False

    def clear(self) -> None:
        self.pending_steers.clear()
        self.rejected_steers_queue.clear()
        self.rejected_steer_history_records.clear()
        self.queued_user_messages.clear()
        self.queued_user_message_history_records.clear()
        self.user_turn_pending_start = False


@dataclass
class InputRestoreModel:
    """Semantic stand-in for ``ChatWidget`` fields touched by input_restore.rs."""

    input_queue: InputQueue = field(default_factory=InputQueue)
    initial_user_message: UserMessage | None = None
    suppress_initial_user_message_submit: bool = False
    composer: ComposerDraftSnapshot = field(default_factory=ComposerDraftSnapshot)
    remote_image_urls: list[str] = field(default_factory=list)
    submitted_messages: list[tuple[UserMessage, UserMessageHistoryRecord]] = field(
        default_factory=list
    )
    restored_messages: list[UserMessage] = field(default_factory=list)
    history_events: list[tuple[str, str]] = field(default_factory=list)
    redraw_requests: int = 0
    pending_preview_refreshes: int = 0
    finalized_turns: int = 0
    interrupted_turn_notice_mode: InterruptedTurnNoticeMode = InterruptedTurnNoticeMode.NORMAL
    current_collaboration_mode: Any | None = None
    active_collaboration_mask: Any | None = None
    task_running: bool = False
    agent_turn_running: bool = False

    def set_initial_user_message_submit_suppressed(self, suppressed: bool) -> None:
        self.suppress_initial_user_message_submit = bool(suppressed)

    def submit_initial_user_message_if_pending(self) -> None:
        if self.initial_user_message is not None:
            message = self.initial_user_message
            self.initial_user_message = None
            self.submit_user_message(message)

    def submit_user_message(self, user_message: UserMessage) -> None:
        self.submit_user_message_with_history_record(user_message, UserMessageHistoryRecord.text())

    def submit_user_message_with_history_record(
        self,
        user_message: UserMessage,
        history_record: UserMessageHistoryRecord,
    ) -> None:
        self.submitted_messages.append((user_message, history_record))

    def pop_next_queued_user_message(
        self,
    ) -> tuple[QueuedUserMessage, UserMessageHistoryRecord] | None:
        queue = self.input_queue
        if not queue.rejected_steers_queue:
            if not queue.queued_user_messages:
                return None
            return queue.queued_user_messages.popleft(), _popleft_or_text(
                queue.queued_user_message_history_records
            )

        rejected_messages = list(queue.rejected_steers_queue)
        queue.rejected_steers_queue.clear()
        history_records = _resize_records(
            list(queue.rejected_steer_history_records), len(rejected_messages)
        )
        queue.rejected_steer_history_records.clear()
        message, history_record = merge_user_messages_with_history_record(
            zip(rejected_messages, history_records)
        )
        return QueuedUserMessage.from_message(message), history_record

    def pop_latest_queued_user_message(self) -> UserMessage | None:
        queue = self.input_queue
        if queue.queued_user_messages:
            return user_message_for_restore(
                queue.queued_user_messages.pop().into_user_message(),
                _pop_or_text(queue.queued_user_message_history_records),
            )
        if not queue.rejected_steers_queue:
            return None
        return user_message_for_restore(
            queue.rejected_steers_queue.pop(),
            _pop_or_text(queue.rejected_steer_history_records),
        )

    def enqueue_rejected_steer(self) -> bool:
        if not self.input_queue.pending_steers:
            return False
        pending_steer = self.input_queue.pending_steers.popleft()
        self.input_queue.rejected_steers_queue.append(pending_steer.user_message)
        self.input_queue.rejected_steer_history_records.append(pending_steer.history_record)
        self.refresh_pending_input_preview()
        return True

    def on_interrupted_turn(self, reason: str = "interrupted") -> None:
        self.finalize_turn()
        send_pending = self.input_queue.submit_pending_steers_after_interrupt
        self.input_queue.submit_pending_steers_after_interrupt = False
        if self.interrupted_turn_notice_mode is not InterruptedTurnNoticeMode.SUPPRESS:
            if send_pending:
                self.history_events.append(
                    ("info", "Model interrupted to submit steer instructions.")
                )
            else:
                self.history_events.append(("error", self.interrupted_turn_message(reason)))

        if send_pending:
            pending = [
                (steer.user_message, steer.history_record)
                for steer in self.input_queue.pending_steers
            ]
            self.input_queue.pending_steers.clear()
            if pending:
                message, history_record = merge_user_messages_with_history_record(pending)
                self.submit_user_message_with_history_record(message, history_record)
            elif (combined := self.drain_pending_messages_for_restore()) is not None:
                self.restore_user_message_to_composer(combined)
        elif (combined := self.drain_pending_messages_for_restore()) is not None:
            self.restore_user_message_to_composer(combined)

        self.refresh_pending_input_preview()
        self.request_redraw()

    def drain_pending_messages_for_restore(self) -> UserMessage | None:
        if not self.input_queue.pending_steers and not self.has_queued_follow_up_messages():
            return None

        to_merge: list[UserMessage] = []
        queue = self.input_queue

        rejected_messages = list(queue.rejected_steers_queue)
        queue.rejected_steers_queue.clear()
        rejected_records = _resize_records(
            list(queue.rejected_steer_history_records), len(rejected_messages)
        )
        queue.rejected_steer_history_records.clear()
        to_merge.extend(
            user_message_for_restore(message, record)
            for message, record in zip(rejected_messages, rejected_records)
        )

        to_merge.extend(
            user_message_for_restore(steer.user_message, steer.history_record)
            for steer in queue.pending_steers
        )
        queue.pending_steers.clear()

        queued_messages = list(queue.queued_user_messages)
        queue.queued_user_messages.clear()
        queued_records = _resize_records(
            list(queue.queued_user_message_history_records), len(queued_messages)
        )
        queue.queued_user_message_history_records.clear()
        to_merge.extend(
            user_message_for_restore(message.into_user_message(), record)
            for message, record in zip(queued_messages, queued_records)
        )

        existing = self.composer.to_user_message()
        if existing.text or existing.local_images or existing.remote_image_urls:
            to_merge.append(existing)

        return merge_user_messages(to_merge)

    def restore_user_message_to_composer(self, user_message: UserMessage) -> None:
        self.remote_image_urls = list(user_message.remote_image_urls)
        self.composer = ComposerDraftSnapshot(
            text=user_message.text,
            text_elements=list(user_message.text_elements),
            local_images=list(user_message.local_images),
            remote_image_urls=list(user_message.remote_image_urls),
            mention_bindings=list(user_message.mention_bindings),
            pending_pastes=[],
        )
        self.restored_messages.append(user_message)

    def capture_thread_input_state(self) -> ThreadInputState:
        composer_state = ThreadComposerState(
            text=self.composer.text,
            local_images=list(self.composer.local_images),
            remote_image_urls=list(self.composer.remote_image_urls),
            text_elements=list(self.composer.text_elements),
            mention_bindings=list(self.composer.mention_bindings),
            pending_pastes=list(self.composer.pending_pastes),
        )
        return ThreadInputState(
            composer=composer_state if composer_state.has_content() else None,
            pending_steers=deque(steer.user_message for steer in self.input_queue.pending_steers),
            pending_steer_history_records=deque(
                steer.history_record for steer in self.input_queue.pending_steers
            ),
            pending_steer_compare_keys=deque(
                steer.compare_key
                for steer in self.input_queue.pending_steers
                if steer.compare_key is not None
            ),
            rejected_steers_queue=deque(self.input_queue.rejected_steers_queue),
            rejected_steer_history_records=deque(self.input_queue.rejected_steer_history_records),
            queued_user_messages=deque(self.input_queue.queued_user_messages),
            queued_user_message_history_records=deque(
                self.input_queue.queued_user_message_history_records
            ),
            user_turn_pending_start=self.input_queue.user_turn_pending_start,
            current_collaboration_mode=self.current_collaboration_mode,
            active_collaboration_mask=self.active_collaboration_mask,
            task_running=self.task_running,
            agent_turn_running=self.agent_turn_running,
        )

    def restore_thread_input_state(self, input_state: ThreadInputState | None) -> None:
        restored_task_running = bool(input_state and input_state.task_running)
        if input_state is None:
            self.agent_turn_running = False
            self.input_queue.clear()
            self.remote_image_urls = []
            self.composer = ComposerDraftSnapshot()
        else:
            self.current_collaboration_mode = input_state.current_collaboration_mode
            self.active_collaboration_mask = input_state.active_collaboration_mask
            self.agent_turn_running = input_state.agent_turn_running
            self.input_queue.user_turn_pending_start = input_state.user_turn_pending_start
            if input_state.composer is None:
                self.remote_image_urls = []
                self.composer = ComposerDraftSnapshot()
            else:
                composer = input_state.composer
                self.remote_image_urls = list(composer.remote_image_urls)
                self.composer = ComposerDraftSnapshot(
                    text=composer.text,
                    local_images=list(composer.local_images),
                    remote_image_urls=list(composer.remote_image_urls),
                    text_elements=list(composer.text_elements),
                    mention_bindings=list(composer.mention_bindings),
                    pending_pastes=list(composer.pending_pastes),
                )

            pending_records = _resize_records(
                list(input_state.pending_steer_history_records), len(input_state.pending_steers)
            )
            pending_keys = deque(input_state.pending_steer_compare_keys)
            self.input_queue.pending_steers = deque(
                PendingSteer(
                    user_message=message,
                    history_record=record,
                    compare_key=pending_keys.popleft()
                    if pending_keys
                    else PendingSteerCompareKey.from_message(message),
                )
                for message, record in zip(input_state.pending_steers, pending_records)
            )
            self.input_queue.rejected_steers_queue = deque(input_state.rejected_steers_queue)
            self.input_queue.rejected_steer_history_records = deque(
                _resize_records(
                    list(input_state.rejected_steer_history_records),
                    len(self.input_queue.rejected_steers_queue),
                )
            )
            self.input_queue.queued_user_messages = deque(input_state.queued_user_messages)
            self.input_queue.queued_user_message_history_records = deque(
                _resize_records(
                    list(input_state.queued_user_message_history_records),
                    len(self.input_queue.queued_user_messages),
                )
            )

        if restored_task_running and not self.task_running:
            self.task_running = True
        self.refresh_pending_input_preview()
        self.request_redraw()

    def set_queue_autosend_suppressed(self, suppressed: bool) -> None:
        self.input_queue.suppress_queue_autosend = bool(suppressed)

    def has_queued_follow_up_messages(self) -> bool:
        return bool(self.input_queue.rejected_steers_queue or self.input_queue.queued_user_messages)

    def finalize_turn(self) -> None:
        self.finalized_turns += 1
        self.agent_turn_running = False

    def interrupted_turn_message(self, reason: str) -> str:
        return f"Turn interrupted: {reason}"

    def refresh_pending_input_preview(self) -> None:
        self.pending_preview_refreshes += 1

    def request_redraw(self) -> None:
        self.redraw_requests += 1


def user_message_for_restore(
    message: UserMessage,
    history_record: UserMessageHistoryRecord,
) -> UserMessage:
    if history_record.has_non_empty_override() and history_record.override is not None:
        restored = message.clone()
        restored.text = history_record.override.text
        restored.text_elements = list(history_record.override.text_elements)
        return restored
    return message


def merge_user_messages(messages: Iterable[UserMessage]) -> UserMessage:
    combined = UserMessage()
    for index, message in enumerate(messages):
        if index > 0:
            combined.text += "\n"
        offset = len(combined.text.encode("utf-8"))
        combined.text += message.text
        combined.text_elements.extend(element.shift(offset) for element in message.text_elements)
        combined.local_images.extend(message.local_images)
        combined.remote_image_urls.extend(message.remote_image_urls)
        combined.mention_bindings.extend(message.mention_bindings)
    return combined


def merge_user_messages_with_history_record(
    messages: Iterable[tuple[UserMessage, UserMessageHistoryRecord]],
) -> tuple[UserMessage, UserMessageHistoryRecord]:
    pairs = [(user_message_for_restore(message, record), record) for message, record in messages]
    merged = merge_user_messages(message for message, _ in pairs)
    if all(record.kind is UserMessageHistoryRecordKind.USER_MESSAGE_TEXT for _, record in pairs):
        return merged, UserMessageHistoryRecord.text()

    history_segments: list[UserMessage] = []
    for message, record in pairs:
        if record.has_non_empty_override() and record.override is not None:
            history_segments.append(
                UserMessage(
                    text=record.override.text,
                    text_elements=list(record.override.text_elements),
                )
            )
        elif record.kind is UserMessageHistoryRecordKind.OVERRIDE and not message.text:
            continue
        else:
            history_segments.append(
                UserMessage(text=message.text, text_elements=list(message.text_elements))
            )
    history_message = merge_user_messages(history_segments)
    return merged, UserMessageHistoryRecord.override_text(
        history_message.text,
        history_message.text_elements,
    )


def _resize_records(
    records: list[UserMessageHistoryRecord],
    length: int,
) -> list[UserMessageHistoryRecord]:
    if len(records) < length:
        records.extend(UserMessageHistoryRecord.text() for _ in range(length - len(records)))
    return records[:length]


def _popleft_or_text(records: Deque[UserMessageHistoryRecord]) -> UserMessageHistoryRecord:
    return records.popleft() if records else UserMessageHistoryRecord.text()


def _pop_or_text(records: Deque[UserMessageHistoryRecord]) -> UserMessageHistoryRecord:
    return records.pop() if records else UserMessageHistoryRecord.text()


__all__ = [
    "ComposerDraftSnapshot",
    "InputQueue",
    "InputRestoreModel",
    "InterruptedTurnNoticeMode",
    "LocalImageAttachment",
    "MentionBinding",
    "PendingSteer",
    "PendingSteerCompareKey",
    "QueuedInputAction",
    "QueuedUserMessage",
    "RUST_MODULE",
    "TextElement",
    "ThreadComposerState",
    "ThreadInputState",
    "UserMessage",
    "UserMessageHistoryOverride",
    "UserMessageHistoryRecord",
    "UserMessageHistoryRecordKind",
    "merge_user_messages",
    "merge_user_messages_with_history_record",
    "user_message_for_restore",
]
