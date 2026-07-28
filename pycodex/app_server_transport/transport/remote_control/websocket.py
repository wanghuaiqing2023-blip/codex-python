from __future__ import annotations

import asyncio
import base64
import json
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping

from pycodex.app_server_protocol import RemoteControlConnectionStatus
from pycodex.app_server_transport.transport import CHANNEL_CAPACITY, TransportEvent

from . import QueuedServerEnvelope, RemoteControlHandle
from .client_tracker import (
    ClientTracker,
    REMOTE_CONTROL_IDLE_SWEEP_INTERVAL_SECONDS,
)
from .enroll import (
    REMOTE_CONTROL_ACCOUNT_ID_HEADER,
    REMOTE_CONTROL_INSTALLATION_ID_HEADER,
    RemoteControlConnectionAuth,
    RemoteControlEnrollment,
    enroll_remote_control_server,
    load_persisted_remote_control_enrollment,
    update_persisted_remote_control_enrollment,
)
from .protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    RemoteControlTarget,
    ServerEnvelope,
    StreamId,
)
from .segment import (
    ClientSegmentObservation,
    ClientSegmentReassembler,
    REMOTE_CONTROL_SEGMENT_MAX_BYTES,
    split_server_envelope_for_transport,
)

REMOTE_CONTROL_PROTOCOL_VERSION = "3"
REMOTE_CONTROL_SUBSCRIBE_CURSOR_HEADER = "x-codex-subscribe-cursor"
REMOTE_CONTROL_WEBSOCKET_PING_INTERVAL_SECONDS = 10.0
REMOTE_CONTROL_WEBSOCKET_PONG_TIMEOUT_SECONDS = 60.0
REMOTE_CONTROL_ACCOUNT_ID_RETRY_INTERVAL_SECONDS = 1.0
REMOTE_CONTROL_RECONNECT_BACKOFF_CAP_SECONDS = 30.0
REMOTE_CONTROL_WEBSOCKET_CONNECT_TIMEOUT_SECONDS = 30.0
REMOTE_CONTROL_CONNECTION_SHUTDOWN_TIMEOUT_SECONDS = 5.0


class BoundedOutboundBuffer:
    def __init__(self) -> None:
        self._buffer_by_stream: dict[
            tuple[ClientId, StreamId],
            deque[ServerEnvelope],
        ] = defaultdict(deque)
        self.used = 0

    def insert(self, server_envelope: ServerEnvelope) -> None:
        self._buffer_by_stream[
            (server_envelope.client_id, server_envelope.stream_id)
        ].append(server_envelope)
        self.used += 1

    def ack(
        self,
        client_id: ClientId,
        stream_id: StreamId,
        acked_seq_id: int,
        acked_segment_id: int | None,
    ) -> None:
        key = (client_id, stream_id)
        buffer = self._buffer_by_stream.get(key)
        if buffer is None:
            return
        ack_segment = (2**63 - 1) if acked_segment_id is None else acked_segment_id
        retained: deque[ServerEnvelope] = deque()
        for envelope in buffer:
            segment_id = envelope.event.wire_segment_id()
            cursor = (envelope.seq_id, 0 if segment_id is None else segment_id)
            if cursor <= (acked_seq_id, ack_segment):
                self.used -= 1
            else:
                retained.append(envelope)
        if retained:
            self._buffer_by_stream[key] = retained
        else:
            self._buffer_by_stream.pop(key, None)

    def server_envelopes(self) -> Iterable[ServerEnvelope]:
        for buffer in self._buffer_by_stream.values():
            yield from buffer


