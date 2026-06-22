"""Rust-derived tests for codex-exec-server/src/client_transport.rs."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
from pathlib import Path
import sys
import struct
import textwrap

import pytest

import pycodex.exec_server as exec_server
from pycodex.app_server_protocol import JSONRPCMessage, JSONRPCRequest, JSONRPCResponse
from pycodex.exec_server import (
    DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
    ENVIRONMENT_CLIENT_NAME,
    ExecServerClient,
    ExecServerClientConnectOptions,
    ExecServerError,
    ExecServerTransportParams,
    JsonRpcConnection,
    JsonRpcConnectionEvent,
    JsonRpcWebSocketMessage,
    RelayFrameBodyKind,
    RemoteExecServerConnectArgs,
    StdioExecServerCommand,
    StdioExecServerConnectArgs,
    decode_relay_message_frame,
    is_rendezvous_harness_url,
    stdio_command_process_spec,
)


def test_connect_for_transport_projects_websocket_params_to_environment_client() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client_transport.rs::ExecServerClient::connect_for_transport.
    # Contract: WebSocketUrl transport is converted to RemoteExecServerConnectArgs
    # with client_name "codex-environment" and no resume session.
    async def run() -> tuple[RemoteExecServerConnectArgs, ExecServerClient]:
        seen: list[RemoteExecServerConnectArgs] = []

        async def websocket_connector(args: RemoteExecServerConnectArgs) -> JsonRpcConnection:
            seen.append(args)
            return FakeConnection()

        async def initializer(_connection: JsonRpcConnection, options: ExecServerClientConnectOptions) -> str:
            assert options.client_name == ENVIRONMENT_CLIENT_NAME
            assert options.resume_session_id is None
            return "remote-session"

        client = await ExecServerClient.connect_for_transport(
            ExecServerTransportParams.from_websocket_url(
                "ws://127.0.0.1:4567",
                connect_timeout=3,
                initialize_timeout=4,
            ),
            websocket_connector=websocket_connector,
            initializer=initializer,
        )
        return seen[0], client

    args, client = asyncio.run(run())

    assert args == RemoteExecServerConnectArgs(
        websocket_url="ws://127.0.0.1:4567",
        client_name=ENVIRONMENT_CLIENT_NAME,
        connect_timeout=3,
        initialize_timeout=4,
        resume_session_id=None,
    )
    assert client.session_id() == "remote-session"


def test_is_rendezvous_harness_url_matches_rust_query_scan() -> None:
    # Rust source contract:
    # codex-exec-server/src/client_transport.rs::is_rendezvous_harness_url.
    # Contract: only a literal query pair `role=harness` selects the rendezvous
    # harness relay transport; query parsing is split-based and not URL-decoded.
    assert is_rendezvous_harness_url("wss://rendezvous.test/ws?role=harness") is True
    assert is_rendezvous_harness_url("wss://rendezvous.test/ws?sig=abc&role=harness") is True
    assert is_rendezvous_harness_url("wss://rendezvous.test/ws?role=environment") is False
    assert is_rendezvous_harness_url("wss://rendezvous.test/ws?ROLE=harness") is False
    assert is_rendezvous_harness_url("wss://rendezvous.test/ws?role=harness%20") is False
    assert is_rendezvous_harness_url("wss://rendezvous.test/ws") is False


def test_connect_websocket_selects_harness_or_plain_connection_from_url_role() -> None:
    # Rust source contract:
    # codex-exec-server/src/client_transport.rs::ExecServerClient::connect_websocket.
    # Contract: after websocket connect, URLs with query pair `role=harness`
    # wrap the stream with relay::harness_connection_from_websocket; all other
    # URLs use JsonRpcConnection::from_websocket.
    async def run_harness() -> tuple[ExecServerClient, RelayFrameBodyKind]:
        websocket = ControlledClientWebSocket()

        async def connector(_args: RemoteExecServerConnectArgs) -> ControlledClientWebSocket:
            return websocket

        async def initializer(connection: JsonRpcConnection, _options: ExecServerClientConnectOptions) -> str:
            resume = await asyncio.wait_for(websocket.outgoing.get(), 1)
            assert resume.kind == "binary"
            assert isinstance(resume.data, bytes)
            frame = decode_relay_message_frame(resume.data)
            return f"harness:{frame.validate().value}"

        client = await ExecServerClient.connect_websocket(
            RemoteExecServerConnectArgs(
                websocket_url="wss://rendezvous.test/cloud-agent/default/ws/environment/env-1?role=harness&sig=abc",
                client_name="harness-client",
            ),
            websocket_connector=connector,
            initializer=initializer,
        )
        await client.connection.close()
        return client, RelayFrameBodyKind.RESUME

    async def run_plain() -> tuple[ExecServerClient, JsonRpcWebSocketMessage]:
        websocket = ControlledClientWebSocket()

        async def connector(_args: RemoteExecServerConnectArgs) -> ControlledClientWebSocket:
            return websocket

        async def initializer(connection: JsonRpcConnection, _options: ExecServerClientConnectOptions) -> str:
            await connection.outgoing_tx.put(JSONRPCMessage(JSONRPCRequest(id=7, method="plain")))
            return "plain-session"

        client = await ExecServerClient.connect_websocket(
            RemoteExecServerConnectArgs(
                websocket_url="wss://rendezvous.test/cloud-agent/default/ws/environment/env-1?role=environment",
                client_name="plain-client",
            ),
            websocket_connector=connector,
            initializer=initializer,
        )
        outgoing = await asyncio.wait_for(websocket.outgoing.get(), 1)
        await client.connection.close()
        return client, outgoing

    harness_client, resume_kind = asyncio.run(run_harness())
    plain_client, plain_outgoing = asyncio.run(run_plain())

    assert harness_client.session_id() == "harness:resume"
    assert resume_kind is RelayFrameBodyKind.RESUME
    assert plain_client.session_id() == "plain-session"
    assert plain_outgoing.kind == "text"
    assert plain_outgoing.data == '{"id":7,"method":"plain"}'


def test_connect_websocket_maps_connect_timeout_like_rust() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client_transport.rs::ExecServerClient::connect_websocket.
    # Anchors: tokio::time::timeout(connect_timeout, connect_async(...)) and
    # client.rs::ExecServerError::WebSocketConnectTimeout.
    # Contract: the websocket dial future is bounded by connect_timeout and
    # timeout failure displays the Rust websocket timeout error text.
    async def run() -> tuple[str, str, bool]:
        cancelled = False

        async def connector(_args: RemoteExecServerConnectArgs) -> ControlledClientWebSocket:
            nonlocal cancelled
            try:
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                cancelled = True
                raise
            raise AssertionError("connector should have timed out")

        try:
            await ExecServerClient.connect_websocket(
                RemoteExecServerConnectArgs(
                    websocket_url="wss://rendezvous.test/ws",
                    client_name="timeout-client",
                    connect_timeout=0.01,
                ),
                websocket_connector=connector,
                initializer=lambda _connection, _options: "unused",
            )
        except ExecServerError as exc:
            return exc.kind or "", str(exc), cancelled
        raise AssertionError("connect timeout should fail")

    kind, message, cancelled = asyncio.run(run())

    assert kind == "websocket_connect_timeout"
    assert message == (
        "timed out connecting to exec-server websocket "
        "`wss://rendezvous.test/ws` after 10ms"
    )
    assert cancelled is True


def test_connect_websocket_maps_connector_error_like_rust() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client_transport.rs::ExecServerClient::connect_websocket.
    # Anchor: connect_async(...).map_err(ExecServerError::WebSocketConnect).
    # Contract: websocket dial errors preserve the target URL and source error
    # display in the Rust WebSocketConnect message shape.
    async def run() -> tuple[str, str, BaseException | None]:
        async def connector(_args: RemoteExecServerConnectArgs) -> ControlledClientWebSocket:
            raise OSError("dns failed")

        try:
            await ExecServerClient.connect_websocket(
                RemoteExecServerConnectArgs(
                    websocket_url="wss://rendezvous.test/ws",
                    client_name="error-client",
                    connect_timeout=3,
                ),
                websocket_connector=connector,
                initializer=lambda _connection, _options: "unused",
            )
        except ExecServerError as exc:
            return exc.kind or "", str(exc), getattr(exc, "source", None)
        raise AssertionError("connect error should fail")

    kind, message, source = asyncio.run(run())

    assert kind == "websocket_connect"
    assert message == (
        "failed to connect to exec-server websocket "
        "`wss://rendezvous.test/ws`: dns failed"
    )
    assert isinstance(source, OSError)


def test_connect_websocket_without_injected_connector_uses_stdlib_handshake(monkeypatch) -> None:
    # Rust source contract:
    # codex-exec-server/src/client_transport.rs::ExecServerClient::connect_websocket.
    # Anchor: timeout(connect_timeout, connect_async(websocket_url.as_str())).
    # Contract: without an injected connector, Python performs the websocket
    # HTTP upgrade, sends masked client frames, receives server frames, and then
    # routes the stream through JsonRpcConnection::from_websocket before the
    # initialize/initialized handoff.
    async def run() -> tuple[ExecServerClient, StdlibWebSocketFakeWriter, tuple[object, ...], dict[str, object]]:
        reader = asyncio.StreamReader()
        writer = StdlibWebSocketFakeWriter(reader)
        open_args: list[tuple[object, ...]] = []
        open_kwargs: list[dict[str, object]] = []

        async def fake_open_connection(*args: object, **kwargs: object) -> tuple[asyncio.StreamReader, StdlibWebSocketFakeWriter]:
            open_args.append(args)
            open_kwargs.append(kwargs)
            return reader, writer

        monkeypatch.setattr(exec_server.asyncio, "open_connection", fake_open_connection)
        client = await ExecServerClient.connect_websocket(
            RemoteExecServerConnectArgs(
                websocket_url="ws://127.0.0.1:7777/exec?token=abc",
                client_name="stdlib-ws-client",
                connect_timeout=1,
                initialize_timeout=1,
            )
        )
        await wait_for_client_messages(writer, 2)
        await client.connection.close()
        return client, writer, open_args[0], open_kwargs[0]

    client, writer, open_args, open_kwargs = asyncio.run(run())

    assert client.session_id() == "stdlib-ws-session"
    assert open_args == ("127.0.0.1", 7777)
    assert open_kwargs == {"ssl": None}
    assert writer.http_request.startswith("GET /exec?token=abc HTTP/1.1\r\n")
    assert "host: 127.0.0.1:7777\r\n" in writer.http_request
    assert "upgrade: websocket\r\n" in writer.http_request
    assert len(writer.client_messages) == 2
    assert writer.client_messages[0]["method"] == "initialize"
    assert writer.client_messages[0]["params"] == {"clientName": "stdlib-ws-client"}
    assert writer.client_messages[1] == {"method": "initialized"}
    assert all(masked for _message, masked in writer.client_frame_masking)


def test_stdlib_websocket_upgrade_response_requires_tungstenite_protocol_headers() -> None:
    # Rust source contract:
    # codex-exec-server/src/client_transport.rs::ExecServerClient::connect_websocket.
    # Anchor: tokio_tungstenite::connect_async(websocket_url.as_str()).
    # Contract: the dependency-light Python handshake mirrors tungstenite's
    # successful 101 upgrade boundary by requiring Upgrade, Connection, and
    # Sec-WebSocket-Accept before returning a websocket stream.
    key = "dGhlIHNhbXBsZSBub25jZQ=="
    accept = base64.b64encode(
        hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
    ).decode("ascii")

    def response(*headers: str) -> bytes:
        return (
            "HTTP/1.1 101 Switching Protocols\r\n"
            + "\r\n".join(headers)
            + "\r\n\r\n"
        ).encode("ascii")

    exec_server._validate_websocket_upgrade_response(
        response(
            "Upgrade: websocket",
            "Connection: keep-alive, Upgrade",
            f"Sec-WebSocket-Accept: {accept}",
        ),
        key,
    )

    with pytest.raises(ValueError, match="invalid Upgrade header"):
        exec_server._validate_websocket_upgrade_response(
            response(
                "Connection: Upgrade",
                f"Sec-WebSocket-Accept: {accept}",
            ),
            key,
        )

    with pytest.raises(ValueError, match="invalid Connection header"):
        exec_server._validate_websocket_upgrade_response(
            response(
                "Upgrade: websocket",
                "Connection: keep-alive",
                f"Sec-WebSocket-Accept: {accept}",
            ),
            key,
        )


def test_connect_for_transport_projects_stdio_command_to_environment_client() -> None:
    # Rust test: connect_for_transport_initializes_stdio_command.
    # Contract: StdioCommand transport is converted to StdioExecServerConnectArgs
    # with client_name "codex-environment" and the configured initialize timeout.
    async def run() -> tuple[StdioExecServerCommand, ExecServerClient]:
        command = StdioExecServerCommand(program="server", args=["--listen", "stdio"])
        seen: list[StdioExecServerCommand] = []

        async def stdio_connector(command_arg: StdioExecServerCommand) -> JsonRpcConnection:
            seen.append(command_arg)
            return FakeConnection()

        async def initializer(_connection: JsonRpcConnection, options: ExecServerClientConnectOptions) -> str:
            assert options.client_name == ENVIRONMENT_CLIENT_NAME
            assert options.initialize_timeout == 8
            assert options.resume_session_id is None
            return "stdio-session"

        client = await ExecServerClient.connect_for_transport(
            ExecServerTransportParams.stdio_command(command, initialize_timeout=8),
            stdio_connector=stdio_connector,
            initializer=initializer,
        )
        return seen[0], client

    command, client = asyncio.run(run())

    assert command == StdioExecServerCommand(program="server", args=["--listen", "stdio"])
    assert client.session_id() == "stdio-session"


def test_connect_stdio_command_uses_options_conversion() -> None:
    # Rust: connect_stdio_command passes args.into() to ExecServerClient::connect.
    async def run() -> ExecServerClient:
        async def stdio_connector(_command: StdioExecServerCommand) -> JsonRpcConnection:
            return FakeConnection()

        async def initializer(_connection: JsonRpcConnection, options: ExecServerClientConnectOptions) -> str:
            assert options == ExecServerClientConnectOptions(
                client_name="stdio-test-client",
                initialize_timeout=5,
                resume_session_id="resume-me",
            )
            return "resumed-session"

        return await ExecServerClient.connect_stdio_command(
            StdioExecServerConnectArgs(
                command=StdioExecServerCommand(program="server"),
                client_name="stdio-test-client",
                initialize_timeout=5,
                resume_session_id="resume-me",
            ),
            stdio_connector=stdio_connector,
            initializer=initializer,
        )

    assert asyncio.run(run()).session_id() == "resumed-session"


def test_connect_stdio_command_spawns_real_json_rpc_client(tmp_path: Path) -> None:
    # Rust tests:
    # connect_stdio_command_initializes_json_rpc_client_on_windows and the
    # non-Windows stdio initialization companion.
    # Contract: without an injected connector, connect_stdio_command spawns the
    # configured command with piped stdio/env/cwd, performs initialize, then
    # sends initialized.
    script = textwrap.dedent(
        """
        import json
        import os
        import pathlib
        import sys

        initialize = json.loads(sys.stdin.readline())
        assert initialize["method"] == "initialize"
        session_id = os.environ["PYCODEX_STDIO_TEST"] + ":" + pathlib.Path.cwd().name
        sys.stdout.write(json.dumps({"id": initialize["id"], "result": {"sessionId": session_id}}) + "\\n")
        sys.stdout.flush()
        initialized = json.loads(sys.stdin.readline())
        assert initialized["method"] == "initialized"
        """
    )

    async def run() -> tuple[str | None, str]:
        client = await ExecServerClient.connect_stdio_command(
            StdioExecServerConnectArgs(
                command=StdioExecServerCommand(
                    program=sys.executable,
                    args=["-u", "-c", script],
                    env={"PYCODEX_STDIO_TEST": "stdio-real"},
                    cwd=tmp_path,
                ),
                client_name="stdio-test-client",
                initialize_timeout=2,
                resume_session_id=None,
            )
        )
        transport_kind = client.connection.transport.kind
        session_id = client.session_id()
        stdio_transport = client.connection.transport.stdio_transport
        if stdio_transport is not None and stdio_transport.handle.task is not None:
            await asyncio.wait_for(stdio_transport.handle.task, 1)
        await client.connection.close()
        return session_id, transport_kind

    session_id, transport_kind = asyncio.run(run())

    assert session_id == f"stdio-real:{tmp_path.name}"
    assert transport_kind == "stdio"


def test_connect_stdio_command_spawn_error_matches_rust_prefix() -> None:
    # Rust: ExecServerError::Spawn displays "failed to spawn exec-server: ...".
    async def run() -> str:
        try:
            await ExecServerClient.connect_stdio_command(
                StdioExecServerConnectArgs(
                    command=StdioExecServerCommand(program="definitely-not-a-pycodex-exec-server"),
                    client_name="stdio-test-client",
                    initialize_timeout=1,
                    resume_session_id=None,
                )
            )
        except Exception as exc:
            return str(exc)
        raise AssertionError("missing command should fail to spawn")

    assert asyncio.run(run()).startswith("failed to spawn exec-server:")


def test_initialize_connection_sends_initialize_then_initialized() -> None:
    # Rust: ExecServerClient::connect initializes the JSON-RPC connection and
    # sends initialized after the initialize response.
    async def run() -> tuple[list[dict[str, object]], ExecServerClient]:
        connection = FakeConnection()

        async def server() -> None:
            first = await connection.outgoing_tx.get()
            assert first.to_mapping() == {
                "id": 1,
                "method": "initialize",
                "params": {
                    "clientName": "wire-client",
                    "resumeSessionId": "resume-1",
                },
            }
            await connection.incoming_rx.put(
                JsonRpcConnectionEvent.message_event(
                    JSONRPCMessage(JSONRPCResponse(id=1, result={"sessionId": "wire-session"}))
                )
            )
            second = await connection.outgoing_tx.get()
            connection.sent.append(second.to_mapping())

        task = asyncio.create_task(server())
        client = await ExecServerClient.connect(
            connection,
            ExecServerClientConnectOptions(
                client_name="wire-client",
                initialize_timeout=DEFAULT_REMOTE_EXEC_SERVER_INITIALIZE_TIMEOUT,
                resume_session_id="resume-1",
            ),
        )
        await task
        return connection.sent, client

    sent, client = asyncio.run(run())

    assert sent == [{"method": "initialized"}]
    assert client.session_id() == "wire-session"


def test_stdio_command_process_spec_matches_rust_command_builder(tmp_path: Path) -> None:
    # Rust: stdio_command_process sets program, args, env, cwd, piped stdio,
    # and process_group(0) on Unix.
    command = StdioExecServerCommand(
        program="server",
        args=["--listen", "stdio"],
        env={"A": "B"},
        cwd=tmp_path,
    )

    spec = stdio_command_process_spec(command)

    assert spec.program == "server"
    assert spec.args == ("--listen", "stdio")
    assert spec.env == {"A": "B"}
    assert spec.cwd == tmp_path
    assert spec.stdin_piped is True
    assert spec.stdout_piped is True
    assert spec.stderr_piped is True


class FakeConnection(JsonRpcConnection):
    def __init__(self) -> None:
        self.sent: list[dict[str, object]] = []
        super().__init__(
            outgoing_tx=asyncio.Queue(),
            incoming_rx=asyncio.Queue(),
            disconnected=asyncio.Event(),
            task_handles=[],
        )


class ControlledClientWebSocket:
    def __init__(self) -> None:
        self.incoming: asyncio.Queue[JsonRpcWebSocketMessage | None] = asyncio.Queue()
        self.outgoing: asyncio.Queue[JsonRpcWebSocketMessage] = asyncio.Queue()

    async def recv(self) -> JsonRpcWebSocketMessage | None:
        return await self.incoming.get()

    async def send(self, message: JsonRpcWebSocketMessage) -> None:
        await self.outgoing.put(message)


class StdlibWebSocketFakeWriter:
    def __init__(self, reader: asyncio.StreamReader) -> None:
        self.reader = reader
        self.http_request = ""
        self.client_messages: list[dict[str, object]] = []
        self.client_frame_masking: list[tuple[dict[str, object], bool]] = []
        self.data = bytearray()

    def write(self, data: bytes) -> None:
        self.data.extend(data)
        if data.startswith(b"GET "):
            self.http_request = data.decode("ascii")
            key = websocket_request_header(self.http_request, "sec-websocket-key")
            accept = base64.b64encode(
                hashlib.sha1((key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")).digest()
            ).decode("ascii")
            self.reader.feed_data(
                (
                    "HTTP/1.1 101 Switching Protocols\r\n"
                    "upgrade: websocket\r\n"
                    "connection: Upgrade\r\n"
                    f"sec-websocket-accept: {accept}\r\n"
                    "\r\n"
                ).encode("ascii")
            )
            return
        message, masked = decode_client_websocket_frame(data)
        self.client_messages.append(message)
        self.client_frame_masking.append((message, masked))
        if message.get("method") == "initialize":
            response = {
                "id": message["id"],
                "result": {
                    "sessionId": "stdlib-ws-session",
                },
            }
            self.reader.feed_data(exec_server._encode_websocket_frame(0x1, json.dumps(response).encode("utf-8")))

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        return None

    async def wait_closed(self) -> None:
        return None


def websocket_request_header(request: str, name: str) -> str:
    prefix = f"{name.lower()}:"
    for line in request.split("\r\n"):
        if line.lower().startswith(prefix):
            return line.split(":", 1)[1].strip()
    raise AssertionError(f"missing websocket request header {name}")


def decode_client_websocket_frame(data: bytes) -> tuple[dict[str, object], bool]:
    first, second = data[0], data[1]
    opcode = first & 0x0F
    masked = (second & 0x80) != 0
    length = second & 0x7F
    offset = 2
    if length == 126:
        length = struct.unpack("!H", data[offset : offset + 2])[0]
        offset += 2
    elif length == 127:
        length = struct.unpack("!Q", data[offset : offset + 8])[0]
        offset += 8
    mask = data[offset : offset + 4] if masked else b""
    if masked:
        offset += 4
    payload = data[offset : offset + length]
    if masked:
        payload = bytes(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    assert opcode == 0x1
    return json.loads(payload.decode("utf-8")), masked


async def wait_for_client_messages(writer: StdlibWebSocketFakeWriter, count: int) -> None:
    deadline = asyncio.get_running_loop().time() + 1.0
    while asyncio.get_running_loop().time() < deadline:
        if len(writer.client_messages) >= count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} client websocket messages, got {len(writer.client_messages)}")
