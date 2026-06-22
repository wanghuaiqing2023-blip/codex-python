"""Rust-derived tests for codex-exec-server/src/connection.rs."""

from __future__ import annotations

import asyncio
import json

from pycodex.app_server_protocol import JSONRPCMessage, JSONRPCRequest
from pycodex.exec_server import JsonRpcConnection, JsonRpcConnectionEvent, JsonRpcTransport, JsonRpcWebSocketMessage, StdioTransport


def test_stdio_connection_reads_messages_skips_blanks_and_reports_eof() -> None:
    # Rust crate/module:
    # codex-exec-server/src/connection.rs::JsonRpcConnection::from_stdio.
    # Contract: stdio reader consumes newline-framed lite JSON-RPC messages,
    # skips blank lines, and reports a disconnected event on EOF.
    async def run() -> tuple[JsonRpcConnectionEvent, JsonRpcConnectionEvent]:
        reader = asyncio.StreamReader()
        writer = MemoryWriter()
        reader.feed_data(b"\n  \n")
        reader.feed_data(b'{"id":1,"method":"test","params":{"ok":true}}\n')
        reader.feed_eof()
        connection = JsonRpcConnection.from_stdio(reader, writer, "stdio-test")
        try:
            message_event = await asyncio.wait_for(connection.incoming_rx.get(), 1)
            disconnected = await asyncio.wait_for(connection.incoming_rx.get(), 1)
            return message_event, disconnected
        finally:
            await connection.close()

    message_event, disconnected = asyncio.run(run())

    assert message_event == JsonRpcConnectionEvent.message_event(
        JSONRPCMessage(JSONRPCRequest(id=1, method="test", params={"ok": True}))
    )
    assert disconnected == JsonRpcConnectionEvent.disconnected(None)


def test_stdio_connection_reports_malformed_jsonrpc_message() -> None:
    # Rust: malformed stdio frames become JsonRpcConnectionEvent::MalformedMessage
    # with the Rust connection-label prefix.
    async def run() -> JsonRpcConnectionEvent:
        reader = asyncio.StreamReader()
        writer = MemoryWriter()
        reader.feed_data(b"{not-json}\n")
        reader.feed_eof()
        connection = JsonRpcConnection.from_stdio(reader, writer, "bad-stdio")
        try:
            return await asyncio.wait_for(connection.incoming_rx.get(), 1)
        finally:
            await connection.close()

    event = asyncio.run(run())

    assert event.kind == "malformed"
    assert event.reason is not None
    assert event.reason.startswith("failed to parse JSON-RPC message from bad-stdio:")


def test_stdio_connection_writes_compact_jsonrpc_lines() -> None:
    # Rust: write_jsonrpc_line_message serializes JSONRPCMessage with
    # serde_json::to_string, appends a newline, and flushes the writer.
    async def run() -> bytes:
        reader = asyncio.StreamReader()
        writer = MemoryWriter()
        connection = JsonRpcConnection.from_stdio(reader, writer, "writer-stdio")
        try:
            await connection.outgoing_tx.put(
                JSONRPCMessage(JSONRPCRequest(id=2, method="out", params={"value": 3}))
            )
            await writer.wait_for_write()
            return bytes(writer.data)
        finally:
            await connection.close()

    encoded = asyncio.run(run())

    assert encoded == b'{"id":2,"method":"out","params":{"value":3}}\n'


def test_stdio_connection_reports_write_errors_as_disconnected() -> None:
    # Rust: stdio writer failures are reported as Disconnected with the
    # connection-label write-error prefix.
    async def run() -> JsonRpcConnectionEvent:
        reader = asyncio.StreamReader()
        writer = FailingWriter()
        connection = JsonRpcConnection.from_stdio(reader, writer, "failing-writer")
        try:
            await connection.outgoing_tx.put(JSONRPCMessage(JSONRPCRequest(id=1, method="out")))
            return await asyncio.wait_for(connection.incoming_rx.get(), 1)
        finally:
            await connection.close()

    event = asyncio.run(run())

    assert event.kind == "disconnected"
    assert event.reason == "failed to write JSON-RPC message to failing-writer: boom"


