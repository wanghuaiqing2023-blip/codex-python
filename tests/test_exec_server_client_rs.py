"""Rust-derived tests for codex-exec-server/src/client.rs."""

from __future__ import annotations

import asyncio

import pytest

from pycodex.app_server_protocol import JSONRPCError, JSONRPCMessage, JSONRPCNotification, JSONRPCResponse
from pycodex.app_server_protocol.jsonrpc_lite import JSONRPCErrorError
from pycodex.exec_server import (
    EXEC_CLOSED_METHOD,
    EXEC_EXITED_METHOD,
    EXEC_OUTPUT_DELTA_METHOD,
    EXEC_READ_METHOD,
    EXEC_TERMINATE_METHOD,
    EXEC_WRITE_METHOD,
    ByteChunk,
    ExecClosedNotification,
    ExecExitedNotification,
    ExecOutputDeltaNotification,
    ExecOutputStream,
    ExecProcessEvent,
    ExecServerClient,
    ExecServerClientConnectOptions,
    ExecServerError,
    ExecServerTransportParams,
    HttpHeader,
    HttpRequestParams,
    HttpRequestResponse,
    JsonRpcConnection,
    JsonRpcConnectionEvent,
    LazyRemoteExecServerClient,
    ProcessId,
    ProcessOutputChunk,
    ReadParams,
    StdioExecServerCommand,
    TerminateResponse,
    WriteResponse,
    WriteStatus,
    encode_exec_closed_notification,
    encode_exec_exited_notification,
    encode_exec_output_delta_notification,
)


class FakeConnection(JsonRpcConnection):
    def __init__(self) -> None:
        super().__init__(
            outgoing_tx=asyncio.Queue(),
            incoming_rx=asyncio.Queue(),
            disconnected=asyncio.Event(),
            task_handles=[],
        )


def _connected_client() -> ExecServerClient:
    return ExecServerClient(
        FakeConnection(),
        ExecServerClientConnectOptions(),
        session_id="session-1",
    )


async def _send_notification(client: ExecServerClient, method: str, params: dict[str, object]) -> None:
    await client.connection.incoming_rx.put(
        JsonRpcConnectionEvent.message_event(
            JSONRPCMessage(JSONRPCNotification(method=method, params=params))
        )
    )


def test_process_events_are_delivered_in_seq_order_when_notifications_are_reordered() -> None:
    # Rust: codex-exec-server/src/client.rs test
    # `process_events_are_delivered_in_seq_order_when_notifications_are_reordered`.
    # Contract: connection-global process notifications are routed by process id
    # and only published to the session event stream when prior sequence
    # numbers have already been delivered.
    async def run() -> list[ExecProcessEvent]:
        client = _connected_client()
        process_id = ProcessId.new("reordered")
        session = await client.register_session(process_id)
        events = session.subscribe_events()

        await _send_notification(
            client,
            EXEC_CLOSED_METHOD,
            encode_exec_closed_notification(ExecClosedNotification(process_id, 4)),
        )
        await _send_notification(
            client,
            EXEC_OUTPUT_DELTA_METHOD,
            encode_exec_output_delta_notification(
                ExecOutputDeltaNotification(process_id, 1, ExecOutputStream.STDOUT, ByteChunk(b"one"))
            ),
        )
        await _send_notification(
            client,
            EXEC_EXITED_METHOD,
            encode_exec_exited_notification(ExecExitedNotification(process_id, 3, 0)),
        )
        await _send_notification(
            client,
            EXEC_OUTPUT_DELTA_METHOD,
            encode_exec_output_delta_notification(
                ExecOutputDeltaNotification(process_id, 2, ExecOutputStream.STDERR, ByteChunk(b"two"))
            ),
        )

        delivered = [await asyncio.wait_for(events.recv(), timeout=1) for _ in range(4)]
        assert process_id not in client.sessions
        client.reader_task.cancel()
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return delivered

    assert asyncio.run(run()) == [
        ExecProcessEvent.output(ProcessOutputChunk(1, ExecOutputStream.STDOUT, ByteChunk(b"one"))),
        ExecProcessEvent.output(ProcessOutputChunk(2, ExecOutputStream.STDERR, ByteChunk(b"two"))),
        ExecProcessEvent.exited(seq=3, exit_code=0),
        ExecProcessEvent.closed(seq=4),
    ]


