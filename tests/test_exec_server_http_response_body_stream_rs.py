from __future__ import annotations

import asyncio
import gc

import pytest

from pycodex.app_server_protocol import JSONRPCMessage, JSONRPCNotification
from pycodex.exec_server import (
    HTTP_REQUEST_BODY_DELTA_METHOD,
    ByteChunk,
    ExecServerClient,
    ExecServerClientConnectOptions,
    ExecServerError,
    HttpRequestBodyDeltaNotification,
    HttpResponseBodyStream,
    JsonRpcConnection,
    encode_http_request_body_delta_notification,
)


class FakeConnection(JsonRpcConnection):
    def __init__(self) -> None:
        super().__init__(
            outgoing_tx=asyncio.Queue(),
            incoming_rx=asyncio.Queue(),
            disconnected=asyncio.Event(),
            task_handles=[],
        )


def _client() -> ExecServerClient:
    return ExecServerClient(
        FakeConnection(),
        ExecServerClientConnectOptions(),
        session_id="session-1",
        start_reader=False,
    )


def _delta(request_id: str, seq: int, data: bytes, *, done: bool = False, error: str | None = None):
    return encode_http_request_body_delta_notification(
        HttpRequestBodyDeltaNotification(
            request_id=request_id,
            seq=seq,
            delta=ByteChunk(data),
            done=done,
            error=error,
        )
    )


async def _registered_stream(client: ExecServerClient, request_id: str = "http-1") -> HttpResponseBodyStream:
    queue: asyncio.Queue[HttpRequestBodyDeltaNotification | None] = asyncio.Queue(maxsize=256)
    await client.insert_http_body_stream(request_id, queue)
    return HttpResponseBodyStream.remote(client, request_id, queue)


def test_remote_http_response_body_stream_yields_chunk_then_eof() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client/http_response_body_stream.rs::HttpResponseBodyStream::recv.
    # Contract: a done delta with a non-empty chunk returns the chunk first and
    # EOF on the next recv, removing the request route.
    async def run() -> tuple[bytes | None, bytes | None, bool]:
        client = _client()
        stream = await _registered_stream(client)
        await client.handle_http_body_delta_notification(_delta("http-1", 1, b"hello", done=True))
        first = await stream.recv()
        second = await stream.recv()
        return first, second, "http-1" in client.http_body_streams

    assert asyncio.run(run()) == (b"hello", None, False)


def test_remote_http_response_body_stream_empty_done_is_immediate_eof() -> None:
    # Rust contract: a terminal done delta with no bytes returns EOF directly.
    async def run() -> bytes | None:
        client = _client()
        stream = await _registered_stream(client)
        await client.handle_http_body_delta_notification(_delta("http-1", 1, b"", done=True))
        return await stream.recv()

    assert asyncio.run(run()) is None


def test_remote_http_response_body_stream_rejects_sequence_gap() -> None:
    # Rust contract: remote streams require contiguous sequence numbers.
    async def run() -> str:
        client = _client()
        stream = await _registered_stream(client)
        await client.handle_http_body_delta_notification(_delta("http-1", 2, b"late"))
        with pytest.raises(ExecServerError) as exc_info:
            await stream.recv()
        return str(exc_info.value)

    assert asyncio.run(run()) == (
        "exec-server protocol error: http response stream `http-1` received seq 2, expected 1"
    )


def test_remote_http_response_body_stream_error_delta_fails() -> None:
    # Rust contract: stream-side terminal errors become protocol errors with
    # the request id and original error text.
    async def run() -> str:
        client = _client()
        stream = await _registered_stream(client)
        await client.handle_http_body_delta_notification(
            _delta("http-1", 1, b"", done=True, error="upstream reset")
        )
        with pytest.raises(ExecServerError) as exc_info:
            await stream.recv()
        return str(exc_info.value)

    assert asyncio.run(run()) == (
        "exec-server protocol error: http response stream `http-1` failed: upstream reset"
    )


def test_unknown_http_body_delta_request_id_is_ignored() -> None:
    # Rust contract: body deltas for unknown request ids are ignored because a
    # stream may have already reached EOF and released its route.
    async def run() -> dict[str, object]:
        client = _client()
        await client.handle_http_body_delta_notification(_delta("missing", 1, b"ignored"))
        return dict(client.http_body_streams)

    assert asyncio.run(run()) == {}


def test_stream_drop_schedules_route_removal() -> None:
    # Rust contract: dropping a remote stream before EOF schedules request-route
    # removal from the synchronous drop path.
    async def run() -> bool:
        client = _client()
        stream = await _registered_stream(client)
        assert "http-1" in client.http_body_streams
        del stream
        gc.collect()
        await asyncio.sleep(0)
        return "http-1" in client.http_body_streams

    assert asyncio.run(run()) is False


def test_fail_all_http_body_streams_delivers_terminal_error() -> None:
    # Rust contract: active streamed HTTP bodies are failed when the transport
    # disconnects so callers do not wait forever.
    async def run() -> str:
        client = _client()
        stream = await _registered_stream(client)
        await client.fail_all_http_body_streams("transport closed")
        with pytest.raises(ExecServerError) as exc_info:
            await stream.recv()
        return str(exc_info.value)

    assert asyncio.run(run()) == (
        "exec-server protocol error: http response stream `http-1` failed: transport closed"
    )


def test_reader_loop_routes_http_body_delta_notifications() -> None:
    # Rust integration contract: `http/request/bodyDelta` notifications on the
    # shared connection are routed into the matching request-local stream.
    async def run() -> bytes | None:
        client = ExecServerClient(
            FakeConnection(),
            ExecServerClientConnectOptions(),
            session_id="session-1",
        )
        stream = await _registered_stream(client)
        await client.connection.incoming_rx.put(
            JsonRpcConnectionEvent_message(
                HTTP_REQUEST_BODY_DELTA_METHOD,
                _delta("http-1", 1, b"via-reader", done=True),
            )
        )
        chunk = await asyncio.wait_for(stream.recv(), timeout=1)
        client.reader_task.cancel()
        await asyncio.gather(client.reader_task, return_exceptions=True)
        return chunk

    assert asyncio.run(run()) == b"via-reader"


def JsonRpcConnectionEvent_message(method: str, params: dict[str, object]):
    from pycodex.exec_server import JsonRpcConnectionEvent

    return JsonRpcConnectionEvent.message_event(
        JSONRPCMessage(JSONRPCNotification(method=method, params=params))
    )
