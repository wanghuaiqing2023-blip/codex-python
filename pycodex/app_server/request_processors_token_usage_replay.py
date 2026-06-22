"""Token-usage replay helpers for app-server request processors.

Ported from ``codex-app-server/src/request_processors/token_usage_replay.rs``.
The Rust module owns replay attribution for persisted token-count rollout
events and the replay notification sent when a client attaches to an existing
thread. Python keeps that contract focused here; conversation storage and
outgoing transport remain injected dependencies.
"""

from __future__ import annotations

import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from pycodex.app_server_protocol import (
    ServerNotification,
    Thread,
    ThreadHistoryBuilder,
    ThreadTokenUsage,
    ThreadTokenUsageUpdatedNotification,
    TokenUsageBreakdown,
    Turn,
)
from pycodex.protocol import TokenUsage, TokenUsageInfo

JsonValue = Any


@dataclass(frozen=True)
class TokenUsageTurnOwner:
    id: str
    position: int | None


async def send_thread_token_usage_update_to_connection(
    outgoing: Any,
    connection_id: Any,
    thread_id: Any,
    thread: Thread | Mapping[str, JsonValue],
    conversation: Any,
    token_usage_turn_id: str | None = None,
) -> None:
    """Send Rust's ``ThreadTokenUsageUpdated`` replay notification if present."""

    info = await _maybe_await(conversation.token_usage_info())
    if info is None:
        return

    token_usage = thread_token_usage_from_info(info)
    notification = ThreadTokenUsageUpdatedNotification(
        thread_id=str(thread_id),
        turn_id=token_usage_turn_id if token_usage_turn_id is not None else latest_token_usage_turn_id(thread),
        token_usage=token_usage,
    )
    await _maybe_await(
        outgoing.send_server_notification_to_connections(
            [connection_id],
            ServerNotification("ThreadTokenUsageUpdated", notification),
        )
    )


def latest_token_usage_turn_id_from_rollout_items(
    rollout_items: Sequence[JsonValue],
    turns: Sequence[Turn | Mapping[str, JsonValue]],
) -> str | None:
    """Return the turn id that owned the latest persisted token-count item.

    Rust snapshots the active turn *before* feeding the token-count item back
    into ``ThreadHistoryBuilder``. That ordering matters when the token-count
    item has no own payload but belongs to the previously loaded turn.
    """

    owner: TokenUsageTurnOwner | None = None
    builder = ThreadHistoryBuilder()
    for item in rollout_items:
        if _is_token_count_rollout_item(item):
            snapshot = builder.active_turn_snapshot()
            if snapshot is not None:
                owner = TokenUsageTurnOwner(snapshot.id, builder.active_turn_position())
        builder.handle_rollout_item(item)

    if owner is None:
        return None

    loaded_turns = tuple(_turn(turn) for turn in turns)
    if any(turn.id == owner.id for turn in loaded_turns):
        return owner.id
    if owner.position is not None and 0 <= owner.position < len(loaded_turns):
        return loaded_turns[owner.position].id
    return None


def latest_token_usage_turn_id(thread: Thread | Mapping[str, JsonValue]) -> str:
    """Mirror Rust's fallback turn selection for replay notifications."""

    loaded = _thread(thread)
    for turn in reversed(loaded.turns):
        if _turn_status_value(turn.status) in {"completed", "failed"}:
            return turn.id
    return loaded.turns[-1].id if loaded.turns else ""


def thread_token_usage_from_info(info: TokenUsageInfo | Mapping[str, JsonValue]) -> ThreadTokenUsage:
    value = _token_usage_info(info)
    return ThreadTokenUsage(
        total=_token_usage_breakdown(value.total_token_usage),
        last=_token_usage_breakdown(value.last_token_usage),
        model_context_window=value.model_context_window,
    )


def _is_token_count_rollout_item(item: JsonValue) -> bool:
    kind, payload = _rollout_parts(item)
    if kind not in {"event_msg", "eventMsg", "EventMsg", "event"}:
        return False
    event_type, _ = _event_parts(payload)
    return event_type in {"token_count", "TokenCount", "tokenCount"}


def _rollout_parts(item: JsonValue) -> tuple[str, JsonValue]:
    data = _to_mapping(item)
    if isinstance(data, Mapping):
        type_ = data.get("type") or data.get("kind") or data.get("variant")
        if type_ is not None:
            payload = data.get("payload", data.get("item", data.get("msg", {key: value for key, value in data.items() if key not in {"type", "kind", "variant"}})))
            return _str(type_), payload
    if hasattr(item, "msg"):
        return "event_msg", getattr(item, "msg")
    return "event_msg", item


def _event_parts(event: JsonValue) -> tuple[str, JsonValue]:
    data = _to_mapping(event)
    if isinstance(data, Mapping):
        type_ = data.get("type")
        payload = data.get("payload")
        if payload is None:
            payload = {key: value for key, value in data.items() if key != "type"}
        return _str(type_), payload
    kind = getattr(event, "kind", None)
    type_ = getattr(event, "type", None) or (kind() if callable(kind) else kind)
    return _str(type_), getattr(event, "payload", None)


def _token_usage_info(value: TokenUsageInfo | Mapping[str, JsonValue]) -> TokenUsageInfo:
    if isinstance(value, TokenUsageInfo):
        return value
    return TokenUsageInfo.from_mapping(value)


def _token_usage_breakdown(value: TokenUsage | Mapping[str, JsonValue]) -> TokenUsageBreakdown:
    usage = value if isinstance(value, TokenUsage) else TokenUsage.from_mapping(value)
    return TokenUsageBreakdown(
        total_tokens=usage.total_tokens,
        input_tokens=usage.input_tokens,
        cached_input_tokens=usage.cached_input_tokens,
        output_tokens=usage.output_tokens,
        reasoning_output_tokens=usage.reasoning_output_tokens,
    )


def _thread(value: Thread | Mapping[str, JsonValue]) -> Thread:
    if isinstance(value, Thread):
        return value
    return Thread.from_mapping(value)


def _turn(value: Turn | Mapping[str, JsonValue]) -> Turn:
    if isinstance(value, Turn):
        return value
    return Turn.from_mapping(value)


def _turn_status_value(value: JsonValue) -> str:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else str(raw)


def _str(value: JsonValue) -> str:
    raw = getattr(value, "value", value)
    return raw if isinstance(raw, str) else str(raw)


def _to_mapping(value: JsonValue) -> Mapping[str, JsonValue] | None:
    if isinstance(value, Mapping):
        return value
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        mapped = to_mapping()
        return mapped if isinstance(mapped, Mapping) else None
    return None


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


__all__ = [
    "TokenUsageTurnOwner",
    "latest_token_usage_turn_id",
    "latest_token_usage_turn_id_from_rollout_items",
    "send_thread_token_usage_update_to_connection",
    "thread_token_usage_from_info",
]
