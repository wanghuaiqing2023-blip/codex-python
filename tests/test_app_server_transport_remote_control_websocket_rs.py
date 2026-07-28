from __future__ import annotations

import asyncio
import base64
import json

import pytest
from websockets.asyncio.server import serve

from pycodex.app_server_protocol import (
    RemoteControlConnectionStatus,
    RemoteControlStatusChangedNotification,
)
from pycodex.app_server_transport.outgoing_message import (
    OutgoingMessage,
    QueuedOutgoingMessage,
)
from pycodex.app_server_transport.transport import TransportEventKind
from pycodex.app_server_transport.transport.remote_control import RemoteControlHandle
from pycodex.app_server_transport.transport.remote_control.enroll import (
    RemoteControlConnectionAuth,
    RemoteControlEnrollment,
    update_persisted_remote_control_enrollment,
)
from pycodex.app_server_transport.transport.remote_control.protocol import (
    ClientEnvelope,
    ClientEvent,
    ClientId,
    RemoteControlTarget,
    ServerEnvelope,
    ServerEvent,
    StreamId,
)
from pycodex.app_server_transport.transport.remote_control.websocket import (
    BoundedOutboundBuffer,
    RemoteControlChannels,
    RemoteControlStatusPublisher,
    RemoteControlWebsocket,
    RemoteControlWebsocketConfig,
    build_remote_control_websocket_headers,
    load_remote_control_auth,
    next_reconnect_delay,
)
from pycodex.state import StateRuntime


class _AuthProvider:
    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["Authorization"] = "Bearer token"


def _server_envelope(
    client: str,
    stream: str,
    seq_id: int,
    *,
    segment_id: int | None = None,
) -> ServerEnvelope:
    event = (
        ServerEvent.server_message(
            OutgoingMessage.app_server_notification({"method": "test"})
        )
        if segment_id is None
        else ServerEvent.server_message_chunk(
            segment_id=segment_id,
            segment_count=2,
            message_size_bytes=2,
            message_chunk_base64="eA==",
        )
    )
    return ServerEnvelope(
        event=event,
        client_id=ClientId(client),
        stream_id=StreamId(stream),
        seq_id=seq_id,
    )


def test_outbound_buffer_ack_is_scoped_by_client_stream_and_segment() -> None:
    buffer = BoundedOutboundBuffer()
    buffer.insert(_server_envelope("client-1", "stream-1", 4, segment_id=0))
    buffer.insert(_server_envelope("client-1", "stream-1", 4, segment_id=1))
    buffer.insert(_server_envelope("client-1", "stream-2", 4))

    buffer.ack(ClientId("client-1"), StreamId("stream-1"), 4, 0)
    retained = list(buffer.server_envelopes())
    assert [(item.stream_id.value, item.event.wire_segment_id()) for item in retained] == [
        ("stream-1", 1),
        ("stream-2", None),
    ]


def test_websocket_headers_include_rust_protocol_identity_and_cursor() -> None:
    headers = build_remote_control_websocket_headers(
        RemoteControlEnrollment(
            account_id="account",
            environment_id="env",
            server_id="server",
            server_name="my server",
        ),
        RemoteControlConnectionAuth(_AuthProvider(), "account"),
        installation_id="install",
        subscribe_cursor="cursor",
    )
    assert headers["x-codex-server-id"] == "server"
    assert headers["x-codex-name"] == base64.b64encode(b"my server").decode()
    assert headers["x-codex-protocol-version"] == "3"
    assert headers["chatgpt-account-id"] == "account"
    assert headers["x-codex-installation-id"] == "install"
    assert headers["x-codex-subscribe-cursor"] == "cursor"
    assert headers["Authorization"] == "Bearer token"


@pytest.mark.asyncio
async def test_load_remote_control_auth_reloads_missing_auth_and_rejects_api_key() -> None:
    class Auth:
        def __init__(self, backend: bool, account: str | None = None) -> None:
            self.backend = backend
            self.account = account

        def uses_codex_backend(self) -> bool:
            return self.backend

        def get_account_id(self) -> str | None:
            return self.account

    class Manager:
        def __init__(self, values) -> None:
            self.values = iter(values)
            self.current = None

        async def auth(self):
            if self.current is None:
                self.current = next(self.values)
            return self.current

        async def reload(self) -> None:
            self.current = next(self.values)

    manager = Manager([None, Auth(True, "account")])
    auth = await load_remote_control_auth(manager, auth_provider_factory=lambda _: _AuthProvider())
    assert auth.account_id == "account"

    with pytest.raises(PermissionError, match="API key auth is not supported"):
        await load_remote_control_auth(
            Manager([Auth(False)]),
            auth_provider_factory=lambda _: _AuthProvider(),
        )


