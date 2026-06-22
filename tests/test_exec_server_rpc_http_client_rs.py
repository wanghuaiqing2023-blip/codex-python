from __future__ import annotations

import asyncio

import pytest

from pycodex.exec_server import (
    HTTP_BODY_DELTA_CHANNEL_CAPACITY,
    HTTP_REQUEST_METHOD,
    ByteChunk,
    ExecServerClient,
    ExecServerClientConnectOptions,
    ExecServerError,
    HttpHeader,
    HttpRequestParams,
    HttpRequestResponse,
    HttpResponseBodyStream,
    JsonRpcConnection,
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


def _params(*, request_id: str = "caller-id", stream_response: bool = True) -> HttpRequestParams:
    return HttpRequestParams(
        method="POST",
        url="https://example.test/path",
        headers=[HttpHeader("x-test", "1")],
        request_id=request_id,
        body=ByteChunk(b"body"),
        timeout_ms=123,
        stream_response=stream_response,
    )


def _response() -> HttpRequestResponse:
    return HttpRequestResponse(
        status=200,
        headers=[HttpHeader("content-type", "text/plain")],
        body=ByteChunk(b"ok"),
    )


def test_http_request_forces_buffered_response() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client/rpc_http_client.rs::ExecServerClient::http_request.
    # Contract: buffered HTTP requests force stream_response=false and forward
    # the request through the shared `http/request` JSON-RPC method.
    async def run():
        client = _client()
        calls = []

        async def call_impl(method, params):
            calls.append((method, params))
            return _response()

        client.call_impl = call_impl
        response = await client.http_request(_params(stream_response=True))
        return response, calls

    response, calls = asyncio.run(run())

    assert response == _response()
    assert len(calls) == 1
    method, params = calls[0]
    assert method == HTTP_REQUEST_METHOD
    assert params.stream_response is False
    assert params.request_id == "caller-id"


def test_http_request_stream_allocates_request_id_and_registers_stream() -> None:
    # Rust crate/module:
    # codex-exec-server/src/client/rpc_http_client.rs::ExecServerClient::http_request_stream.
    # Contract: streamed requests allocate a connection-local request id,
    # replace any caller-supplied request id, register a body stream route
    # before issuing `http/request`, and return the remote body stream.
    async def run():
        client = _client()
        calls = []

        async def call_impl(method, params):
            calls.append((method, params, dict(client.http_body_streams)))
            return _response()

        client.call_impl = call_impl
        response, stream = await client.http_request_stream(_params(request_id="caller", stream_response=False))
        return response, stream, calls, dict(client.http_body_streams)

    response, stream, calls, streams = asyncio.run(run())

    assert response == _response()
    assert isinstance(stream, HttpResponseBodyStream)
    assert len(calls) == 1
    method, params, streams_during_call = calls[0]
    assert method == HTTP_REQUEST_METHOD
    assert params.stream_response is True
    assert params.request_id == "http-1"
    assert "http-1" in streams_during_call
    assert "http-1" in streams
    assert stream.request_id == "http-1"


def test_http_request_stream_cleans_registration_on_call_error() -> None:
    # Rust source contract: if the header `http/request` call fails after body
    # stream registration, the request route is removed before the error is
    # returned.
    async def run():
        client = _client()

        async def call_impl(method, params):
            raise ExecServerError.protocol("http failed")

        client.call_impl = call_impl
        with pytest.raises(ExecServerError) as exc_info:
            await client.http_request_stream(_params())
        return str(exc_info.value), dict(client.http_body_streams)

    error, streams = asyncio.run(run())

    assert error == "exec-server protocol error: http failed"
    assert streams == {}


def test_http_request_stream_request_ids_are_connection_local() -> None:
    # Rust source contract: stream request ids are allocated per connection
    # with the `http-N` prefix so late deltas cannot collide with caller ids.
    async def run():
        client = _client()

        async def call_impl(method, params):
            return _response()

        client.call_impl = call_impl
        _, first = await client.http_request_stream(_params(request_id="same"))
        _, second = await client.http_request_stream(_params(request_id="same"))
        return first.request_id, second.request_id

    assert asyncio.run(run()) == ("http-1", "http-2")


def test_http_body_delta_channel_capacity_matches_rust_constant() -> None:
    # Rust module constant: HTTP_BODY_DELTA_CHANNEL_CAPACITY = 256.
    assert HTTP_BODY_DELTA_CHANNEL_CAPACITY == 256
