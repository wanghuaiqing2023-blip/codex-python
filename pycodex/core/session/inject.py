"""Session injection methods owned by ``core::session::inject``."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pycodex.protocol import ResponseItem, UserInput


async def inject_if_running(
    self: Any,
    items: list[Any] | tuple[Any, ...],
) -> tuple[Any, ...] | None:
    """Return input when idle, otherwise append it atomically to the active turn."""

    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise TypeError("items must be a list or tuple")
    original_items = tuple(items)
    if self.active_turn is None:
        return original_items
    await self.input_queue.extend_pending_input_for_turn_state(
        self.active_turn.turn_state,
        tuple(_pending_input_item(item) for item in original_items),
    )
    return None


async def inject_no_new_turn(
    self: Any,
    items: list[ResponseItem | dict[str, Any]] | tuple[ResponseItem | dict[str, Any], ...],
    current_turn_context: Any | None,
) -> None:
    """Inject into active work or record the items without starting a turn."""

    if isinstance(items, (str, bytes)) or not isinstance(items, (list, tuple)):
        raise TypeError("items must be a list or tuple of ResponseItem or mapping")
    not_injected = await self.inject_if_running(items)
    if not_injected is None:
        return
    turn_context = current_turn_context
    if turn_context is None:
        turn_context = await self.new_default_turn()
    await self.record_conversation_items(
        turn_context,
        tuple(_response_item(item) for item in not_injected),
    )


def _response_item(value: ResponseItem | dict[str, Any]) -> ResponseItem:
    if isinstance(value, ResponseItem):
        return value
    if isinstance(value, dict):
        return ResponseItem.from_mapping(value)
    raise TypeError("items entries must be ResponseItem or mapping")


def _pending_input_item(value: Any) -> Any:
    if isinstance(value, (ResponseItem, UserInput)):
        return value
    if isinstance(value, Mapping):
        value_type = value.get("type")
        if value_type in {"text", "image", "local_image", "skill", "mention"}:
            return UserInput.from_mapping(value)
        return ResponseItem.from_mapping(value)
    return value


__all__ = ["inject_if_running", "inject_no_new_turn"]
