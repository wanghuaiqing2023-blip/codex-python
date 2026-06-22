from __future__ import annotations

import asyncio
from dataclasses import replace

from pycodex.app_server.request_processors_token_usage_replay import (
    latest_token_usage_turn_id,
    latest_token_usage_turn_id_from_rollout_items,
    send_thread_token_usage_update_to_connection,
    thread_token_usage_from_info,
)
from pycodex.app_server_protocol import Thread, Turn
from pycodex.app_server_protocol.thread_history import build_turns_from_rollout_items
from pycodex.protocol import TokenUsage, TokenUsageInfo


def token_usage_history():
    # Rust source: codex-app-server/src/request_processors/token_usage_replay.rs
    # test helper token_usage_history().
    return [
        {"type": "event_msg", "payload": {"type": "user_message", "message": "first turn"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "first answer"}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": None, "rate_limits": None}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "second turn"}},
    ]


def test_replay_attribution_uses_already_loaded_history() -> None:
    turns = build_turns_from_rollout_items(token_usage_history())

    owner_id = latest_token_usage_turn_id_from_rollout_items(token_usage_history(), turns)

    assert owner_id == turns[0].id


def test_replay_attribution_falls_back_to_rebuilt_turn_position() -> None:
    turns = build_turns_from_rollout_items(token_usage_history())
    rebuilt = [replace(turns[0], id="rebuilt-turn-id"), *turns[1:]]

    owner_id = latest_token_usage_turn_id_from_rollout_items(token_usage_history(), rebuilt)

    assert owner_id == "rebuilt-turn-id"


def test_replay_attribution_returns_none_without_token_count_owner() -> None:
    turns = build_turns_from_rollout_items(token_usage_history())

    owner_id = latest_token_usage_turn_id_from_rollout_items(token_usage_history()[:2], turns)

    assert owner_id is None


def test_latest_token_usage_turn_id_prefers_last_terminal_turn() -> None:
    thread = thread_with_turns(
        Turn(id="started", items=(), status="running"),
        Turn(id="failed", items=(), status="failed"),
        Turn(id="in-progress", items=(), status="running"),
    )

    assert latest_token_usage_turn_id(thread) == "failed"


def test_latest_token_usage_turn_id_falls_back_to_last_or_empty() -> None:
    assert latest_token_usage_turn_id(thread_with_turns(Turn(id="running", items=(), status="running"))) == "running"
    assert latest_token_usage_turn_id(thread_with_turns()) == ""


def test_thread_token_usage_from_info_maps_core_usage_fields() -> None:
    info = TokenUsageInfo(
        total_token_usage=TokenUsage(
            input_tokens=60,
            cached_input_tokens=10,
            output_tokens=30,
            reasoning_output_tokens=5,
            total_tokens=100,
        ),
        last_token_usage=TokenUsage(
            input_tokens=12,
            cached_input_tokens=2,
            output_tokens=8,
            reasoning_output_tokens=1,
            total_tokens=20,
        ),
        model_context_window=200000,
    )

    usage = thread_token_usage_from_info(info)

    assert usage.total.total_tokens == 100
    assert usage.total.input_tokens == 60
    assert usage.total.cached_input_tokens == 10
    assert usage.total.output_tokens == 30
    assert usage.total.reasoning_output_tokens == 5
    assert usage.last.total_tokens == 20
    assert usage.last.input_tokens == 12
    assert usage.last.cached_input_tokens == 2
    assert usage.last.output_tokens == 8
    assert usage.last.reasoning_output_tokens == 1
    assert usage.model_context_window == 200000


def test_send_thread_token_usage_update_returns_early_without_info() -> None:
    outgoing = FakeOutgoing()
    conversation = FakeConversation(None)

    asyncio.run(send_thread_token_usage_update_to_connection(outgoing, "conn", "thread-1", thread_with_turns(), conversation))

    assert outgoing.sent == []


def test_send_thread_token_usage_update_sends_to_connection_with_turn_id() -> None:
    outgoing = FakeOutgoing()
    conversation = FakeConversation(
        TokenUsageInfo(
            total_token_usage=TokenUsage(input_tokens=1, total_tokens=2),
            last_token_usage=TokenUsage(output_tokens=1, total_tokens=1),
            model_context_window=None,
        )
    )
    thread = thread_with_turns(Turn(id="fallback-turn", items=(), status="completed"))

    asyncio.run(send_thread_token_usage_update_to_connection(outgoing, "conn", "thread-1", thread, conversation, "provided-turn"))

    assert len(outgoing.sent) == 1
    connections, notification = outgoing.sent[0]
    assert connections == ["conn"]
    assert notification.type == "ThreadTokenUsageUpdated"
    assert notification.payload.thread_id == "thread-1"
    assert notification.payload.turn_id == "provided-turn"
    assert notification.payload.token_usage.total.total_tokens == 2
    assert notification.payload.token_usage.last.total_tokens == 1


class FakeConversation:
    def __init__(self, info):
        self.info = info

    async def token_usage_info(self):
        return self.info


class FakeOutgoing:
    def __init__(self) -> None:
        self.sent = []

    async def send_server_notification_to_connections(self, connections, notification) -> None:
        self.sent.append((list(connections), notification))


def thread_with_turns(*turns: Turn) -> Thread:
    return Thread(
        id="thread-1",
        session_id="session-1",
        forked_from_id=None,
        preview="preview",
        ephemeral=False,
        model_provider="openai",
        created_at=1,
        updated_at=2,
        status={"type": "idle"},
        path=None,
        cwd=".",
        cli_version="0.0.0",
        turns=turns,
    )