def test_transport_disconnect_fails_sessions_and_rejects_new_sessions() -> None:
    # Rust: codex-exec-server/src/client.rs test
    # `transport_disconnect_fails_sessions_and_rejects_new_sessions`.
    # Contract: transport disconnect publishes a Failed event, synthesizes a
    # closed read response for existing sessions, and rejects new sessions.
    async def run() -> tuple[ExecProcessEvent, str | None, bool, str]:
        client = _connected_client()
        session = await client.register_session(ProcessId.new("disconnect"))
        events = session.subscribe_events()

        await client.connection.incoming_rx.put(JsonRpcConnectionEvent.disconnected())
        event = await asyncio.wait_for(events.recv(), timeout=1)
        response = await session.read(None, None, None)
        try:
            await client.register_session(ProcessId.new("new"))
        except ExecServerError as exc:
            register_error = str(exc)
        else:
            raise AssertionError("registering after disconnect should fail")
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return event, response.failure, response.closed, register_error

    event, failure, closed, register_error = asyncio.run(run())

    assert event == ExecProcessEvent.failed("exec-server transport disconnected")
    assert failure == "exec-server transport disconnected"
    assert closed is True
    assert register_error == "exec-server transport disconnected"


def test_wake_notifications_do_not_block_other_sessions() -> None:
    # Rust: codex-exec-server/src/client.rs test
    # `wake_notifications_do_not_block_other_sessions`.
    # Contract: a noisy session's notification stream must not prevent a quiet
    # session from receiving its own wake notification.
    async def run() -> int:
        client = _connected_client()
        noisy_process_id = ProcessId.new("noisy")
        quiet_process_id = ProcessId.new("quiet")
        await client.register_session(noisy_process_id)
        quiet_session = await client.register_session(quiet_process_id)
        quiet_wake = quiet_session.subscribe_wake()

        for seq in range(1, 65):
            await _send_notification(
                client,
                EXEC_OUTPUT_DELTA_METHOD,
                encode_exec_output_delta_notification(
                    ExecOutputDeltaNotification(
                        noisy_process_id,
                        seq,
                        ExecOutputStream.STDOUT,
                        ByteChunk(b"x"),
                    )
                ),
            )
        await _send_notification(
            client,
            EXEC_EXITED_METHOD,
            encode_exec_exited_notification(ExecExitedNotification(quiet_process_id, 1, 17)),
        )

        wake_value = await asyncio.wait_for(quiet_wake.get(), timeout=1)
        client.reader_task.cancel()
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return wake_value

    assert asyncio.run(run()) == 1


def test_register_session_rejects_duplicate_process_id() -> None:
    # Rust: codex-exec-server/src/client.rs::Inner::insert_session.
    # Contract: a single client may not register two sessions for the same
    # logical process id.
    async def run() -> str:
        client = _connected_client()
        await client.register_session("same")
        with pytest.raises(ExecServerError) as exc_info:
            await client.register_session("same")
        client.reader_task.cancel()
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return str(exc_info.value)

    assert asyncio.run(run()) == "exec-server protocol error: session already registered for process same"


