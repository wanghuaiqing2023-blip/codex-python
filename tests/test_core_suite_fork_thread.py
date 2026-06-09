"""Rust integration parity for ``core/tests/suite/fork_thread.rs``.

Rust drives live Codex threads and then checks the forked rollout files. Python
keeps the same behavior at the deterministic ThreadManager/history boundary:
truncate-before-nth-user-message can be applied repeatedly, and
``fork_thread_from_history`` accepts a resumed history whose source rollout path
is absent.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from pycodex.core.thread_manager import (
    ForkSnapshot,
    NewThread,
    StartThreadOptions,
    ThreadManager,
    fork_history_from_snapshot,
)
from pycodex.protocol import EventMsg, InitialHistory, ResumedHistory, RolloutItem, ThreadId
from pycodex.protocol.models import ContentItem, ResponseItem


def user_msg(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def assistant_msg(text: str) -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def response_item(item: ResponseItem) -> RolloutItem:
    return RolloutItem.response_item(item)


def task_started(turn_id: str) -> RolloutItem:
    return RolloutItem.event_msg(
        EventMsg.with_payload("task_started", {"turn_id": turn_id, "model_context_window": 128000})
    )


def task_complete(turn_id: str) -> RolloutItem:
    return RolloutItem.event_msg(EventMsg.with_payload("task_complete", {"turn_id": turn_id, "last_agent_message": None}))


def user_turn(turn_id: str, text: str) -> tuple[RolloutItem, ...]:
    return (
        task_started(turn_id),
        RolloutItem.event_msg(EventMsg.with_payload("user_message", {"message": text})),
        response_item(user_msg(text)),
        response_item(assistant_msg(f"{text} reply")),
        task_complete(turn_id),
    )


def rollout_user_texts(items: tuple[RolloutItem, ...]) -> list[str]:
    texts: list[str] = []
    for item in items:
        if item.type != "response_item":
            continue
        payload = item.payload
        response = payload if isinstance(payload, ResponseItem) else ResponseItem.from_mapping(payload)
        if response.type == "message" and response.role == "user" and response.content:
            texts.append(response.content[0].text or "")
    return texts


def test_fork_thread_twice_drops_to_first_message() -> None:
    # Rust test: fork_thread_twice_drops_to_first_message.
    base_items = (
        *user_turn("turn-1", "first"),
        *user_turn("turn-2", "second"),
        *user_turn("turn-3", "third"),
    )
    base_history = InitialHistory.forked(base_items)

    fork1 = fork_history_from_snapshot(ForkSnapshot.truncate_before_nth_user_message(1), base_history)
    assert fork1.type == "Forked"
    fork1_items = fork1.items
    expected_after_first = base_items[: base_items.index(response_item(user_msg("second")))]

    fork2 = fork_history_from_snapshot(ForkSnapshot.truncate_before_nth_user_message(0), fork1)
    assert fork2.type == "Forked"
    expected_after_second = fork1_items[: fork1_items.index(response_item(user_msg("first")))]

    assert fork1_items == expected_after_first
    assert rollout_user_texts(fork1_items) == ["first"]
    assert fork2.items == expected_after_second
    assert rollout_user_texts(fork2.items) == []


@pytest.mark.asyncio
async def test_fork_thread_from_history_does_not_require_source_rollout_path() -> None:
    # Rust test: fork_thread_from_history_does_not_require_source_rollout_path.
    source_thread_id = ThreadId.from_string(str(uuid.uuid4()))
    source_items = user_turn("turn-1", "fork me from stored history")
    captured_options: list[StartThreadOptions] = []

    async def factory(options: StartThreadOptions) -> NewThread:
        captured_options.append(options)
        return NewThread(thread_id="forked-thread", thread=SimpleNamespace(), session_configured={"ok": True})

    manager = ThreadManager(thread_factory=factory)
    history = InitialHistory.resumed_history(
        ResumedHistory(
            conversation_id=source_thread_id,
            history=source_items,
            rollout_path=None,
        )
    )

    new_thread = await manager.fork_thread_from_history(
        ForkSnapshot.interrupted(),
        SimpleNamespace(cwd=None),
        history,
        thread_source=None,
        persist_extended_history=False,
        parent_trace=None,
    )

    assert new_thread.thread_id == "forked-thread"
    assert manager.get_thread_metadata("forked-thread")["forked_from_thread_id"] == str(source_thread_id)
    assert len(captured_options) == 1
    forked_history = captured_options[0].initial_history
    assert forked_history.type == "Forked"
    assert forked_history.items[: len(source_items)] == source_items
    assert rollout_user_texts(forked_history.items) == ["fork me from stored history"]
