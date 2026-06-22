"""Parity tests for Rust ``app-server/src/thread_state.rs``."""

from __future__ import annotations

import asyncio

from pycodex.app_server.outgoing_message import ConnectionRequestId
from pycodex.app_server.thread_state import (
    CancellationSender,
    ConnectionCapabilities,
    ThreadState,
    ThreadStateManager,
    resolve_server_request_on_thread_listener,
)
from pycodex.app_server_protocol import RequestId
from pycodex.protocol import EventMsg, TurnCompleteEvent, TurnStartedEvent


def test_note_thread_settings_reports_only_effective_changes() -> None:
    # Rust test: note_thread_settings_reports_only_effective_changes.
    state = ThreadState()
    initial = {"cwd": "/tmp", "model": "mock-model"}
    updated = {"cwd": "/tmp", "model": "mock-model-2"}

    results = [
        state.note_thread_settings(initial.copy()),
        state.note_thread_settings(initial.copy()),
        state.note_thread_settings(updated.copy()),
        state.note_thread_settings(updated.copy()),
    ]

    assert results == [True, False, True, False]


def test_set_listener_replaces_previous_cancel_and_increments_generation() -> None:
    # Rust module: ThreadState::set_listener cancels any previous listener,
    # installs a new command channel, and wraps listener_generation.
    state = ThreadState()
    first_cancel = CancellationSender()
    second_cancel = CancellationSender()
    conversation = object()

    first_sink, first_generation = state.set_listener(first_cancel, conversation, "watch-1", {"model": "a"})
    second_sink, second_generation = state.set_listener(second_cancel, conversation, "watch-2", {"model": "b"})

    assert first_generation == 1
    assert second_generation == 2
    assert first_cancel.canceled is True
    assert second_cancel.canceled is False
    assert state.listener_command_sender() is second_sink
    assert first_sink is not second_sink
    assert state.listener_matches(conversation) is True


def test_clear_listener_cancels_sender_and_resets_history() -> None:
    # Rust module: ThreadState::clear_listener cancels listener work and drops
    # listener state.
    state = ThreadState()
    cancel = CancellationSender()
    sink, _generation = state.set_listener(cancel, object(), "watch", {"model": "a"})

    state.clear_listener()

    assert cancel.canceled is True
    assert sink.closed is True
    assert state.cancel_tx is None
    assert state.listener_command_sender() is None
    assert state.listener_thread is None
    assert state.watch_registration is None


def test_track_current_turn_event_updates_summary_and_terminal_turn() -> None:
    # Rust module: ThreadState::track_current_turn_event records TurnStarted
    # started_at and resets current turn history after a terminal event.
    state = ThreadState()

    state.track_current_turn_event(
        "turn-1",
        EventMsg.with_payload("turn_started", TurnStartedEvent("turn-1", None, started_at=123)),
    )
    assert state.turn_summary.started_at == 123
    assert state.active_turn_snapshot() is not None

    state.track_current_turn_event(
        "turn-1",
        EventMsg.with_payload("task_complete", TurnCompleteEvent("turn-1", None, completed_at=456)),
    )
    assert state.last_terminal_turn_id == "turn-1"
    assert state.current_turn_history.has_active_turn() is False


def test_resolve_server_request_on_thread_listener_queues_ordered_command() -> None:
    # Rust helper: resolve_server_request_on_thread_listener queues the
    # ResolveServerRequest command through the listener channel and awaits
    # completion.
    state = ThreadState()
    sink, _generation = state.set_listener(CancellationSender(), object(), "watch", {"model": "a"})

    asyncio.run(resolve_server_request_on_thread_listener(state, RequestId.from_value("req-1")))

    assert len(sink.commands) == 1
    assert sink.commands[0].kind == "ResolveServerRequest"
    assert sink.commands[0].request_id == RequestId.from_value("req-1")


def test_thread_state_manager_subscribe_unsubscribe_and_remove_connection() -> None:
    # Rust module: ThreadStateManager maintains bidirectional
    # connection/thread subscription maps and has-connections watcher state.
    manager = ThreadStateManager.new()
    asyncio.run(manager.connection_initialized(1, ConnectionCapabilities()))
    asyncio.run(manager.connection_initialized(2, ConnectionCapabilities()))

    state = asyncio.run(manager.try_ensure_connection_subscribed("thread-a", 1, experimental_raw_events=True))
    assert state is not None
    assert state.experimental_raw_events is True
    assert asyncio.run(manager.try_add_connection_to_thread("thread-a", 2)) is True
    assert sorted(asyncio.run(manager.subscribed_connection_ids("thread-a"))) == [1, 2]
    watcher = asyncio.run(manager.subscribe_to_has_connections("thread-a"))
    assert watcher is not None
    assert watcher.current is True

    assert asyncio.run(manager.unsubscribe_connection_from_thread("thread-a", 1)) is True
    assert asyncio.run(manager.unsubscribe_connection_from_thread("thread-a", 1)) is False
    assert asyncio.run(manager.remove_connection(2)) == ["thread-a"]
    assert watcher.current is False


def test_thread_state_manager_attestation_chooses_lowest_capable_connection() -> None:
    # Rust module: first_attestation_capable_connection_for_thread returns the
    # minimum connection id among subscribed attestation-capable connections.
    manager = ThreadStateManager.new()
    asyncio.run(manager.connection_initialized(3, ConnectionCapabilities(request_attestation=True)))
    asyncio.run(manager.connection_initialized(1, ConnectionCapabilities(request_attestation=True)))
    asyncio.run(manager.connection_initialized(2, ConnectionCapabilities(request_attestation=False)))
    asyncio.run(manager.try_add_connection_to_thread("thread-a", 3))
    asyncio.run(manager.try_add_connection_to_thread("thread-a", 1))
    asyncio.run(manager.try_add_connection_to_thread("thread-a", 2))

    assert asyncio.run(manager.first_attestation_capable_connection_for_thread("thread-a")) == 1


def test_remove_thread_state_clears_listener_and_connection_indexes() -> None:
    # Rust module: remove_thread_state drops thread entry, removes reverse
    # connection indexes, and clears listener state.
    manager = ThreadStateManager.new()
    asyncio.run(manager.connection_initialized(1, ConnectionCapabilities()))
    state = asyncio.run(manager.try_ensure_connection_subscribed("thread-a", 1, experimental_raw_events=False))
    assert state is not None
    cancel = CancellationSender()
    state.set_listener(cancel, object(), "watch", {"model": "a"})

    asyncio.run(manager.remove_thread_state("thread-a"))

    assert cancel.canceled is True
    assert asyncio.run(manager.has_subscribers("thread-a")) is False
    assert manager.thread_ids_by_connection == {}


def test_pending_interrupt_and_rollback_defaults_match_rust_shape() -> None:
    # Rust struct: ThreadState keeps pending interrupt queue and one pending
    # rollback request id.
    state = ThreadState()
    request_id = ConnectionRequestId(connection_id=7, request_id=42)

    state.pending_interrupts.append(request_id)
    state.pending_rollbacks = request_id

    assert state.pending_interrupts == [request_id]
    assert state.pending_rollbacks == request_id
