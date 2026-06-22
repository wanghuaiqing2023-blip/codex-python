from __future__ import annotations

import asyncio
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import threading

import pytest

from pycodex.app_server.error_code import INVALID_PARAMS_ERROR_CODE
from pycodex.app_server_protocol import JSONRPCErrorError
from pycodex.exec_server import (
    ByteChunk,
    HttpHeader,
    HttpRequestBodyDeltaNotification,
    HttpRequestParams,
    ReqwestHttpClient,
    ReqwestHttpRequestRunner,
)


class _CapturedServer:
    def __init__(self, handler_cls: type[BaseHTTPRequestHandler]) -> None:
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_cls)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "_CapturedServer":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"


class _BufferedHandler(BaseHTTPRequestHandler):
    captured: dict[str, object] = {}

    def do_POST(self) -> None:
        content_length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(content_length)
        type(self).captured = {
            "request_line": self.requestline,
            "header": self.headers.get("x-codex-test"),
            "body": body,
        }
        self.send_response(201)
        self.send_header("x-mcp-test", "buffered")
        self.send_header("content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"response-body")

    def log_message(self, *_args: object) -> None:
        pass


class _NotFoundHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(404)
        self.send_header("x-mcp-test", "missing")
        self.end_headers()
        self.wfile.write(b"not-found")

    def log_message(self, *_args: object) -> None:
        pass


class _StreamingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("x-mcp-test", "streaming")
        self.send_header("content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"hello ")
        self.wfile.write(b"world")

    def log_message(self, *_args: object) -> None:
        pass


class _Notifications:
    def __init__(self) -> None:
        self.sent: list[tuple[str, HttpRequestBodyDeltaNotification]] = []

    async def notify(self, method: str, delta: HttpRequestBodyDeltaNotification) -> None:
        self.sent.append((method, delta))


def _params(url: str, *, stream_response: bool = False) -> HttpRequestParams:
    return HttpRequestParams(
        method="POST",
        url=url,
        headers=[HttpHeader("x-codex-test", "buffered")],
        request_id="request-1",
        body=ByteChunk(b"request-body"),
        timeout_ms=5_000,
        stream_response=stream_response,
    )


def _response_header(headers: list[HttpHeader], name: str) -> str | None:
    for header in headers:
        if header.name.lower() == name.lower():
            return header.value
    return None


def test_runner_buffers_response_body_and_sends_request_shape() -> None:
    # Rust integration contract:
    # codex-exec-server/tests/http_request.rs::exec_server_http_request_buffers_response_body,
    # backed by src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::run.
    # A buffered http/request performs the method/url/header/body request and
    # returns status, response headers, and the complete body.
    async def run() -> object:
        with _CapturedServer(_BufferedHandler) as server:
            runner = ReqwestHttpRequestRunner.new(5_000)
            response, pending = await runner.run(_params(f"{server.url}/mcp?case=buffered"))
            return response, pending, dict(_BufferedHandler.captured)

    response, pending, captured = asyncio.run(run())

    assert pending is None
    assert response.status == 201
    assert _response_header(response.headers, "x-mcp-test") == "buffered"
    assert response.body.into_inner() == b"response-body"
    assert captured == {
        "request_line": "POST /mcp?case=buffered HTTP/1.1",
        "header": "buffered",
        "body": b"request-body",
    }


def test_runner_treats_http_error_status_as_response() -> None:
    # Rust source contract: reqwest::Client::send does not fail merely because
    # the HTTP status is 4xx/5xx; status and body are returned to the caller.
    async def run() -> object:
        with _CapturedServer(_NotFoundHandler) as server:
            params = HttpRequestParams("GET", f"{server.url}/missing", [], "request-1")
            runner = ReqwestHttpRequestRunner.new(5_000)
            return await runner.run(params)

    response, pending = asyncio.run(run())

    assert pending is None
    assert response.status == 404
    assert _response_header(response.headers, "x-mcp-test") == "missing"
    assert response.body.into_inner() == b"not-found"


def test_client_stream_returns_empty_header_body_and_local_stream() -> None:
    # Rust integration contract:
    # codex-exec-server/tests/http_request.rs::exec_server_http_request_streams_response_body_notifications.
    # A streamed request returns headers with an empty buffered body; callers
    # consume bytes through HttpResponseBodyStream.
    async def run() -> object:
        with _CapturedServer(_StreamingHandler) as server:
            client = ReqwestHttpClient()
            params = HttpRequestParams("GET", f"{server.url}/mcp?case=streaming", [], "stream-1")
            response, stream = await client.http_request_stream(params)
            chunks: list[bytes] = []
            while True:
                chunk = await stream.recv()
                if chunk is None:
                    break
                chunks.append(chunk)
            return response, b"".join(chunks)

    response, body = asyncio.run(run())

    assert response.status == 200
    assert _response_header(response.headers, "x-mcp-test") == "streaming"
    assert response.body.into_inner() == b""
    assert body == b"hello world"


def test_stream_body_sends_ordered_deltas_and_terminal_frame() -> None:
    # Rust source contract:
    # src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::stream_body.
    # Local pending body chunks are forwarded as 1-based bodyDelta frames with
    # a final empty done=true notification.
    async def run() -> list[tuple[str, HttpRequestBodyDeltaNotification]]:
        with _CapturedServer(_StreamingHandler) as server:
            params = HttpRequestParams(
                "GET",
                f"{server.url}/mcp?case=streaming",
                [],
                "stream-1",
                stream_response=True,
            )
            _response, pending = await ReqwestHttpRequestRunner.new(5_000).run(params)
            notifications = _Notifications()
            assert pending is not None
            await ReqwestHttpRequestRunner.stream_body(pending, notifications)
            return notifications.sent

    sent = asyncio.run(run())

    assert [method for method, _delta in sent] == ["http/request/bodyDelta", "http/request/bodyDelta"]
    deltas = [delta for _method, delta in sent]
    assert [(delta.seq, delta.done, delta.error) for delta in deltas] == [(1, False, None), (2, True, None)]
    assert b"".join(delta.delta.into_inner() for delta in deltas) == b"hello world"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        (
            HttpRequestParams("BAD METHOD", "http://example.test", [], "request-1"),
            "http/request method is invalid:",
        ),
        (
            HttpRequestParams("GET", "file:///tmp/body", [], "request-1"),
            "http/request only supports http and https URLs, got file",
        ),
        (
            HttpRequestParams("GET", "http://example.test", [HttpHeader("bad\nname", "value")], "request-1"),
            "http/request header name is invalid:",
        ),
        (
            HttpRequestParams("GET", "http://example.test", [HttpHeader("x-test", "bad\nvalue")], "request-1"),
            "http/request header value is invalid for x-test:",
        ),
    ],
)
def test_runner_maps_invalid_method_url_and_headers_to_invalid_params(
    params: HttpRequestParams,
    message: str,
) -> None:
    # Rust source contract:
    # src/client/reqwest_http_client.rs::ReqwestHttpRequestRunner::run/build_headers.
    # Invalid methods, unsupported URL schemes, and invalid headers become
    # JSON-RPC invalid_params errors with Rust-shaped messages.
    async def run() -> JSONRPCErrorError:
        result = await ReqwestHttpRequestRunner.new(None).run(params)
        assert isinstance(result, JSONRPCErrorError)
        return result

    error = asyncio.run(run())
    assert error.code == INVALID_PARAMS_ERROR_CODE
    assert error.message.startswith(message)