@dataclass
class WebsocketState:
    outbound_buffer: BoundedOutboundBuffer = field(default_factory=BoundedOutboundBuffer)
    subscribe_cursor: str | None = None
    next_seq_id_by_stream: dict[tuple[ClientId, StreamId], int] = field(
        default_factory=dict
    )
    last_completed_client_chunk_seq_id_by_stream: dict[
        tuple[ClientId, StreamId | None],
        int,
    ] = field(default_factory=dict)
    client_segment_reassembler: ClientSegmentReassembler = field(
        default_factory=ClientSegmentReassembler
    )

    def observe_client_message(
        self,
        client_envelope: ClientEnvelope,
        wire_size_bytes: int,
    ) -> ClientSegmentObservation:
        key = self.client_message_key(client_envelope)
        if key is not None:
            stream_key, seq_id = key
            if self.last_completed_client_chunk_seq_id_by_stream.get(
                stream_key,
                -1,
            ) >= seq_id:
                return ClientSegmentObservation.dropped()
            if (
                client_envelope.stream_id is not None
                and client_envelope.event.segment_id is not None
                and self.client_segment_reassembler.should_ignore_chunk(
                    client_envelope.client_id,
                    client_envelope.stream_id,
                    seq_id,
                    client_envelope.event.segment_id,
                )
            ):
                return ClientSegmentObservation.dropped()
            if wire_size_bytes > REMOTE_CONTROL_SEGMENT_MAX_BYTES:
                if client_envelope.stream_id is not None:
                    self.client_segment_reassembler.invalidate_stream(
                        client_envelope.client_id,
                        client_envelope.stream_id,
                    )
                return ClientSegmentObservation.dropped()
        return self.client_segment_reassembler.observe(client_envelope)

    def record_client_message_delivery(
        self,
        client_envelope: ClientEnvelope,
        client_message_key: tuple[tuple[ClientId, StreamId | None], int] | None,
    ) -> None:
        if client_envelope.cursor is not None:
            self.subscribe_cursor = client_envelope.cursor
        if client_message_key is not None:
            key, seq_id = client_message_key
            self.last_completed_client_chunk_seq_id_by_stream[key] = seq_id
        if (
            client_envelope.event.kind is ClientEvent.Kind.ACK
            and client_envelope.seq_id is not None
            and client_envelope.stream_id is not None
        ):
            self.outbound_buffer.ack(
                client_envelope.client_id,
                client_envelope.stream_id,
                client_envelope.seq_id,
                client_envelope.event.segment_id,
            )

    def invalidate_client_message_stream(
        self,
        client_id: ClientId,
        stream_id: StreamId,
    ) -> None:
        self.last_completed_client_chunk_seq_id_by_stream.pop(
            (client_id, stream_id),
            None,
        )

    def invalidate_client_message_client(self, client_id: ClientId) -> None:
        self.last_completed_client_chunk_seq_id_by_stream = {
            key: value
            for key, value in self.last_completed_client_chunk_seq_id_by_stream.items()
            if key[0] != client_id
        }

    @staticmethod
    def client_message_key(
        client_envelope: ClientEnvelope,
    ) -> tuple[tuple[ClientId, StreamId | None], int] | None:
        if (
            client_envelope.event.kind is not ClientEvent.Kind.CLIENT_MESSAGE_CHUNK
            or client_envelope.seq_id is None
        ):
            return None
        return (
            (client_envelope.client_id, client_envelope.stream_id),
            client_envelope.seq_id,
        )


@dataclass(frozen=True)
class RemoteControlWebsocketConfig:
    remote_control_url: str
    installation_id: str
    remote_control_target: RemoteControlTarget | None
    server_name: str


@dataclass(frozen=True)
class RemoteControlChannels:
    transport_event_tx: asyncio.Queue[TransportEvent]
    status_publisher: "RemoteControlStatusPublisher"


class RemoteControlStatusPublisher:
    def __init__(self, handle: RemoteControlHandle) -> None:
        self._handle = handle

    def status(self):
        return self._handle.status()

    def publish_status(self, status: RemoteControlConnectionStatus) -> None:
        self._handle.publish_status(status)

    def publish_environment_id(self, environment_id: str | None) -> None:
        if self.status().status is RemoteControlConnectionStatus.DISABLED:
            return
        self._handle.publish_status(
            self.status().status,
            environment_id=environment_id,
        )


@dataclass(frozen=True)
class RemoteControlConnectOptions:
    installation_id: str
    server_name: str
    subscribe_cursor: str | None = None
    app_server_client_name: str | None = None