def test_status_publisher_preserves_environment_except_when_disabled() -> None:
    enabled = asyncio.Event()
    handle = RemoteControlHandle(
        enabled_event=enabled,
        initial_status=RemoteControlStatusChangedNotification(
            status=RemoteControlConnectionStatus.CONNECTING,
            server_name="server",
            installation_id="install",
            environment_id="env",
        ),
        state_db_available=True,
    )
    publisher = RemoteControlStatusPublisher(handle)
    publisher.publish_status(RemoteControlConnectionStatus.CONNECTED)
    assert handle.status().environment_id == "env"
    publisher.publish_status(RemoteControlConnectionStatus.DISABLED)
    assert handle.status().environment_id is None


def test_reconnect_backoff_caps_and_resets_like_rust() -> None:
    attempt = 0
    delays = []
    reset_seen = False
    for _ in range(10):
        delay, reset = next_reconnect_delay(attempt)
        delays.append(delay)
        reset_seen = reset_seen or reset
        attempt = 0 if reset else attempt + 1
    assert delays[0] <= delays[-1]
    assert max(delays) == 30.0
    assert reset_seen


@pytest.mark.asyncio
async def test_real_websocket_connection_routes_conversation_through_tracker(
    tmp_path,
) -> None:
    server_received: asyncio.Future[dict] = asyncio.get_running_loop().create_future()

    async def remote_server(connection) -> None:
        await connection.send(
            json.dumps(
                ClientEnvelope(
                    event=ClientEvent.client_message(
                        {"id": 1, "method": "initialize", "params": {}}
                    ),
                    client_id=ClientId("client-1"),
                    stream_id=StreamId("stream-1"),
                    seq_id=0,
                ).to_mapping()
            )
        )
        server_received.set_result(json.loads(await connection.recv()))
        await connection.send(
            json.dumps(
                ClientEnvelope(
                    event=ClientEvent.client_closed(),
                    client_id=ClientId("client-1"),
                    stream_id=StreamId("stream-1"),
                ).to_mapping()
            )
        )

    class Auth:
        def uses_codex_backend(self) -> bool:
            return True

        def get_account_id(self) -> str:
            return "account"

        def get_token(self) -> str:
            return "token"

        def is_fedramp_account(self) -> bool:
            return False

    class AuthManager:
        async def auth(self):
            return Auth()

        async def reload(self) -> None:
            return None

    class Cancellation:
        def __init__(self) -> None:
            self.event = asyncio.Event()

        def cancel(self) -> None:
            self.event.set()

        def is_cancelled(self) -> bool:
            return self.event.is_set()

        async def cancelled(self) -> None:
            await self.event.wait()

    runtime = await StateRuntime.init(tmp_path, "test-provider")
    cancellation = Cancellation()
    enabled = asyncio.Event()
    enabled.set()
    transport_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    handle = RemoteControlHandle(
        enabled_event=enabled,
        initial_status=RemoteControlStatusChangedNotification(
            status=RemoteControlConnectionStatus.CONNECTING,
            server_name="server",
            installation_id="install",
        ),
        state_db_available=True,
    )
    try:
        async with serve(remote_server, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            target = RemoteControlTarget(
                websocket_url=f"ws://127.0.0.1:{port}/remote",
                enroll_url=f"http://127.0.0.1:{port}/enroll",
            )
            await update_persisted_remote_control_enrollment(
                runtime,
                target,
                "account",
                None,
                RemoteControlEnrollment(
                    account_id="account",
                    environment_id="environment",
                    server_id="server-id",
                    server_name="server",
                ),
            )
            websocket = RemoteControlWebsocket(
                RemoteControlWebsocketConfig(
                    remote_control_url="http://localhost",
                    installation_id="install",
                    remote_control_target=target,
                    server_name="server",
                ),
                state_db=runtime,
                auth_manager=AuthManager(),
                channels=RemoteControlChannels(
                    transport_event_tx=transport_events,
                    status_publisher=RemoteControlStatusPublisher(handle),
                ),
                shutdown_token=cancellation,
                enabled_event=enabled,
            )
            task = asyncio.create_task(websocket.run(None))
            opened = await asyncio.wait_for(transport_events.get(), timeout=2)
            initialize = await asyncio.wait_for(transport_events.get(), timeout=2)
            assert opened.kind is TransportEventKind.CONNECTION_OPENED
            assert initialize.kind is TransportEventKind.INCOMING_MESSAGE
            assert opened.writer is not None
            await opened.writer.put(
                QueuedOutgoingMessage.new(
                    OutgoingMessage.app_server_notification(
                        {"method": "server/initialized"}
                    )
                )
            )
            outbound = await asyncio.wait_for(server_received, timeout=2)
            assert outbound["type"] == "server_message"
            assert outbound["message"]["method"] == "server/initialized"
            closed = await asyncio.wait_for(transport_events.get(), timeout=2)
            assert closed.kind is TransportEventKind.CONNECTION_CLOSED
            cancellation.cancel()
            await asyncio.wait_for(task, timeout=2)
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_client_disconnect_is_observed_while_websocket_remains_open(
    tmp_path,
) -> None:
    server_ready = asyncio.Event()
    release_server = asyncio.Event()

    async def remote_server(connection) -> None:
        await connection.send(
            json.dumps(
                ClientEnvelope(
                    event=ClientEvent.client_message(
                        {"id": 1, "method": "initialize", "params": {}}
                    ),
                    client_id=ClientId("client-1"),
                    stream_id=StreamId("stream-1"),
                    seq_id=0,
                ).to_mapping()
            )
        )
        server_ready.set()
        await release_server.wait()

    class Auth:
        def uses_codex_backend(self) -> bool:
            return True

        def get_account_id(self) -> str:
            return "account"

        def get_token(self) -> str:
            return "token"

        def is_fedramp_account(self) -> bool:
            return False

    class AuthManager:
        async def auth(self):
            return Auth()

        async def reload(self) -> None:
            return None

    class Cancellation:
        def __init__(self) -> None:
            self.event = asyncio.Event()

        def cancel(self) -> None:
            self.event.set()

        def is_cancelled(self) -> bool:
            return self.event.is_set()

        async def cancelled(self) -> None:
            await self.event.wait()

    runtime = await StateRuntime.init(tmp_path, "test-provider")
    cancellation = Cancellation()
    enabled = asyncio.Event()
    enabled.set()
    transport_events: asyncio.Queue = asyncio.Queue(maxsize=128)
    handle = RemoteControlHandle(
        enabled_event=enabled,
        initial_status=RemoteControlStatusChangedNotification(
            status=RemoteControlConnectionStatus.CONNECTING,
            server_name="server",
            installation_id="install",
        ),
        state_db_available=True,
    )
    task: asyncio.Task[None] | None = None
    try:
        async with serve(remote_server, "127.0.0.1", 0) as server:
            port = server.sockets[0].getsockname()[1]
            target = RemoteControlTarget(
                websocket_url=f"ws://127.0.0.1:{port}/remote",
                enroll_url=f"http://127.0.0.1:{port}/enroll",
            )
            await update_persisted_remote_control_enrollment(
                runtime,
                target,
                "account",
                None,
                RemoteControlEnrollment(
                    account_id="account",
                    environment_id="environment",
                    server_id="server-id",
                    server_name="server",
                ),
            )
            websocket = RemoteControlWebsocket(
                RemoteControlWebsocketConfig(
                    remote_control_url="http://localhost",
                    installation_id="install",
                    remote_control_target=target,
                    server_name="server",
                ),
                state_db=runtime,
                auth_manager=AuthManager(),
                channels=RemoteControlChannels(
                    transport_event_tx=transport_events,
                    status_publisher=RemoteControlStatusPublisher(handle),
                ),
                shutdown_token=cancellation,
                enabled_event=enabled,
            )
            task = asyncio.create_task(websocket.run(None))
            await asyncio.wait_for(server_ready.wait(), timeout=2)
            opened = await asyncio.wait_for(transport_events.get(), timeout=2)
            await asyncio.wait_for(transport_events.get(), timeout=2)
            assert opened.kind is TransportEventKind.CONNECTION_OPENED
            assert opened.disconnect_sender is not None

            opened.disconnect_sender.cancel()

            closed = await asyncio.wait_for(transport_events.get(), timeout=2)
            assert closed.kind is TransportEventKind.CONNECTION_CLOSED
            assert closed.connection_id == opened.connection_id
            release_server.set()
    finally:
        release_server.set()
        cancellation.cancel()
        if task is not None:
            await asyncio.wait_for(task, timeout=2)
        await runtime.close()
