"""Pending input coordination owned by ``session::input_queue``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from pycodex.protocol import InterAgentCommunication, ResponseItem


@dataclass
class InputQueue:
    items: list[Any] = field(default_factory=list)
    mailbox_pending_mails: list[InterAgentCommunication] = field(default_factory=list)
    mailbox_subscribers: list[Any] = field(default_factory=list)

    async def extend_pending_input(self, items: Any) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("pending input must be a list or tuple")
        self.items.extend(items)

    async def enqueue_mailbox_communication(self, communication: InterAgentCommunication) -> None:
        if not isinstance(communication, InterAgentCommunication):
            communication = InterAgentCommunication.from_mapping(communication)
        self.mailbox_pending_mails.append(communication)
        for subscriber in tuple(self.mailbox_subscribers):
            subscriber.mark_changed()

    async def subscribe_mailbox(self) -> Any:
        subscriber = _MailboxSubscription()
        self.mailbox_subscribers.append(subscriber)
        if self.mailbox_pending_mails:
            subscriber.mark_changed()
        return subscriber

    async def has_pending_mailbox_items(self) -> bool:
        return bool(self.mailbox_pending_mails)

    async def has_trigger_turn_mailbox_items(self) -> bool:
        return any(mail.trigger_turn for mail in self.mailbox_pending_mails)

    async def drain_mailbox_input_items(self) -> tuple[ResponseItem, ...]:
        pending = tuple(self.mailbox_pending_mails)
        self.mailbox_pending_mails.clear()
        return tuple(
            ResponseItem.from_response_input_item(mail.to_response_input_item())
            for mail in pending
        )

    async def accept_mailbox_delivery_for_turn_state(self, turn_state: Any) -> None:
        turn_state.accept_mailbox_delivery_for_current_turn()

    async def extend_pending_input_for_turn_state(self, turn_state: Any, items: Any) -> None:
        if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
            raise TypeError("pending input must be a list or tuple")
        _turn_state_pending_input_items(turn_state).extend(items)

    async def extend_pending_input_and_accept_mailbox_delivery_for_turn_state(
        self, turn_state: Any, items: Any
    ) -> None:
        await self.extend_pending_input_for_turn_state(turn_state, items)
        await self.accept_mailbox_delivery_for_turn_state(turn_state)

    async def take_pending_input_for_turn_state(self, turn_state: Any) -> tuple[Any, ...]:
        pending = _turn_state_pending_input_items(turn_state)
        items = tuple(pending)
        pending.clear()
        return items

    async def turn_state_for_sub_id(self, active_turn: Any, sub_id: str) -> Any | None:
        active = _active_turn_value(active_turn)
        if active is None:
            return None
        task = getattr(active, "task", None)
        turn_context = getattr(task, "turn_context", None)
        if getattr(turn_context, "sub_id", None) != sub_id:
            return None
        return getattr(active, "turn_state", None)

    async def clear_pending(self, active_turn: Any) -> None:
        active = _active_turn_value(active_turn)
        if active is None:
            return
        turn_state = getattr(active, "turn_state", None)
        if turn_state is None:
            return
        clear_pending_waiters = getattr(turn_state, "clear_pending_waiters", None)
        if callable(clear_pending_waiters):
            clear_pending_waiters()
        _turn_state_pending_input_items(turn_state).clear()

    async def defer_mailbox_delivery_to_next_turn(self, active_turn: Any, sub_id: str) -> None:
        turn_state = await self.turn_state_for_sub_id(active_turn, sub_id)
        if turn_state is None or _turn_state_pending_input_items(turn_state):
            return
        setter = getattr(turn_state, "set_mailbox_delivery_phase", None)
        if callable(setter):
            setter("next_turn")

    async def accept_mailbox_delivery_for_current_turn(self, active_turn: Any, sub_id: str) -> None:
        turn_state = await self.turn_state_for_sub_id(active_turn, sub_id)
        if turn_state is not None:
            await self.accept_mailbox_delivery_for_turn_state(turn_state)

    async def get_pending_input(self, active_turn: Any = None) -> tuple[Any, ...]:
        turn_state = _active_turn_state(active_turn)
        if turn_state is None:
            items = tuple(self.items)
            self.items.clear()
            if self.mailbox_pending_mails:
                items += tuple(await self.drain_mailbox_input_items())
            return items
        pending = _turn_state_pending_input_items(turn_state)
        items = tuple(pending)
        pending.clear()
        if self.items:
            items += tuple(self.items)
            self.items.clear()
        if _accepts_mailbox_delivery_for_current_turn(turn_state) and self.mailbox_pending_mails:
            items += tuple(await self.drain_mailbox_input_items())
        return items

    async def has_pending_input(self, active_turn: Any = None) -> bool:
        turn_state = _active_turn_state(active_turn)
        if turn_state is None:
            return bool(self.items) or bool(self.mailbox_pending_mails)
        if _turn_state_pending_input_items(turn_state) or self.items:
            return True
        return (
            _accepts_mailbox_delivery_for_current_turn(turn_state)
            and bool(self.mailbox_pending_mails)
        )


def _turn_state_pending_input_items(turn_state: Any) -> list[Any]:
    pending_input = getattr(turn_state, "pending_input", None)
    if pending_input is None:
        pending_input = SimpleNamespace(items=[])
        setattr(turn_state, "pending_input", pending_input)
    items = getattr(pending_input, "items", None)
    if items is None:
        items = []
        setattr(pending_input, "items", items)
    if not isinstance(items, list):
        raise TypeError("turn_state.pending_input.items must be a list")
    return items


class _MailboxSubscription:
    def __init__(self) -> None:
        self._changed = asyncio.Event()

    def mark_changed(self) -> None:
        self._changed.set()

    async def changed(self) -> None:
        await self._changed.wait()
        self._changed.clear()

    def has_changed(self) -> bool:
        return self._changed.is_set()


def _active_turn_state(active_turn: Any) -> Any | None:
    active_turn = _active_turn_value(active_turn)
    if active_turn is None:
        return None
    return getattr(active_turn, "turn_state", active_turn)


def _active_turn_value(active_turn: Any) -> Any | None:
    if active_turn is None:
        return None
    value = getattr(active_turn, "value", active_turn)
    return value() if callable(value) else value


def _accepts_mailbox_delivery_for_current_turn(turn_state: Any) -> bool:
    accepts = getattr(turn_state, "accepts_mailbox_delivery_for_current_turn", None)
    return bool(accepts()) if callable(accepts) else True


__all__ = ["InputQueue"]