def build_remote_control_websocket_headers(
    enrollment: RemoteControlEnrollment,
    auth: RemoteControlConnectionAuth,
    *,
    installation_id: str,
    subscribe_cursor: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    add_auth_headers = getattr(auth.auth_provider, "add_auth_headers", None)
    if callable(add_auth_headers):
        result = add_auth_headers(headers)
        if isinstance(result, Mapping):
            headers.update({str(key): str(value) for key, value in result.items()})
    headers.update(
        {
            "x-codex-server-id": enrollment.server_id,
            "x-codex-name": base64.b64encode(enrollment.server_name.encode()).decode(),
            "x-codex-protocol-version": REMOTE_CONTROL_PROTOCOL_VERSION,
            REMOTE_CONTROL_ACCOUNT_ID_HEADER: auth.account_id,
            REMOTE_CONTROL_INSTALLATION_ID_HEADER: installation_id,
        }
    )
    if subscribe_cursor is not None:
        headers[REMOTE_CONTROL_SUBSCRIBE_CURSOR_HEADER] = subscribe_cursor
    return headers


async def load_remote_control_auth(
    auth_manager: Any,
    *,
    auth_provider_factory: Callable[[Any], Any] | None = None,
) -> RemoteControlConnectionAuth:
    reloaded = False
    while True:
        auth = await _call_maybe_async(auth_manager, "auth")
        if auth is None:
            if reloaded:
                raise PermissionError("remote control requires ChatGPT authentication")
            await _call_maybe_async(auth_manager, "reload")
            reloaded = True
            continue
        uses_backend = bool(_call_or_value(auth, "uses_codex_backend"))
        if not uses_backend:
            raise PermissionError(
                "remote control requires ChatGPT authentication; "
                "API key auth is not supported"
            )
        account_id = _call_or_value(auth, "get_account_id")
        if account_id is None and not reloaded:
            await _call_maybe_async(auth_manager, "reload")
            reloaded = True
            continue
        if account_id is None:
            raise BlockingIOError(
                "remote control enrollment is waiting for a ChatGPT account id"
            )
        if auth_provider_factory is None:
            from pycodex.model_provider import auth_provider_from_auth

            auth_provider_factory = auth_provider_from_auth
        return RemoteControlConnectionAuth(
            auth_provider=auth_provider_factory(auth),
            account_id=str(account_id),
        )


def next_reconnect_delay(reconnect_attempt: int) -> tuple[float, bool]:
    delay = min(float(2**min(reconnect_attempt, 10)), 30.0)
    return delay, delay == REMOTE_CONTROL_RECONNECT_BACKOFF_CAP_SECONDS


async def connect_remote_control_websocket(
    remote_control_target: RemoteControlTarget,
    state_db: Any | None,
    auth_manager: Any,
    enrollment: RemoteControlEnrollment | None,
    options: RemoteControlConnectOptions,
    status_publisher: RemoteControlStatusPublisher,
) -> tuple[Any, RemoteControlEnrollment]:
    if state_db is None:
        raise FileNotFoundError(
            "remote control enrollment cache unavailable because sqlite state db is disabled"
        )
    auth = await load_remote_control_auth(auth_manager)
    if enrollment is None or enrollment.account_id != auth.account_id:
        enrollment = await load_persisted_remote_control_enrollment(
            state_db,
            remote_control_target,
            auth.account_id,
            options.app_server_client_name,
        )
    if enrollment is None:
        enrollment = await enroll_remote_control_server(
            remote_control_target,
            auth,
            options.installation_id,
            options.server_name,
        )
        await update_persisted_remote_control_enrollment(
            state_db,
            remote_control_target,
            auth.account_id,
            options.app_server_client_name,
            enrollment,
        )
    status_publisher.publish_environment_id(enrollment.environment_id)
    headers = build_remote_control_websocket_headers(
        enrollment,
        auth,
        installation_id=options.installation_id,
        subscribe_cursor=options.subscribe_cursor,
    )
    from websockets.asyncio.client import connect

    try:
        websocket = await asyncio.wait_for(
            connect(
                remote_control_target.websocket_url,
                additional_headers=headers,
                open_timeout=REMOTE_CONTROL_WEBSOCKET_CONNECT_TIMEOUT_SECONDS,
                ping_interval=None,
                ping_timeout=None,
                max_size=REMOTE_CONTROL_SEGMENT_MAX_BYTES,
                max_queue=CHANNEL_CAPACITY,
            ),
            timeout=REMOTE_CONTROL_WEBSOCKET_CONNECT_TIMEOUT_SECONDS,
        )
    except Exception as exc:
        status_code = getattr(getattr(exc, "response", None), "status_code", None)
        if status_code in {401, 403}:
            await update_persisted_remote_control_enrollment(
                state_db,
                remote_control_target,
                auth.account_id,
                options.app_server_client_name,
                None,
            )
        raise OSError(
            "failed to connect remote control websocket at "
            f"`{remote_control_target.websocket_url}`: {exc}"
        ) from exc
    return websocket, enrollment


class RemoteControlWebsocket:
    def __init__(
        self,
        config: RemoteControlWebsocketConfig,
        *,
        state_db: Any | None,
        auth_manager: Any,
        channels: RemoteControlChannels,
        shutdown_token: Any,
        enabled_event: asyncio.Event,
    ) -> None:
        self.remote_control_url = config.remote_control_url
        self.installation_id = config.installation_id
        self.server_name = config.server_name
        self.remote_control_target = config.remote_control_target
        self.state_db = state_db
        self.auth_manager = auth_manager
        self.status_publisher = channels.status_publisher
        self.shutdown_token = shutdown_token
        self.enabled_event = enabled_event
        self.reconnect_attempt = 0
        self.enrollment: RemoteControlEnrollment | None = None
        self.state = WebsocketState()
        self._state_lock = asyncio.Lock()
        self.server_event_rx: asyncio.Queue[QueuedServerEnvelope] = asyncio.Queue(
            maxsize=CHANNEL_CAPACITY
        )
        self.client_tracker = ClientTracker(
            self.server_event_rx,
            channels.transport_event_tx,
            shutdown_token,
        )

    async def run(self, app_server_client_name_rx: Any | None) -> None:
        app_server_client_name = await self._wait_for_app_server_client_name(
            app_server_client_name_rx
        )
        if app_server_client_name_rx is not None and app_server_client_name is None:
            await self.client_tracker.shutdown()
            return
        while not _is_cancelled(self.shutdown_token):
            if not await self._wait_until_enabled():
                break
            try:
                websocket = await self._connect(app_server_client_name)
            except _RemoteControlDisabled:
                self.status_publisher.publish_status(
                    RemoteControlConnectionStatus.DISABLED
                )
                continue
            except _RemoteControlShutdown:
                break
            await self._run_connection(websocket)
        await self.client_tracker.shutdown()

    async def _wait_for_app_server_client_name(
        self,
        receiver: Any | None,
    ) -> str | None:
        if receiver is None:
            return None
        receive_task = asyncio.create_task(_receive_once(receiver))
        cancel_task = asyncio.create_task(_wait_cancelled(self.shutdown_token))
        done, pending = await asyncio.wait(
            {receive_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        if cancel_task in done:
            return None
        return receive_task.result()

    async def _wait_until_enabled(self) -> bool:
        while not self.enabled_event.is_set():
            if _is_cancelled(self.shutdown_token):
                return False
            try:
                await asyncio.wait_for(self.enabled_event.wait(), timeout=0.1)
            except TimeoutError:
                continue
        return not _is_cancelled(self.shutdown_token)

    async def _connect(self, app_server_client_name: str | None) -> Any:
        self.status_publisher.publish_status(RemoteControlConnectionStatus.CONNECTING)
        if self.remote_control_target is None:
            from .protocol import normalize_remote_control_url

            try:
                self.remote_control_target = normalize_remote_control_url(
                    self.remote_control_url
                )
            except ValueError:
                self.status_publisher.publish_status(
                    RemoteControlConnectionStatus.ERRORED
                )
                await self._wait_disabled_or_shutdown()
                raise _RemoteControlDisabled()
        while True:
            if _is_cancelled(self.shutdown_token):
                raise _RemoteControlShutdown()
            if not self.enabled_event.is_set():
                raise _RemoteControlDisabled()
            options = RemoteControlConnectOptions(
                installation_id=self.installation_id,
                server_name=self.server_name,
                subscribe_cursor=self.state.subscribe_cursor,
                app_server_client_name=app_server_client_name,
            )
            try:
                websocket, self.enrollment = await connect_remote_control_websocket(
                    self.remote_control_target,
                    self.state_db,
                    self.auth_manager,
                    self.enrollment,
                    options,
                    self.status_publisher,
                )
            except BlockingIOError:
                delay = REMOTE_CONTROL_ACCOUNT_ID_RETRY_INTERVAL_SECONDS
            except Exception:
                self.status_publisher.publish_status(
                    RemoteControlConnectionStatus.ERRORED
                )
                delay, reset = next_reconnect_delay(self.reconnect_attempt)
                self.reconnect_attempt = 0 if reset else self.reconnect_attempt + 1
            else:
                self.reconnect_attempt = 0
                self.status_publisher.publish_status(
                    RemoteControlConnectionStatus.CONNECTED
                )
                return websocket
            await self._sleep_while_enabled(delay)

    async def _sleep_while_enabled(self, delay: float) -> None:
        deadline = asyncio.get_running_loop().time() + delay
        while asyncio.get_running_loop().time() < deadline:
            if _is_cancelled(self.shutdown_token):
                raise _RemoteControlShutdown()
            if not self.enabled_event.is_set():
                raise _RemoteControlDisabled()
            await asyncio.sleep(min(0.1, deadline - asyncio.get_running_loop().time()))

    async def _wait_disabled_or_shutdown(self) -> None:
        while self.enabled_event.is_set() and not _is_cancelled(self.shutdown_token):
            await asyncio.sleep(0.1)

    async def _run_connection(self, websocket: Any) -> None:
        writer = asyncio.create_task(self._run_server_writer(websocket))
        reader = asyncio.create_task(self._run_websocket_reader(websocket))
        disabled = asyncio.create_task(self._wait_disabled_or_shutdown())
        cancelled = asyncio.create_task(_wait_cancelled(self.shutdown_token))
        done, pending = await asyncio.wait(
            {writer, reader, disabled, cancelled},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if disabled in done and not self.enabled_event.is_set():
            self.status_publisher.publish_status(RemoteControlConnectionStatus.DISABLED)
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
        for task in done:
            if task not in {disabled, cancelled}:
                try:
                    task.result()
                except Exception:
                    pass
        try:
            await websocket.close()
        except Exception:
            pass

    async def _run_server_writer(self, websocket: Any) -> None:
        async with self._state_lock:
            buffered = list(self.state.outbound_buffer.server_envelopes())
        for envelope in buffered:
            await websocket.send(_wire_json(envelope.to_mapping()))
        while True:
            try:
                queued = await asyncio.wait_for(
                    self.server_event_rx.get(),
                    timeout=REMOTE_CONTROL_WEBSOCKET_PING_INTERVAL_SECONDS,
                )
            except TimeoutError:
                pong = await websocket.ping()
                await asyncio.wait_for(
                    pong,
                    timeout=REMOTE_CONTROL_WEBSOCKET_PONG_TIMEOUT_SECONDS,
                )
                continue
            while True:
                async with self._state_lock:
                    has_capacity = self.state.outbound_buffer.used < CHANNEL_CAPACITY
                if has_capacity:
                    break
                await asyncio.sleep(0.01)
            async with self._state_lock:
                key = (queued.client_id, queued.stream_id)
                seq_id = self.state.next_seq_id_by_stream.get(key, 1)
                envelope = ServerEnvelope(
                    event=queued.event,
                    client_id=queued.client_id,
                    stream_id=queued.stream_id,
                    seq_id=seq_id,
                )
                envelopes = split_server_envelope_for_transport(envelope)
                for wire_envelope in envelopes:
                    self.state.outbound_buffer.insert(wire_envelope)
                self.state.next_seq_id_by_stream[key] = seq_id + 1
            for wire_envelope in envelopes:
                await websocket.send(_wire_json(wire_envelope.to_mapping()))
            _complete_write(queued.write_complete_tx)

    async def _run_websocket_reader(self, websocket: Any) -> None:
        next_sweep = (
            asyncio.get_running_loop().time()
            + REMOTE_CONTROL_IDLE_SWEEP_INTERVAL_SECONDS
        )
        recv_task = asyncio.create_task(websocket.recv())
        tracker_task = asyncio.create_task(self.client_tracker.bookkeep_join_set())
        shutdown_task = asyncio.create_task(_wait_cancelled(self.shutdown_token))
        try:
            while True:
                timeout = max(0.01, next_sweep - asyncio.get_running_loop().time())
                done, _ = await asyncio.wait(
                    {recv_task, tracker_task, shutdown_task},
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if shutdown_task in done:
                    return
                if not done:
                    expired = await self.client_tracker.close_expired_clients()
                    await self._invalidate_client_streams(expired)
                    next_sweep = (
                        asyncio.get_running_loop().time()
                        + REMOTE_CONTROL_IDLE_SWEEP_INTERVAL_SECONDS
                    )
                    continue
                if tracker_task in done:
                    client_key = tracker_task.result()
                    if client_key is None:
                        return
                    await self.client_tracker.close_client(client_key)
                    await self._invalidate_client_streams([client_key])
                    tracker_task = asyncio.create_task(
                        self.client_tracker.bookkeep_join_set()
                    )
                    continue

                incoming = recv_task.result()
                recv_task = asyncio.create_task(websocket.recv())
                if isinstance(incoming, bytes):
                    continue
                wire_size = len(incoming.encode())
                try:
                    client_envelope = ClientEnvelope.from_mapping(json.loads(incoming))
                except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                    continue
                key = WebsocketState.client_message_key(client_envelope)
                async with self._state_lock:
                    observation = self.state.observe_client_message(
                        client_envelope,
                        wire_size,
                    )
                if observation.kind is not ClientSegmentObservation.Kind.FORWARD:
                    continue
                delivered = observation.envelope
                assert delivered is not None
                await self.client_tracker.handle_message(delivered)
                async with self._state_lock:
                    self.state.record_client_message_delivery(delivered, key)
                    if delivered.event.kind is ClientEvent.Kind.CLIENT_CLOSED:
                        if delivered.stream_id is None:
                            self.state.client_segment_reassembler.invalidate_client(
                                delivered.client_id
                            )
                            self.state.invalidate_client_message_client(
                                delivered.client_id
                            )
                        else:
                            self.state.client_segment_reassembler.invalidate_stream(
                                delivered.client_id,
                                delivered.stream_id,
                            )
                            self.state.invalidate_client_message_stream(
                                delivered.client_id,
                                delivered.stream_id,
                            )
        finally:
            for task in (recv_task, tracker_task, shutdown_task):
                if not task.done():
                    task.cancel()
            await asyncio.gather(
                recv_task,
                tracker_task,
                shutdown_task,
                return_exceptions=True,
            )

    async def _invalidate_client_streams(
        self,
        client_keys: list[tuple[ClientId, StreamId]],
    ) -> None:
        async with self._state_lock:
            for client_id, stream_id in client_keys:
                self.state.client_segment_reassembler.invalidate_stream(
                    client_id,
                    stream_id,
                )
                self.state.invalidate_client_message_stream(client_id, stream_id)


class _RemoteControlDisabled(Exception):
    pass


class _RemoteControlShutdown(Exception):
    pass


def _wire_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _complete_write(completion: Any | None) -> None:
    if completion is None:
        return
    if isinstance(completion, asyncio.Future):
        if not completion.done():
            completion.set_result(None)
        return
    setter = getattr(completion, "set_result", None)
    if callable(setter):
        setter(None)
    elif callable(completion):
        completion()


async def _call_maybe_async(target: Any, name: str) -> Any:
    method = getattr(target, name)
    value = method() if callable(method) else method
    if hasattr(value, "__await__"):
        return await value
    return value


def _call_or_value(target: Any, name: str) -> Any:
    value = getattr(target, name)
    return value() if callable(value) else value


def _is_cancelled(token: Any) -> bool:
    method = getattr(token, "is_cancelled", None)
    if callable(method):
        return bool(method())
    method = getattr(token, "cancelled", None)
    if callable(method):
        value = method()
        if isinstance(value, bool):
            return value
        close = getattr(value, "close", None)
        if callable(close):
            close()
    return False


async def _wait_cancelled(token: Any) -> None:
    method = getattr(token, "cancelled", None)
    if callable(method):
        value = method()
        if hasattr(value, "__await__"):
            await value
            return
        if value:
            return
    method = getattr(token, "wait_cancelled", None)
    if callable(method):
        await method()
        return
    while not _is_cancelled(token):
        await asyncio.sleep(0.05)


async def _receive_once(receiver: Any) -> str:
    if isinstance(receiver, asyncio.Queue):
        return str(await receiver.get())
    if isinstance(receiver, asyncio.Future):
        return str(await receiver)
    receive = getattr(receiver, "recv", None) or getattr(receiver, "get", None)
    value = receive() if callable(receive) else receiver
    if hasattr(value, "__await__"):
        value = await value
    return str(value)


__all__ = [
    "BoundedOutboundBuffer",
    "REMOTE_CONTROL_PROTOCOL_VERSION",
    "RemoteControlChannels",
    "RemoteControlConnectOptions",
    "RemoteControlStatusPublisher",
    "RemoteControlWebsocket",
    "RemoteControlWebsocketConfig",
    "WebsocketState",
    "build_remote_control_websocket_headers",
    "connect_remote_control_websocket",
    "load_remote_control_auth",
    "next_reconnect_delay",
]
