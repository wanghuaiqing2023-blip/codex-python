from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server_transport.outgoing_message import OutgoingMessage
from pycodex.app_server_transport.outgoing_message import OutgoingResponse
from pycodex.app_server_transport.outgoing_message import QueuedOutgoingMessage
from pycodex.app_server_transport.transport import ConnectionOrigin
from pycodex.app_server_transport.transport import TransportEventKind
from pycodex.app_server_transport.transport.auth import WebsocketAuthPolicy
from pycodex.app_server_transport.transport.websocket import DisconnectToken
from pycodex.app_server_transport.transport.websocket import run_websocket_connection
from pycodex.app_server_transport.transport.websocket import start_websocket_acceptor


class _MemoryWebsocket:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[object] = asyncio.Queue()
        self.sent: list[str] = []

    async def recv(self) -> object:
        value = await self.incoming.get()
        if isinstance(value, BaseException):
            raise value
        return value

    async def send(self, value: str) -> None:
        self.sent.append(value)


@pytest.mark.asyncio
async def test_connection_emits_open_message_and_close_events() -> None:
    websocket = _MemoryWebsocket()
    events: asyncio.Queue = asyncio.Queue()
    task = asyncio.create_task(run_websocket_connection(websocket, websocket, events))

    opened = await events.get()
    assert opened.kind is TransportEventKind.CONNECTION_OPENED
    assert opened.origin is ConnectionOrigin.WEB_SOCKET
    assert opened.writer is not None

    await websocket.incoming.put('{"jsonrpc":"2.0","method":"initialized"}')
    incoming = await events.get()
    assert incoming.kind is TransportEventKind.INCOMING_MESSAGE
    assert incoming.message["method"] == "initialized"

    await opened.writer.put(
        QueuedOutgoingMessage.new(
            OutgoingMessage.response(OutgoingResponse(7, {"ok": True}))
        )
    )
    await asyncio.wait_for(opened.writer.join(), timeout=1)
    assert websocket.sent == ['{"id":7,"result":{"ok":true}}']

    await websocket.incoming.put(EOFError())
    closed = await events.get()
    assert closed.kind is TransportEventKind.CONNECTION_CLOSED
    await task


@pytest.mark.asyncio
async def test_non_loopback_listener_requires_auth() -> None:
    with pytest.raises(ValueError, match="without auth"):
        await start_websocket_acceptor(
            "0.0.0.0:0",
            asyncio.Queue(),
            DisconnectToken(),
            WebsocketAuthPolicy(),
        )