def test_websocket_connection_sends_configured_ping() -> None:
    # Rust test: websocket_connection_sends_configured_ping.
    # Contract: a websocket connection with a configured keepalive interval
    # sends ping frames when no other traffic arrives.
    async def run() -> JsonRpcWebSocketMessage:
        websocket = ControlledWebSocket()
        connection = JsonRpcConnection.from_websocket_stream(websocket, "ws-test", ping_interval=0.01)
        try:
            return await asyncio.wait_for(websocket.outgoing.get(), 1)
        finally:
            await connection.close()

    message = asyncio.run(run())

    assert message == JsonRpcWebSocketMessage.ping()


def test_websocket_connection_ignores_server_pong() -> None:
    # Rust test: websocket_connection_ignores_server_pong.
    async def run() -> bool:
        websocket = ControlledWebSocket()
        connection = JsonRpcConnection.from_websocket(websocket, "ws-test")
        try:
            await websocket.incoming.put(JsonRpcWebSocketMessage.pong(b"check"))
            try:
                await asyncio.wait_for(connection.incoming_rx.get(), 0.05)
            except TimeoutError:
                return True
            return False
        finally:
            await connection.close()

    assert asyncio.run(run()) is True


def test_websocket_connection_reports_server_close() -> None:
    # Rust test: websocket_connection_reports_server_close.
    async def run() -> JsonRpcConnectionEvent:
        websocket = ControlledWebSocket()
        connection = JsonRpcConnection.from_websocket(websocket, "ws-test")
        try:
            await websocket.incoming.put(JsonRpcWebSocketMessage.close())
            return await asyncio.wait_for(connection.incoming_rx.get(), 1)
        finally:
            await connection.close()

    assert asyncio.run(run()) == JsonRpcConnectionEvent.disconnected(None)


def test_websocket_connection_accepts_binary_jsonrpc_message() -> None:
    # Rust test: websocket_connection_accepts_binary_jsonrpc_message.
    async def run() -> JsonRpcConnectionEvent:
        websocket = ControlledWebSocket()
        connection = JsonRpcConnection.from_websocket(websocket, "ws-test")
        message = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
        try:
            await websocket.incoming.put(
                JsonRpcWebSocketMessage.binary(json.dumps(message.to_mapping()).encode("utf-8"))
            )
            return await asyncio.wait_for(connection.incoming_rx.get(), 1)
        finally:
            await connection.close()

    assert asyncio.run(run()) == JsonRpcConnectionEvent.message_event(
        JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
    )


def test_websocket_connection_keeps_outbound_message_while_send_is_backpressured() -> None:
    # Rust test: websocket_connection_keeps_outbound_message_while_send_is_backpressured.
    # Contract: while an outbound websocket send is blocked, inbound ignored
    # frames do not advance the single transport loop and the outbound message
    # remains the next write once backpressure is released.
    async def run() -> tuple[bool, JsonRpcWebSocketMessage]:
        websocket = ControlledWebSocket(write_ready=False)
        connection = JsonRpcConnection.from_websocket_stream(websocket, "ws-test", ping_interval=None)
        message = JSONRPCMessage(JSONRPCRequest(id=1, method="test"))
        try:
            await connection.outgoing_tx.put(message)
            await websocket.wait_for_blocked_write()
            await websocket.incoming.put(JsonRpcWebSocketMessage.pong(b"check"))
            try:
                await asyncio.wait_for(connection.incoming_rx.get(), 0.05)
                no_event = False
            except TimeoutError:
                no_event = True
            websocket.release_write()
            outbound = await asyncio.wait_for(websocket.outgoing.get(), 1)
            return no_event, outbound
        finally:
            await connection.close()

    no_event, outbound = asyncio.run(run())

    assert no_event is True
    assert outbound == JsonRpcWebSocketMessage.text('{"id":1,"method":"test"}')


def test_stdio_transport_terminate_is_idempotent_and_requests_child_termination() -> None:
    # Rust: StdioTransportHandle::terminate uses an AtomicBool so only the
    # first terminate request notifies the supervisor.
    async def run() -> FakeChildProcess:
        child = FakeChildProcess()
        transport = StdioTransport.spawn(child, grace_period=0.05)
        transport.terminate()
        transport.terminate()
        await child.wait_for_terminate()
        child.finish_wait()
        await asyncio.wait_for(transport.handle.task, 1)
        return child

    child = asyncio.run(run())

    assert child.terminate_calls == 1
    assert child.kill_calls == 0


