from __future__ import annotations

import asyncio
from http import HTTPStatus
from typing import Any

from pycodex.app_server_transport.outgoing_message import QueuedOutgoingMessage
from pycodex.app_server_transport.transport import CHANNEL_CAPACITY
from pycodex.app_server_transport.transport import ConnectionOrigin
from pycodex.app_server_transport.transport import TransportEvent
from pycodex.app_server_transport.transport import forward_incoming_message
from pycodex.app_server_transport.transport import next_connection_id
from pycodex.app_server_transport.transport import serialize_outgoing_message
from pycodex.app_server_transport.transport.auth import WebsocketAuthError
from pycodex.app_server_transport.transport.auth import WebsocketAuthPolicy
from pycodex.app_server_transport.transport.auth import authorize_upgrade
from pycodex.app_server_transport.transport.auth import (
    is_unauthenticated_non_loopback_listener,
)

WEBSOCKET_OUTBOUND_CHANNEL_CAPACITY = 32 * 1024


class DisconnectToken:
    def __init__(self) -> None:
        self._event = asyncio.Event()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set()

    async def cancelled(self) -> None:
        await self._event.wait()


async def start_websocket_acceptor(
    bind_address: str,
    transport_event_tx: asyncio.Queue[TransportEvent],
    shutdown_token: Any,
    auth_policy: WebsocketAuthPolicy,
) -> asyncio.Task[None]:
    host, port = _split_bind_address(bind_address)
    if is_unauthenticated_non_loopback_listener(bind_address, auth_policy):
        raise ValueError(
            "refusing to start non-loopback websocket listener "
            f"{bind_address} without auth; configure `--ws-auth capability-token` "
            "or `--ws-auth signed-bearer-token`"
        )

    from websockets.asyncio.server import serve
    from websockets.datastructures import Headers
    from websockets.http11 import Response

    async def process_request(connection: Any, request: Any) -> Any:
        if request.headers.get("Origin") is not None:
            return Response(
                HTTPStatus.FORBIDDEN,
                "Forbidden",
                Headers(),
                b"",
            )
        if request.path in {"/readyz", "/healthz"}:
            return Response(HTTPStatus.OK, "OK", Headers(), b"")
        try:
            authorize_upgrade(dict(request.headers.raw_items()), auth_policy)
        except WebsocketAuthError as exc:
            return Response(
                HTTPStatus(exc.status_code),
                exc.message,
                Headers(),
                exc.message.encode(),
            )
        return None

    async def handler(connection: Any) -> None:
        await run_websocket_connection(connection, connection, transport_event_tx)

    server = await serve(
        handler,
        host,
        port,
        process_request=process_request,
    )

    async def run() -> None:
        try:
            await _wait_cancelled(shutdown_token)
        finally:
            server.close()
            await server.wait_closed()

    return asyncio.create_task(run(), name="app-server-websocket-acceptor")


async def run_websocket_connection(
    websocket_writer: Any,
    websocket_reader: Any,
    transport_event_tx: asyncio.Queue[TransportEvent],
) -> None:
    connection_id = next_connection_id()
    writer: asyncio.Queue[QueuedOutgoingMessage] = asyncio.Queue(
        WEBSOCKET_OUTBOUND_CHANNEL_CAPACITY
    )
    disconnect_token = DisconnectToken()
    await transport_event_tx.put(
        TransportEvent.connection_opened(
            connection_id,
            ConnectionOrigin.WEB_SOCKET,
            writer,
            disconnect_token,
        )
    )
    outbound_task = asyncio.create_task(
        _run_websocket_outbound_loop(
            websocket_writer,
            writer,
            disconnect_token,
        )
    )
    inbound_task = asyncio.create_task(
        _run_websocket_inbound_loop(
            websocket_reader,
            transport_event_tx,
            writer,
            connection_id,
            disconnect_token,
        )
    )
    try:
        done, pending = await asyncio.wait(
            {outbound_task, inbound_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        disconnect_token.cancel()
        for task in pending:
            task.cancel()
        await asyncio.gather(*done, *pending, return_exceptions=True)
    finally:
        await transport_event_tx.put(TransportEvent.connection_closed(connection_id))


async def _run_websocket_outbound_loop(
    websocket_writer: Any,
    writer: asyncio.Queue[QueuedOutgoingMessage],
    disconnect_token: DisconnectToken,
) -> None:
    while not disconnect_token.is_cancelled():
        queued = await writer.get()
        try:
            payload = serialize_outgoing_message(queued.message)
            if payload is None:
                continue
            await websocket_writer.send(payload)
            completion = queued.write_complete_tx
            if completion is not None and not completion.done():
                completion.set_result(None)
        finally:
            writer.task_done()


async def _run_websocket_inbound_loop(
    websocket_reader: Any,
    transport_event_tx: asyncio.Queue[TransportEvent],
    writer: asyncio.Queue[QueuedOutgoingMessage],
    connection_id: Any,
    disconnect_token: DisconnectToken,
) -> None:
    while not disconnect_token.is_cancelled():
        try:
            message = await websocket_reader.recv()
        except (EOFError, asyncio.CancelledError):
            break
        except Exception:
            break
        if message is None:
            break
        if isinstance(message, str):
            if not await forward_incoming_message(
                transport_event_tx,
                writer,
                connection_id,
                message,
            ):
                break


def _split_bind_address(bind_address: str) -> tuple[str, int]:
    host, separator, port = bind_address.rpartition(":")
    if not separator:
        raise ValueError(f"invalid websocket bind address: {bind_address}")
    return host.strip("[]"), int(port)


async def _wait_cancelled(token: Any) -> None:
    for name in ("cancelled", "wait"):
        method = getattr(token, name, None)
        if callable(method):
            result = method()
            if hasattr(result, "__await__"):
                await result
                return
    while not bool(getattr(token, "cancelled", False)):
        await asyncio.sleep(0.05)


__all__ = [
    "DisconnectToken",
    "WEBSOCKET_OUTBOUND_CHANNEL_CAPACITY",
    "run_websocket_connection",
    "start_websocket_acceptor",
]
