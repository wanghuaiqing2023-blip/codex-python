from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server_transport.outgoing_message import QueuedOutgoingMessage
from pycodex.app_server_transport.transport import (
    TransportEventKind,
)
from pycodex.app_server_transport.transport.remote_control.client_tracker import (
    ClientTracker,
)
from pycodex.app_server_transport.transport.remote_control.protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    PongStatus,
    ServerEvent,
    StreamId,
)


def _envelope(
    message: dict,
    *,
    seq_id: int,
    stream_id: str | None = "stream-1",
) -> ClientEnvelope:
    return ClientEnvelope(
        event=ClientEvent.client_message(message),
        client_id=ClientId("client-1"),
        stream_id=None if stream_id is None else StreamId(stream_id),
        seq_id=seq_id,
    )


@pytest.mark.asyncio
async def test_initialize_opens_connection_and_forwards_followups() -> None:
    server_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    transport_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    tracker = ClientTracker(server_events, transport_events)

    await tracker.handle_message(
        _envelope({"id": 1, "method": "initialize", "params": {}}, seq_id=0)
    )
    opened = await transport_events.get()
    initialized = await transport_events.get()
    assert opened.kind is TransportEventKind.CONNECTION_OPENED
    assert initialized.kind is TransportEventKind.INCOMING_MESSAGE
    assert initialized.connection_id == opened.connection_id

    await tracker.handle_message(
        _envelope({"method": "initialized", "params": None}, seq_id=1)
    )
    followup = await transport_events.get()
    assert followup.kind is TransportEventKind.INCOMING_MESSAGE
    assert followup.connection_id == opened.connection_id

    await tracker.shutdown()


@pytest.mark.asyncio
async def test_duplicate_sequence_is_not_forwarded() -> None:
    server_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    transport_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    tracker = ClientTracker(server_events, transport_events)
    await tracker.handle_message(
        _envelope({"id": 1, "method": "initialize", "params": {}}, seq_id=0)
    )
    await transport_events.get()
    await transport_events.get()

    followup = _envelope({"method": "initialized"}, seq_id=1)
    await tracker.handle_message(followup)
    await transport_events.get()
    await tracker.handle_message(followup)
    assert transport_events.empty()
    await tracker.shutdown()


@pytest.mark.asyncio
async def test_unknown_ping_responds_without_opening_connection() -> None:
    server_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    transport_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    tracker = ClientTracker(server_events, transport_events)
    await tracker.handle_message(
        ClientEnvelope(
            event=ClientEvent.ping(),
            client_id=ClientId("unknown"),
            stream_id=StreamId("stream"),
        )
    )
    response = await server_events.get()
    assert response.event.kind is ServerEvent.Kind.PONG
    assert response.event.status is PongStatus.UNKNOWN
    assert transport_events.empty()
    await tracker.shutdown()


@pytest.mark.asyncio
async def test_outbound_writer_and_client_close_use_same_stream() -> None:
    server_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    transport_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    tracker = ClientTracker(server_events, transport_events)
    await tracker.handle_message(
        _envelope({"id": 1, "method": "initialize", "params": {}}, seq_id=0)
    )
    opened = await transport_events.get()
    await transport_events.get()
    assert opened.writer is not None

    await opened.writer.put(
        QueuedOutgoingMessage.new(
            __import__(
                "pycodex.app_server_transport.outgoing_message",
                fromlist=["OutgoingMessage"],
            ).OutgoingMessage.app_server_notification({"method": "test"})
        )
    )
    outbound = await asyncio.wait_for(server_events.get(), timeout=1)
    assert outbound.client_id == ClientId("client-1")
    assert outbound.stream_id == StreamId("stream-1")

    await tracker.handle_message(
        ClientEnvelope(
            event=ClientEvent.client_closed(),
            client_id=ClientId("client-1"),
            stream_id=StreamId("stream-1"),
        )
    )
    closed = await transport_events.get()
    assert closed.kind is TransportEventKind.CONNECTION_CLOSED
    assert closed.connection_id == opened.connection_id
    await tracker.shutdown()