def test_client_read_write_terminate_forward_jsonrpc_calls() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client.rs::ExecServerClient::{read,write,terminate}.
    # Contract: each public process-control helper forwards to the shared
    # JSON-RPC call boundary with Rust protocol method names and serde
    # camelCase/base64 params, then decodes the typed response.
    async def run() -> tuple[list[dict[str, object]], object, WriteResponse, TerminateResponse]:
        client = _connected_client()
        process_id = ProcessId.new("proc-rpc")
        read_task = asyncio.create_task(
            client.read(ReadParams(process_id=process_id, after_seq=None, max_bytes=5, wait_ms=25))
        )
        read_request = await client.connection.outgoing_tx.get()
        await client.connection.incoming_rx.put(
            JsonRpcConnectionEvent.message_event(
                JSONRPCMessage(
                    JSONRPCResponse(
                        id=read_request.value.id,
                        result={
                            "chunks": [{"seq": 7, "stream": "stdout", "chunk": "aGk="}],
                            "nextSeq": 8,
                            "exited": False,
                            "exitCode": None,
                            "closed": False,
                            "failure": None,
                        },
                    )
                )
            )
        )
        read_response = await read_task

        write_task = asyncio.create_task(client.write(process_id, b"stdin"))
        write_request = await client.connection.outgoing_tx.get()
        await client.connection.incoming_rx.put(
            JsonRpcConnectionEvent.message_event(
                JSONRPCMessage(JSONRPCResponse(id=write_request.value.id, result={"status": "accepted"}))
            )
        )
        write_response = await write_task

        terminate_task = asyncio.create_task(client.terminate(process_id))
        terminate_request = await client.connection.outgoing_tx.get()
        await client.connection.incoming_rx.put(
            JsonRpcConnectionEvent.message_event(
                JSONRPCMessage(JSONRPCResponse(id=terminate_request.value.id, result={"running": True}))
            )
        )
        terminate_response = await terminate_task

        requests = [read_request.to_mapping(), write_request.to_mapping(), terminate_request.to_mapping()]
        client.reader_task.cancel()
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return requests, read_response.chunks[0], write_response, terminate_response

    requests, chunk, write_response, terminate_response = asyncio.run(run())

    assert requests == [
        {
            "id": 1,
            "method": EXEC_READ_METHOD,
            "params": {"processId": "proc-rpc", "afterSeq": None, "maxBytes": 5, "waitMs": 25},
        },
        {
            "id": 2,
            "method": EXEC_WRITE_METHOD,
            "params": {"processId": "proc-rpc", "chunk": "c3RkaW4="},
        },
        {
            "id": 3,
            "method": EXEC_TERMINATE_METHOD,
            "params": {"processId": "proc-rpc"},
        },
    ]
    assert chunk == ProcessOutputChunk(seq=7, stream=ExecOutputStream.STDOUT, chunk=ByteChunk(b"hi"))
    assert write_response == WriteResponse(WriteStatus.ACCEPTED)
    assert terminate_response == TerminateResponse(running=True)


def test_client_call_maps_server_error_and_disconnect_like_rust() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client.rs::ExecServerClient::call.
    # Contract: JSON-RPC server errors map to
    # ExecServerError::Server display text, and transport disconnect races map
    # pending calls to the Rust disconnected message.
    async def run_server_error() -> str:
        client = _connected_client()
        call_task = asyncio.create_task(client.call("boom", {"x": 1}))
        request = await client.connection.outgoing_tx.get()
        await client.connection.incoming_rx.put(
            JsonRpcConnectionEvent.message_event(
                JSONRPCMessage(
                    JSONRPCError(
                        id=request.value.id,
                        error=JSONRPCErrorError(code=-32600, message="bad request", data=None),
                    )
                )
            )
        )
        with pytest.raises(ExecServerError) as exc_info:
            await call_task
        client.reader_task.cancel()
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return str(exc_info.value)

    async def run_disconnect() -> str:
        client = _connected_client()
        call_task = asyncio.create_task(client.call("slow", {"x": 1}))
        await client.connection.outgoing_tx.get()
        await client.connection.incoming_rx.put(JsonRpcConnectionEvent.disconnected("closed"))
        with pytest.raises(ExecServerError) as exc_info:
            await call_task
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return str(exc_info.value)

    server_error = asyncio.run(run_server_error())
    disconnect_error = asyncio.run(run_disconnect())

    assert server_error == "exec-server rejected request (-32600): bad request"
    assert disconnect_error == "exec-server transport disconnected: closed"


