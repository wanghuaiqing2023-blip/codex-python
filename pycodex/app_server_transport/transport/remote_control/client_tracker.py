from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from pycodex.app_server_transport.outgoing_message import (
    ConnectionId,
    QueuedOutgoingMessage,
)
from pycodex.app_server_transport.transport import (
    CHANNEL_CAPACITY,
    ConnectionOrigin,
    TransportEvent,
    next_connection_id,
)

from . import QueuedServerEnvelope
from .protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    PongStatus,
    ServerEvent,
    StreamId,
)

REMOTE_CONTROL_CLIENT_IDLE_TIMEOUT_SECONDS = 10 * 60
REMOTE_CONTROL_IDLE_SWEEP_INTERVAL_SECONDS = 30
REMOTE_CONTROL_TRANSPORT_EVENT_SEND_TIMEOUT_SECONDS = 5


class Stopped(RuntimeError):
    pass


class _CancellationToken:
    def __init__(self, parent: Any | None = None) -> None:
        self._event = asyncio.Event()
        self._parent = parent

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set() or _is_cancelled(self._parent)

    async def cancelled(self) -> None:
        if self.is_cancelled():
            return
        own = asyncio.create_task(self._event.wait())
        parent = asyncio.create_task(_wait_cancelled(self._parent))
        done, pending = await asyncio.wait(
            {own, parent},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            task.result()


@dataclass
class _ClientState:
    connection_id: ConnectionId
    disconnect_token: _CancellationToken
    last_activity_at: float
    last_inbound_seq_id: int | None
    status_tx: asyncio.Queue[PongStatus]


class ClientTracker:
    def __init__(
        self,
        server_event_tx: asyncio.Queue[QueuedServerEnvelope],
        transport_event_tx: asyncio.Queue[TransportEvent],
        shutdown_token: Any | None = None,
    ) -> None:
        self._clients: dict[tuple[ClientId, StreamId], _ClientState] = {}
        self._legacy_stream_ids: dict[ClientId, StreamId] = {}
        self._tasks: set[asyncio.Task[tuple[ClientId, StreamId]]] = set()
        self._completed: asyncio.Queue[tuple[ClientId, StreamId]] = asyncio.Queue()
        self._server_event_tx = server_event_tx
        self._transport_event_tx = transport_event_tx
        self._shutdown_token = _CancellationToken(shutdown_token)

    async def bookkeep_join_set(self) -> tuple[ClientId, StreamId] | None:
        completed_task = asyncio.create_task(self._completed.get())
        shutdown_task = asyncio.create_task(self._shutdown_token.cancelled())
        done, pending = await asyncio.wait(
            {completed_task, shutdown_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if shutdown_task in done:
            return None
        return completed_task.result()

    async def shutdown(self) -> None:
        self._shutdown_token.cancel()
        for client_key in list(self._clients):
            await self.close_client(client_key)
        if self._tasks:
            await asyncio.gather(*tuple(self._tasks), return_exceptions=True)

    async def handle_message(self, client_envelope: ClientEnvelope) -> None:
        client_id = client_envelope.client_id
        event = client_envelope.event
        stream_id = client_envelope.stream_id
        seq_id = client_envelope.seq_id
        legacy_stream = stream_id is None
        initialize = (
            event.kind is ClientEvent.Kind.CLIENT_MESSAGE
            and _remote_control_message_starts_connection(event.message)
        )
        if stream_id is None and initialize:
            stream_id = self._legacy_stream_ids.pop(
                client_id,
                StreamId.new_random(),
            )
        elif stream_id is None:
            stream_id = self._legacy_stream_ids.get(client_id)
            if stream_id is None:
                stream_id = (
                    StreamId.new_random()
                    if event.kind is ClientEvent.Kind.PING
                    else StreamId("")
                )
        if not stream_id.value:
            return

        client_key = (client_id, stream_id)
        if event.kind is ClientEvent.Kind.CLIENT_MESSAGE:
            state = self._clients.get(client_key)
            if (
                seq_id is not None
                and state is not None
                and state.last_inbound_seq_id is not None
                and state.last_inbound_seq_id >= seq_id
                and not initialize
            ):
                return
            if initialize and state is not None:
                await self.close_client(client_key)
                state = None

            if state is not None:
                state.last_activity_at = time.monotonic()
                await self._send_transport_event(
                    TransportEvent.incoming_message(
                        state.connection_id,
                        event.message,
                    )
                )
                self._record_inbound_delivery(client_key, seq_id)
                return
            if not initialize:
                return

            connection_id = next_connection_id()
            writer: asyncio.Queue[QueuedOutgoingMessage] = asyncio.Queue(
                maxsize=CHANNEL_CAPACITY
            )
            disconnect_token = _CancellationToken(self._shutdown_token)
            await self._send_transport_event(
                TransportEvent.connection_opened(
                    connection_id,
                    ConnectionOrigin.REMOTE_CONTROL,
                    writer,
                    disconnect_token,
                )
            )
            status_tx: asyncio.Queue[PongStatus] = asyncio.Queue(maxsize=1)
            task = asyncio.create_task(
                self._run_client_outbound(
                    client_id,
                    stream_id,
                    writer,
                    status_tx,
                    disconnect_token,
                )
            )
            self._tasks.add(task)
            task.add_done_callback(self._client_task_done)
            self._clients[client_key] = _ClientState(
                connection_id=connection_id,
                disconnect_token=disconnect_token,
                last_activity_at=time.monotonic(),
                last_inbound_seq_id=None,
                status_tx=status_tx,
            )
            if legacy_stream:
                self._legacy_stream_ids[client_id] = stream_id
            try:
                await self._send_transport_event(
                    TransportEvent.incoming_message(connection_id, event.message)
                )
            except Stopped:
                state = self._remove_client(client_key)
                if state is not None:
                    state.disconnect_token.cancel()
                    asyncio.create_task(
                        self._transport_event_tx.put(
                            TransportEvent.connection_closed(state.connection_id)
                        )
                    )
                raise
            if not legacy_stream:
                self._record_inbound_delivery(client_key, seq_id)
            return

        if event.kind in {
            ClientEvent.Kind.CLIENT_MESSAGE_CHUNK,
            ClientEvent.Kind.ACK,
        }:
            return
        if event.kind is ClientEvent.Kind.PING:
            state = self._clients.get(client_key)
            if state is not None:
                state.last_activity_at = time.monotonic()
                _replace_queue_value(state.status_tx, PongStatus.ACTIVE)
                return
            await self._server_event_tx.put(
                QueuedServerEnvelope(
                    event=ServerEvent.pong(PongStatus.UNKNOWN),
                    client_id=client_id,
                    stream_id=stream_id,
                )
            )
            return
        await self.close_client(client_key)

    async def close_expired_clients(self) -> list[tuple[ClientId, StreamId]]:
        now = time.monotonic()
        expired = [
            key
            for key, state in self._clients.items()
            if now - state.last_activity_at
            >= REMOTE_CONTROL_CLIENT_IDLE_TIMEOUT_SECONDS
        ]
        for client_key in expired:
            await self.close_client(client_key)
        return expired

    async def close_client(
        self,
        client_key: tuple[ClientId, StreamId],
    ) -> None:
        state = self._remove_client(client_key)
        if state is None:
            return
        state.disconnect_token.cancel()
        await self._transport_event_tx.put(
            TransportEvent.connection_closed(state.connection_id)
        )

    def _remove_client(
        self,
        client_key: tuple[ClientId, StreamId],
    ) -> _ClientState | None:
        state = self._clients.pop(client_key, None)
        if self._legacy_stream_ids.get(client_key[0]) == client_key[1]:
            self._legacy_stream_ids.pop(client_key[0], None)
        return state

    async def _send_transport_event(self, event: TransportEvent) -> None:
        try:
            await asyncio.wait_for(
                self._transport_event_tx.put(event),
                timeout=REMOTE_CONTROL_TRANSPORT_EVENT_SEND_TIMEOUT_SECONDS,
            )
        except (TimeoutError, asyncio.CancelledError) as exc:
            raise Stopped() from exc

    def _record_inbound_delivery(
        self,
        client_key: tuple[ClientId, StreamId],
        seq_id: int | None,
    ) -> None:
        if seq_id is not None and (state := self._clients.get(client_key)) is not None:
            state.last_inbound_seq_id = seq_id

    async def _run_client_outbound(
        self,
        client_id: ClientId,
        stream_id: StreamId,
        writer_rx: asyncio.Queue[QueuedOutgoingMessage],
        status_rx: asyncio.Queue[PongStatus],
        disconnect_token: _CancellationToken,
    ) -> tuple[ClientId, StreamId]:
        while not disconnect_token.is_cancelled():
            writer_task = asyncio.create_task(writer_rx.get())
            status_task = asyncio.create_task(status_rx.get())
            cancel_task = asyncio.create_task(disconnect_token.cancelled())
            done, pending = await asyncio.wait(
                {writer_task, status_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if cancel_task in done:
                break
            if writer_task in done:
                queued = writer_task.result()
                event = ServerEvent.server_message(queued.message)
                write_complete_tx = queued.write_complete_tx
            else:
                event = ServerEvent.pong(status_task.result())
                write_complete_tx = None
            put_task = asyncio.create_task(
                self._server_event_tx.put(
                    QueuedServerEnvelope(
                        event=event,
                        client_id=client_id,
                        stream_id=stream_id,
                        write_complete_tx=write_complete_tx,
                    )
                )
            )
            cancel_task = asyncio.create_task(disconnect_token.cancelled())
            done, pending = await asyncio.wait(
                {put_task, cancel_task},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            if cancel_task in done:
                break
        return client_id, stream_id

    def _client_task_done(
        self,
        task: asyncio.Task[tuple[ClientId, StreamId]],
    ) -> None:
        self._tasks.discard(task)
        if task.cancelled():
            return
        try:
            client_key = task.result()
        except Exception:
            return
        self._completed.put_nowait(client_key)


def _replace_queue_value(queue: asyncio.Queue[PongStatus], value: PongStatus) -> None:
    if queue.full():
        try:
            queue.get_nowait()
        except asyncio.QueueEmpty:
            pass
    queue.put_nowait(value)


def _remote_control_message_starts_connection(message: Any) -> bool:
    if isinstance(message, dict):
        return message.get("method") == "initialize" and "id" in message
    return (
        getattr(message, "method", None) == "initialize"
        and getattr(message, "id", None) is not None
    )


def _is_cancelled(token: Any | None) -> bool:
    if token is None:
        return False
    method = getattr(token, "is_cancelled", None)
    if callable(method):
        return bool(method())
    method = getattr(token, "cancelled", None)
    if callable(method):
        try:
            value = method()
        except TypeError:
            return False
        if isinstance(value, bool):
            return value
        close = getattr(value, "close", None)
        if callable(close):
            close()
    return False


async def _wait_cancelled(token: Any | None) -> None:
    if token is None:
        await asyncio.Future()
    method = getattr(token, "cancelled", None)
    if callable(method):
        result = method()
        if hasattr(result, "__await__"):
            await result
            return
        if result:
            return
    method = getattr(token, "wait_cancelled", None)
    if callable(method):
        await method()
        return
    while not _is_cancelled(token):
        await asyncio.sleep(0.05)


__all__ = [
    "ClientEvent",
    "ClientId",
    "ClientTracker",
    "REMOTE_CONTROL_IDLE_SWEEP_INTERVAL_SECONDS",
    "Stopped",
]
