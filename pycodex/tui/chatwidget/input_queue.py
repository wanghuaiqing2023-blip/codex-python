"""Queued-input state for ``codex-tui::chatwidget::input_queue``.

This module owns the mutable queues around queued user input, rejected steers,
and pending steers.  Python keeps the same reducer-style state bag and exposes
plain preview strings; richer ``UserMessage`` rendering remains owned by
``chatwidget::user_messages``.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Iterable

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::input_queue",
    source="codex/codex-rs/tui/src/chatwidget/input_queue.rs",
)


@dataclass(eq=True)
class PendingInputPreview:
    queued_messages: list[str] = field(default_factory=list)
    pending_steers: list[str] = field(default_factory=list)
    rejected_steers: list[str] = field(default_factory=list)


@dataclass
class PendingSteer:
    user_message: Any
    history_record: Any = None
    compare_key: Any = None


@dataclass
class InputQueueState:
    queued_user_messages: Deque[Any] = field(default_factory=deque)
    queued_user_message_history_records: Deque[Any] = field(default_factory=deque)
    user_turn_pending_start: bool = False
    rejected_steers_queue: Deque[Any] = field(default_factory=deque)
    rejected_steer_history_records: Deque[Any] = field(default_factory=deque)
    pending_steers: Deque[PendingSteer | Any] = field(default_factory=deque)
    submit_pending_steers_after_interrupt: bool = False
    suppress_queue_autosend: bool = False

    def has_queued_follow_up_messages(self) -> bool:
        return bool(self.rejected_steers_queue or self.queued_user_messages)

    def clear(self) -> None:
        self.queued_user_messages.clear()
        self.queued_user_message_history_records.clear()
        self.user_turn_pending_start = False
        self.rejected_steers_queue.clear()
        self.rejected_steer_history_records.clear()
        self.pending_steers.clear()
        self.submit_pending_steers_after_interrupt = False

    def preview(self) -> PendingInputPreview:
        queued_messages = [
            user_message_preview_text(message, _get_index(self.queued_user_message_history_records, idx))
            for idx, message in enumerate(self.queued_user_messages)
        ]
        pending_steers = [
            user_message_preview_text(_get(steer, "user_message"), _get(steer, "history_record"))
            for steer in self.pending_steers
        ]
        rejected_steers = [
            user_message_preview_text(message, _get_index(self.rejected_steer_history_records, idx))
            for idx, message in enumerate(self.rejected_steers_queue)
        ]
        return PendingInputPreview(
            queued_messages=queued_messages,
            pending_steers=pending_steers,
            rejected_steers=rejected_steers,
        )

    def enqueue_user_message(self, message: Any, history_record: Any = None) -> None:
        self.queued_user_messages.append(message)
        if history_record is not None:
            self.queued_user_message_history_records.append(history_record)

    def enqueue_rejected_steer(self, message: Any, history_record: Any = None) -> None:
        self.rejected_steers_queue.append(message)
        if history_record is not None:
            self.rejected_steer_history_records.append(history_record)

    def enqueue_pending_steer(self, user_message: Any, history_record: Any = None, compare_key: Any = None) -> None:
        self.pending_steers.append(PendingSteer(user_message, history_record, compare_key))


def user_message_preview_text(message: Any, history_record: Any = None) -> str:
    """Small preview adapter matching this module's dependency use.

    Rust delegates to ``chatwidget::user_messages::user_message_preview_text``.
    For this module's queue contract, the relevant behavior is history-record
    override first, otherwise user-message text.
    """

    history = _history_record_text(history_record)
    if history is not None:
        return history
    return _message_text(message)


def _history_record_text(history_record: Any) -> str | None:
    if history_record is None:
        return None
    if isinstance(history_record, str):
        if history_record == "UserMessageText":
            return None
        return history_record
    if isinstance(history_record, dict):
        for key in ("preview", "text", "display", "history_text"):
            value = history_record.get(key)
            if value is not None:
                return str(value)
        kind = history_record.get("kind")
        if kind == "UserMessageText":
            return None
    for name in ("preview", "text", "display", "history_text"):
        value = getattr(history_record, name, None)
        if value is not None:
            return str(value)
    kind = getattr(history_record, "kind", None)
    if kind == "UserMessageText":
        return None
    return None


def _message_text(message: Any) -> str:
    if message is None:
        return ""
    if isinstance(message, str):
        return message
    if isinstance(message, dict):
        for key in ("text", "message", "content", "input"):
            value = message.get(key)
            if value is not None:
                return str(value)
        payload = message.get("_payload")
        if payload is not None:
            return _message_text(payload)
    for name in ("text", "message", "content", "input", "_payload"):
        value = getattr(message, name, None)
        if value is not None:
            return _message_text(value) if name == "_payload" else str(value)
    return str(message)


def _get(obj: Any, name: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _get_index(values: Iterable[Any], index: int) -> Any | None:
    if hasattr(values, "__getitem__"):
        try:
            return values[index]  # type: ignore[index]
        except IndexError:
            return None
    for idx, value in enumerate(values):
        if idx == index:
            return value
    return None


__all__ = [
    "InputQueueState",
    "PendingInputPreview",
    "PendingSteer",
    "RUST_MODULE",
    "user_message_preview_text",
]