def test_lazy_remote_exec_server_client_caches_and_reconnects_like_rust(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust crate/module:
    # codex-exec-server/src/client.rs::LazyRemoteExecServerClient::get.
    # Contract: connected cached clients are reused, concurrent first connects
    # share a single connect attempt, disconnected WebSocket clients reconnect,
    # and disconnected non-WebSocket clients are returned without reconnect.
    class FakeRemoteClient:
        def __init__(self, name: str, disconnected: bool = False) -> None:
            self.name = name
            self.disconnected = disconnected

        def is_disconnected(self) -> bool:
            return self.disconnected

    async def run() -> tuple[list[str], bool, str, str, str]:
        calls: list[str] = []
        next_clients = [FakeRemoteClient("first"), FakeRemoteClient("second")]

        async def fake_connect(cls, transport_params, **_kwargs):
            calls.append(transport_params.websocket_url or transport_params.kind.value)
            await asyncio.sleep(0)
            return next_clients.pop(0)

        monkeypatch.setattr(
            ExecServerClient,
            "connect_for_transport",
            classmethod(fake_connect),
        )

        websocket_transport = ExecServerTransportParams.from_websocket_url("ws://remote.test")
        lazy = LazyRemoteExecServerClient(websocket_transport)
        first, also_first = await asyncio.gather(lazy.get(), lazy.get())
        first.disconnected = True
        reconnected = await lazy.get()

        stdio_transport = ExecServerTransportParams.stdio_command(StdioExecServerCommand(program="server"))
        disconnected_stdio = FakeRemoteClient("stdio-cached", disconnected=True)
        stdio_lazy = LazyRemoteExecServerClient(stdio_transport, client=disconnected_stdio)
        stdio_result = await stdio_lazy.get()

        return calls, first is also_first, first.name, reconnected.name, stdio_result.name

    calls, shared_first, first_name, reconnected_name, stdio_name = asyncio.run(run())

    assert calls == ["ws://remote.test", "ws://remote.test"]
    assert shared_first is True
    assert first_name == "first"
    assert reconnected_name == "second"
    assert stdio_name == "stdio-cached"


def test_lazy_remote_exec_server_client_http_methods_forward_after_get(monkeypatch: pytest.MonkeyPatch) -> None:
    # Rust crate/module:
    # codex-exec-server/src/client.rs::impl HttpClient for LazyRemoteExecServerClient.
    # Contract: HTTP helpers lazily obtain the remote client and delegate the
    # buffered/streamed request to the connected client.
    class FakeRemoteClient:
        def __init__(self) -> None:
            self.calls: list[tuple[str, HttpRequestParams]] = []

        def is_disconnected(self) -> bool:
            return False

        async def http_request(self, params: HttpRequestParams) -> HttpRequestResponse:
            self.calls.append(("buffered", params))
            return HttpRequestResponse(status=204, headers=[HttpHeader("x-test", "ok")], body=ByteChunk(b"body"))

        async def http_request_stream(self, params: HttpRequestParams) -> tuple[HttpRequestResponse, str]:
            self.calls.append(("stream", params))
            return HttpRequestResponse(status=200, headers=[], body=ByteChunk(b"")), "stream-body"

    async def run() -> tuple[HttpRequestResponse, tuple[HttpRequestResponse, str], list[tuple[str, HttpRequestParams]]]:
        remote_client = FakeRemoteClient()
        connect_count = 0

        async def fake_connect(cls, transport_params, **_kwargs):
            nonlocal connect_count
            connect_count += 1
            return remote_client

        monkeypatch.setattr(
            ExecServerClient,
            "connect_for_transport",
            classmethod(fake_connect),
        )

        lazy = LazyRemoteExecServerClient(ExecServerTransportParams.from_websocket_url("ws://remote.test"))
        params = HttpRequestParams(
            method="GET",
            url="https://example.test",
            headers=[],
            request_id="req-1",
        )
        buffered = await lazy.http_request(params)
        streamed = await lazy.http_request_stream(params)
        assert connect_count == 1
        return buffered, streamed, remote_client.calls

    buffered, streamed, calls = asyncio.run(run())

    assert buffered == HttpRequestResponse(
        status=204,
        headers=[HttpHeader("x-test", "ok")],
        body=ByteChunk(b"body"),
    )
    assert streamed[1] == "stream-body"
    assert [kind for kind, _params in calls] == ["buffered", "stream"]