def test_stdio_transport_kills_child_after_termination_grace_timeout() -> None:
    # Rust: terminate_stdio_child first requests graceful termination, then
    # kills the process tree after STDIO_TERMINATION_GRACE_PERIOD.
    async def run() -> FakeChildProcess:
        child = FakeChildProcess()
        transport = StdioTransport.spawn(child, grace_period=0.01)
        transport.terminate()
        await child.wait_for_kill()
        child.finish_wait()
        await asyncio.wait_for(transport.handle.task, 1)
        return child

    child = asyncio.run(run())

    assert child.terminate_calls == 1
    assert child.kill_calls == 1


def test_stdio_child_supervisor_kills_process_tree_after_child_exit() -> None:
    # Rust: when the stdio child exits before a terminate request, the
    # supervisor logs the wait result and calls kill_process_tree for cleanup.
    async def run() -> FakeChildProcess:
        child = FakeChildProcess()
        transport = StdioTransport.spawn(child, grace_period=0.05)
        child.finish_wait()
        await asyncio.wait_for(transport.handle.task, 1)
        return child

    child = asyncio.run(run())

    assert child.terminate_calls == 0
    assert child.kill_calls == 1


def test_jsonrpc_connection_with_child_process_installs_stdio_transport() -> None:
    # Rust: JsonRpcConnection::with_child_process wraps the connection
    # transport in JsonRpcTransport::Stdio.
    async def run() -> tuple[str, bool]:
        reader = asyncio.StreamReader()
        writer = MemoryWriter()
        child = FakeChildProcess()
        connection = JsonRpcConnection.from_stdio(reader, writer, "child-stdio").with_child_process(child)
        try:
            transport = connection.transport
            transport.terminate()
            await child.wait_for_terminate()
            child.finish_wait()
            return transport.kind, isinstance(transport, JsonRpcTransport)
        finally:
            await connection.close()

    kind, is_transport = asyncio.run(run())

    assert kind == "stdio"
    assert is_transport is True


class MemoryWriter:
    def __init__(self) -> None:
        self.data = bytearray()
        self._write_event = asyncio.Event()

    def write(self, data: bytes) -> None:
        self.data.extend(data)
        self._write_event.set()

    async def drain(self) -> None:
        return None

    async def wait_for_write(self) -> None:
        await asyncio.wait_for(self._write_event.wait(), 1)


class FailingWriter:
    def write(self, data: bytes) -> None:
        raise OSError("boom")

    async def drain(self) -> None:
        return None


class ControlledWebSocket:
    def __init__(self, write_ready: bool = True) -> None:
        self.incoming: asyncio.Queue[JsonRpcWebSocketMessage | None] = asyncio.Queue()
        self.outgoing: asyncio.Queue[JsonRpcWebSocketMessage] = asyncio.Queue()
        self._write_ready = asyncio.Event()
        self._blocked = asyncio.Event()
        if write_ready:
            self._write_ready.set()

    async def recv(self) -> JsonRpcWebSocketMessage | None:
        return await self.incoming.get()

    async def send(self, message: JsonRpcWebSocketMessage) -> None:
        if not self._write_ready.is_set():
            self._blocked.set()
        await self._write_ready.wait()
        await self.outgoing.put(message)

    async def wait_for_blocked_write(self) -> None:
        await asyncio.wait_for(self._blocked.wait(), 1)

    def release_write(self) -> None:
        self._write_ready.set()


class FakeChildProcess:
    def __init__(self) -> None:
        self.terminate_calls = 0
        self.kill_calls = 0
        self._done = asyncio.Event()
        self._terminated = asyncio.Event()
        self._killed = asyncio.Event()

    async def wait(self) -> int:
        await self._done.wait()
        return 0

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._terminated.set()

    def kill(self) -> None:
        self.kill_calls += 1
        self._killed.set()

    def finish_wait(self) -> None:
        self._done.set()

    async def wait_for_terminate(self) -> None:
        await asyncio.wait_for(self._terminated.wait(), 1)

    async def wait_for_kill(self) -> None:
        await asyncio.wait_for(self._killed.wait(), 1)
