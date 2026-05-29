"""Rollout truncation helpers ported from ``core/src/thread_rollout_truncation.rs``."""

from __future__ import annotations

import sys
from collections.abc import Iterable, Sequence
from typing import Any

from pycodex.protocol import (
    EventMsg,
    InitialHistory,
    InterAgentCommunication,
    RolloutItem,
    ThreadRolledBackEvent,
)
from pycodex.protocol.models import ResponseItem

from .context import is_contextual_user_fragment

USIZE_MAX = sys.maxsize * 2 + 1


def _ensure_usize(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{field} must be a usize integer")
    if value < 0:
        raise ValueError(f"{field} must be non-negative")
    if value > USIZE_MAX:
        raise ValueError(f"{field} exceeds usize::MAX")
    return value


def initial_history_has_prior_user_turns(conversation_history: InitialHistory) -> bool:
    history = InitialHistory.from_mapping(conversation_history)
    return history.scan_rollout_items(rollout_item_is_user_turn_boundary)


def rollout_item_is_user_turn_boundary(item: RolloutItem | Any) -> bool:
    rollout_item = _rollout_item(item)
    if rollout_item.type != "response_item":
        return False
    response_item = _response_item(rollout_item.payload)
    return response_item is not None and is_user_turn_boundary(response_item)


def user_message_positions_in_rollout(items: Sequence[RolloutItem | Any]) -> list[int]:
    user_positions: list[int] = []
    for idx, item in enumerate(items):
        rollout_item = _rollout_item(item)
        if rollout_item.type == "response_item":
            response_item = _response_item(rollout_item.payload)
            if response_item is not None and _is_real_user_message_boundary(response_item):
                user_positions.append(idx)
            continue

        rollback = _thread_rolled_back_event(rollout_item)
        if rollback is not None:
            del user_positions[len(user_positions) - _saturating_num_turns(rollback.num_turns) :]
    return user_positions


def fork_turn_positions_in_rollout(items: Sequence[RolloutItem | Any]) -> list[int]:
    rollback_turn_positions: list[int] = []
    fork_turn_positions: list[int] = []
    for idx, item in enumerate(items):
        rollout_item = _rollout_item(item)
        if rollout_item.type == "response_item":
            response_item = _response_item(rollout_item.payload)
            if response_item is None:
                continue
            if is_user_turn_boundary(response_item):
                rollback_turn_positions.append(idx)
            if _is_real_user_message_boundary(response_item) or _is_trigger_turn_boundary(response_item):
                fork_turn_positions.append(idx)
            continue

        rollback = _thread_rolled_back_event(rollout_item)
        if rollback is None:
            continue
        num_turns = _saturating_num_turns(rollback.num_turns)
        if num_turns == 0 or not rollback_turn_positions:
            continue

        if len(rollback_turn_positions) >= num_turns:
            rollback_start_idx = rollback_turn_positions[len(rollback_turn_positions) - num_turns]
        else:
            rollback_start_idx = rollback_turn_positions[0]
        del rollback_turn_positions[len(rollback_turn_positions) - num_turns :]
        fork_turn_positions = [position for position in fork_turn_positions if position < rollback_start_idx]
    return fork_turn_positions


def truncate_rollout_before_nth_user_message_from_start(
    items: Sequence[RolloutItem | Any],
    n_from_start: int,
) -> list[RolloutItem | Any]:
    n_from_start = _ensure_usize(n_from_start, "n_from_start")
    if n_from_start == USIZE_MAX:
        return list(items)

    user_positions = user_message_positions_in_rollout(items)
    if len(user_positions) <= n_from_start:
        return list(items)

    cut_idx = user_positions[n_from_start]
    return list(items[:cut_idx])


def truncate_rollout_to_last_n_fork_turns(
    items: Sequence[RolloutItem | Any],
    n_from_end: int,
) -> list[RolloutItem | Any]:
    n_from_end = _ensure_usize(n_from_end, "n_from_end")
    if n_from_end == 0:
        return []

    fork_turn_positions = fork_turn_positions_in_rollout(items)
    if not fork_turn_positions:
        return []
    if len(fork_turn_positions) >= n_from_end:
        keep_idx = fork_turn_positions[len(fork_turn_positions) - n_from_end]
    else:
        keep_idx = fork_turn_positions[0]
    return list(items[keep_idx:])


def is_user_turn_boundary(item: ResponseItem | Any) -> bool:
    response_item = _response_item(item)
    if response_item is None or response_item.type != "message":
        return False

    if response_item.role == "user":
        return not _is_contextual_user_message_content(response_item.content)
    if response_item.role == "assistant":
        return InterAgentCommunication.is_message_content(response_item.content)
    return False


def _is_real_user_message_boundary(item: ResponseItem) -> bool:
    return item.type == "message" and item.role == "user" and not _is_contextual_user_message_content(item.content)


def _is_trigger_turn_boundary(item: ResponseItem) -> bool:
    if item.type != "message" or item.role != "assistant":
        return False
    communication = InterAgentCommunication.from_message_content(item.content)
    return communication is not None and communication.trigger_turn


def _is_contextual_user_message_content(content: Iterable[Any]) -> bool:
    return any(is_contextual_user_fragment(item) for item in content)


def _rollout_item(item: RolloutItem | Any) -> RolloutItem:
    return item if isinstance(item, RolloutItem) else RolloutItem.from_mapping(item)


def _response_item(item: ResponseItem | Any) -> ResponseItem | None:
    if isinstance(item, ResponseItem):
        return item
    try:
        return ResponseItem.from_mapping(item)
    except (KeyError, TypeError, ValueError):
        return None


def _event_msg(item: RolloutItem) -> EventMsg | None:
    if item.type != "event_msg":
        return None
    if isinstance(item.payload, EventMsg):
        return item.payload
    try:
        return EventMsg.from_mapping(item.payload)
    except (KeyError, TypeError, ValueError):
        return None


def _thread_rolled_back_event(item: RolloutItem) -> ThreadRolledBackEvent | None:
    event = _event_msg(item)
    if event is None or event.type != "thread_rolled_back":
        return None
    if isinstance(event.payload, ThreadRolledBackEvent):
        return event.payload
    try:
        return ThreadRolledBackEvent(num_turns=int(event.payload["num_turns"]))
    except (KeyError, TypeError, ValueError):
        return None


def _saturating_num_turns(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError("num_turns must be an integer")
    if value < 0 or value > USIZE_MAX:
        return USIZE_MAX
    return value


__all__ = [
    "USIZE_MAX",
    "fork_turn_positions_in_rollout",
    "initial_history_has_prior_user_turns",
    "is_user_turn_boundary",
    "rollout_item_is_user_turn_boundary",
    "truncate_rollout_before_nth_user_message_from_start",
    "truncate_rollout_to_last_n_fork_turns",
    "user_message_positions_in_rollout",
]
