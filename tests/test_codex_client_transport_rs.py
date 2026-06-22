"""Rust-derived tests for ``codex-client/src/transport.rs``.

Rust crate: ``codex-client``
Rust module: ``src/transport.rs``

Behavior contract:
- expose ByteStream, StreamResponse, and HttpTransport public shapes;
- mirror request body trace formatting;
- map timeout/network errors;
- prepare requests through ``Request.prepare_body_for_send``;
- map non-success unary/stream responses to ``TransportError::Http``.
"""

from __future__ import annotations

import asyncio
import threading
import unittest
import socket
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

from pycodex.codex_client import HttpTransport
from pycodex.codex_client import CODEX_CA_CERT_ENV
from pycodex.codex_client import MapEnv
from pycodex.codex_client import Request
from pycodex.codex_client import RequestCompression
from pycodex.codex_client import ReqwestTransport
from pycodex.codex_client import StreamResponse
from pycodex.codex_client import TransportError
from pycodex.codex_client import TransportHttpResponse
from pycodex.codex_client import request_body_for_trace

TEST_CA = "codex/codex-rs/codex-client/tests/fixtures/test-ca.pem"


class TimeoutLikeError(Exception):
    def is_timeout(self) -> bool:
        return True


class FakeResponse:
    def __init__(self, status=200, headers=None, body=b""):
        self.status = status
        self._headers = headers or [("x-fake", "1")]
        self._body = body
        self._offset = 0

    def getheaders(self):
        return self._headers

    def read(self, size=-1):
        if size is None or size < 0:
            chunk = self._body[self._offset :]
            self._offset = len(self._body)
            return chunk
        chunk = self._body[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


class TimeoutDuringStreamResponse(FakeResponse):
    def __init__(self):
        super().__init__(status=200, headers=[("x-stream", "1")], body=b"")
        self.read_count = 0

    def read(self, size=-1):
        self.read_count += 1
        if self.read_count == 1:
            return b"first"
        raise socket.timeout("late stream")


class ErrorDuringStreamResponse(FakeResponse):
    def __init__(self):
        super().__init__(status=200, headers=[("x-stream", "1")], body=b"")
        self.read_count = 0

    def read(self, size=-1):
        self.read_count += 1
        if self.read_count == 1:
            return b"first"
        raise RuntimeError("stream reset")


class ErrorDuringHttpBodyReadResponse(FakeResponse):
    def __init__(self):
        super().__init__(status=503, headers=[("retry-after", "2")], body=b"")

    def read(self, size=-1):
        raise RuntimeError("body dropped")


class TimeoutDuringHttpBodyReadResponse(FakeResponse):
    def __init__(self):
        super().__init__(status=503, headers=[("retry-after", "2")], body=b"")

    def read(self, size=-1):
        raise socket.timeout("body timed out")


class TimeoutDuringStreamHttpBodyReadResponse(FakeResponse):
    def __init__(self):
        super().__init__(status=429, headers=[("retry-after", "7")], body=b"")

    def read(self, size=-1):
        raise socket.timeout("stream body timed out")


class ErrorDuringSuccessBodyReadResponse(FakeResponse):
    def __init__(self):
        super().__init__(status=200, headers=[("x-ok", "1")], body=b"")

    def read(self, size=-1):
        raise RuntimeError("body reset")


class FakeConnection:
    def __init__(self, response):
        self.response = response
        self.requests = []
        self.closed = False

    def request(self, method, path, body=None, headers=None):
        self.requests.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "headers": dict(headers or {}),
            }
        )

    def getresponse(self):
        return self.response

    def close(self):
        self.closed = True


class TimeoutBeforeResponseConnection(FakeConnection):
    def __init__(self):
        super().__init__(FakeResponse())

    def getresponse(self):
        raise socket.timeout("connect timed out")


class ErrorBeforeResponseConnection(FakeConnection):
    def __init__(self):
        super().__init__(FakeResponse())

    def getresponse(self):
        raise RuntimeError("connection reset before headers")


class _RecordedRequestHandler(BaseHTTPRequestHandler):
    def do_POST(self):  # noqa: N802 - stdlib handler hook name
        length = int(self.headers.get("content-length", "0"))
        body = self.rfile.read(length)
        self.server.recorded.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": body,
            }
        )
        self.send_response(200)
        self.send_header("x-id", "42")
        self.send_header("content-length", "7")
        self.end_headers()
        self.wfile.write(b"created")
        self.wfile.flush()

    def do_GET(self):  # noqa: N802 - stdlib handler hook name
        self.server.recorded.append(
            {
                "method": self.command,
                "path": self.path,
                "headers": dict(self.headers.items()),
                "body": b"",
            }
        )
        self.send_response(200)
        self.send_header("x-stream", "1")
        self.send_header("content-length", "9")
        self.end_headers()
        self.wfile.write(b"alpha")
        self.wfile.flush()
        self.wfile.write(b"beta")

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return


class LocalHttpServer:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _RecordedRequestHandler)
        self.server.recorded = []
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    @property
    def url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def recorded(self):
        return self.server.recorded


def _header(headers: dict[str, str], name: str) -> str:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    raise KeyError(name)


class CodexClientTransportRsTests(unittest.TestCase):
    def test_request_body_for_trace_matches_rust_branches(self) -> None:
        self.assertEqual(
            request_body_for_trace(
                Request.new("POST", "https://example.test").with_json({"model": "m"})
            ),
            '{"model":"m"}',
        )
        self.assertEqual(
            request_body_for_trace(
                Request.new("POST", "https://example.test").with_raw_body(b"abc")
            ),
            "<raw body: 3 bytes>",
        )
        self.assertEqual(
            request_body_for_trace(Request.new("GET", "https://example.test")),
            "",
        )

    def test_reqwest_transport_build_prepares_headers_body_and_timeout(self) -> None:
        transport = ReqwestTransport(lambda _prepared: TransportHttpResponse(200, {}, b"ok"))
        request = (
            Request.new("POST", "https://example.test")
            .with_json({"model": "m"})
            .with_headers({"x-test": "1"})
        )
        request = Request(
            request.method,
            request.url,
            request.headers,
            request.body,
            request.compression,
            timeout=2.5,
        )

        prepared = transport.build(request)

        self.assertEqual(prepared.method, "POST")
        self.assertEqual(prepared.url, "https://example.test")
        self.assertEqual(prepared.headers["x-test"], "1")
        self.assertEqual(prepared.headers["content-type"], "application/json")
        self.assertEqual(prepared.body, b'{"model":"m"}')
        self.assertEqual(prepared.timeout, 2.5)

    def test_reqwest_transport_build_preserves_valid_extension_methods(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: build() uses Method::from_bytes(method.as_str().as_bytes())
        # and therefore preserves valid extension method tokens.
        transport = ReqwestTransport(lambda _prepared: TransportHttpResponse(200, {}, b"ok"))

        prepared = transport.build(Request.new("PROPFIND", "https://example.test/dav"))

        self.assertEqual(prepared.method, "PROPFIND")

    def test_reqwest_transport_build_preserves_valid_method_token_case(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: Method::from_bytes(method.as_str().as_bytes()) validates
        # the original method token and does not uppercase valid extension
        # tokens before handing them to the request builder.
        transport = ReqwestTransport(lambda _prepared: TransportHttpResponse(200, {}, b"ok"))

        prepared = transport.build(Request.new("x-custom+method", "https://example.test/ext"))

        self.assertEqual(prepared.method, "x-custom+method")

    def test_reqwest_transport_build_falls_back_to_get_for_invalid_method_tokens(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: invalid Method::from_bytes results use unwrap_or(Method::GET).
        transport = ReqwestTransport(lambda _prepared: TransportHttpResponse(200, {}, b"ok"))

        prepared = transport.build(Request.new("bad method", "https://example.test"))

        self.assertEqual(prepared.method, "GET")

    def test_reqwest_transport_build_maps_prepare_error_to_build_error(self) -> None:
        transport = ReqwestTransport(lambda _prepared: TransportHttpResponse(200, {}, b"ok"))
        request = (
            Request.new("POST", "https://example.test")
            .with_raw_body(b"abc")
            .with_compression(RequestCompression.ZSTD)
        )

        with self.assertRaisesRegex(
            TransportError, "request build error: request compression cannot be used"
        ):
            transport.build(request)

    def test_map_error_distinguishes_timeout_from_network(self) -> None:
        self.assertEqual(str(ReqwestTransport.map_error(TimeoutLikeError("late"))), "timeout")
        self.assertEqual(
            str(ReqwestTransport.map_error(RuntimeError("reset"))),
            "network error: reset",
        )

    def test_execute_returns_response_on_success(self) -> None:
        seen = []

        def sender(prepared):
            seen.append(prepared)
            return TransportHttpResponse(201, {"x-id": "1"}, b"created")

        transport = ReqwestTransport(sender)
        response = transport.execute(Request.new("POST", "https://example.test"))

        self.assertIsInstance(transport, HttpTransport)
        self.assertEqual(response.status, 201)
        self.assertEqual(response.headers, {"x-id": "1"})
        self.assertEqual(response.body, b"created")
        self.assertEqual(seen[0].method, "POST")

    def test_execute_emits_trace_message_before_send(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() traces "METHOD to URL: BODY" before sending.
        messages = []
        sent = []

        def sender(prepared):
            sent.append(prepared)
            return TransportHttpResponse(200, {}, b"ok")

        transport = ReqwestTransport(sender, trace_logger=messages.append)
        request = Request.new("POST", "https://example.test/trace").with_json({"model": "m"})

        transport.execute(request)

        self.assertEqual(messages, ['POST to https://example.test/trace: {"model":"m"}'])
        self.assertEqual(len(sent), 1)

    def test_execute_and_stream_trace_before_build_error(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute()/stream() call trace! before self.build(req), so
        # request-body trace formatting is still emitted when
        # Request::prepare_body_for_send fails.
        calls = []

        def sender(_prepared):
            calls.append("sent")
            return TransportHttpResponse(200, {}, b"ok")

        for method_name in ("execute", "stream"):
            with self.subTest(method_name=method_name):
                messages = []
                transport = ReqwestTransport(sender, trace_logger=messages.append)
                request = (
                    Request.new("POST", f"https://example.test/{method_name}")
                    .with_raw_body(b"abc")
                    .with_compression(RequestCompression.ZSTD)
                )

                with self.assertRaisesRegex(
                    TransportError, "request build error: request compression cannot be used"
                ):
                    getattr(transport, method_name)(request)

                self.assertEqual(
                    messages,
                    [f"POST to https://example.test/{method_name}: <raw body: 3 bytes>"],
                )

        self.assertEqual(calls, [])

    def test_async_execute_and_stream_facades_preserve_rust_transport_contracts(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: HttpTransport::execute and HttpTransport::stream are async
        # trait methods in Rust. Python keeps the dependency-light sync sender
        # and exposes async facades that delegate through the same
        # trace/build/send/status/error behavior.
        messages = []
        calls = []

        def sender(prepared):
            calls.append(prepared.method)
            return TransportHttpResponse(
                200,
                {"x-async": "1"},
                b"ok",
                stream=[b"a", b"b"],
            )

        async def run_contract():
            transport = ReqwestTransport(sender, trace_logger=messages.append)
            response = await transport.execute_async(
                Request.new("POST", "https://example.test/async").with_raw_body(b"hi")
            )
            stream = await transport.stream_async(
                Request.new("GET", "https://example.test/async-stream")
            )
            return response, list(stream.bytes)

        response, chunks = asyncio.run(run_contract())

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers, {"x-async": "1"})
        self.assertEqual(response.body, b"ok")
        self.assertEqual(chunks, [b"a", b"b"])
        self.assertEqual(calls, ["POST", "GET"])
        self.assertEqual(
            messages,
            [
                "POST to https://example.test/async: <raw body: 2 bytes>",
                "GET to https://example.test/async-stream: ",
            ],
        )

    def test_execute_maps_non_success_response_to_http_error(self) -> None:
        transport = ReqwestTransport(
            lambda _prepared: TransportHttpResponse(
                500, {"retry-after": "1"}, b"server down"
            )
        )

        with self.assertRaises(TransportError) as caught:
            transport.execute(Request.new("GET", "https://example.test/fail"))

        err = caught.exception
        self.assertEqual(err.kind, "http")
        self.assertEqual(err.status, 500)
        self.assertEqual(err.url, "https://example.test/fail")
        self.assertEqual(err.headers, {"retry-after": "1"})
        self.assertEqual(err.body, "server down")

    def test_execute_non_success_invalid_utf8_body_is_none(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() maps non-success bodies through
        # String::from_utf8(bytes.to_vec()).ok(), so invalid UTF-8 preserves
        # the HTTP error but clears the optional body.
        transport = ReqwestTransport(
            lambda _prepared: TransportHttpResponse(500, {"x": "bad"}, b"\xff")
        )

        with self.assertRaises(TransportError) as caught:
            transport.execute(Request.new("GET", "https://example.test/bad-utf8"))

        err = caught.exception
        self.assertEqual(err.kind, "http")
        self.assertEqual(err.status, 500)
        self.assertEqual(err.url, "https://example.test/bad-utf8")
        self.assertEqual(err.headers, {"x": "bad"})
        self.assertIsNone(err.body)

    def test_stream_returns_stream_response_on_success(self) -> None:
        stream = [b"a", b"b"]
        transport = ReqwestTransport(
            lambda _prepared: TransportHttpResponse(200, {"x-stream": "1"}, b"", stream)
        )

        response = transport.stream(Request.new("GET", "https://example.test/stream"))

        self.assertIsInstance(response, StreamResponse)
        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers, {"x-stream": "1"})
        self.assertEqual(list(response.bytes), [b"a", b"b"])

    def test_stream_success_without_body_chunks_returns_empty_byte_stream(self) -> None:
        # Rust source: codex-client/src/transport.rs
        # Contract: ByteStream items are Result<Bytes, TransportError>; a
        # successful stream with no body chunks must not yield None or b"".
        for body in (None, b""):
            with self.subTest(body=body):
                transport = ReqwestTransport(
                    lambda _prepared, body=body: TransportHttpResponse(
                        200, {"x-stream": "1"}, body
                    )
                )

                response = transport.stream(Request.new("GET", "https://example.test/empty"))

                self.assertEqual(response.status, 200)
                self.assertEqual(response.headers, {"x-stream": "1"})
                self.assertEqual(list(response.bytes), [])

    def test_stream_emits_trace_message_before_send(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: stream() uses the same trace body formatting as execute().
        messages = []
        stream = [b"a"]
        transport = ReqwestTransport(
            lambda _prepared: TransportHttpResponse(200, {}, b"", stream),
            trace_logger=messages.append,
        )

        transport.stream(Request.new("GET", "https://example.test/stream"))

        self.assertEqual(messages, ["GET to https://example.test/stream: "])

    def test_stream_maps_non_success_response_to_http_error(self) -> None:
        transport = ReqwestTransport(
            lambda _prepared: TransportHttpResponse(404, {"x": "y"}, b"missing")
        )

        with self.assertRaisesRegex(TransportError, "http 404: 'missing'"):
            transport.stream(Request.new("GET", "https://example.test/missing"))

    def test_stream_non_success_invalid_utf8_body_is_lossy_text(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: stream() uses resp.text().await.ok() for non-success
        # responses. reqwest Response::text decodes malformed UTF-8 with
        # replacement characters rather than clearing the body.
        transport = ReqwestTransport(
            lambda _prepared: TransportHttpResponse(404, {"x": "y"}, b"a\xffb")
        )

        with self.assertRaises(TransportError) as caught:
            transport.stream(Request.new("GET", "https://example.test/lossy"))

        err = caught.exception
        self.assertEqual(err.kind, "http")
        self.assertEqual(err.status, 404)
        self.assertEqual(err.url, "https://example.test/lossy")
        self.assertEqual(err.headers, {"x": "y"})
        self.assertEqual(err.body, "a\ufffdb")

    def test_default_transport_executes_real_http_request_with_stdlib_sender(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: ReqwestTransport performs a real HTTP send after the same
        # build/body/header preparation path used by injected-sender tests.
        with LocalHttpServer() as server:
            request = (
                Request.new("POST", f"{server.url}/submit")
                .with_json({"model": "m"})
                .with_headers({"x-test": "1"})
            )

            response = ReqwestTransport().execute(request)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["x-id"], "42")
        self.assertEqual(server.recorded[0]["method"], "POST")
        self.assertEqual(server.recorded[0]["path"], "/submit")
        self.assertEqual(server.recorded[0]["body"], b'{"model":"m"}')
        self.assertEqual(_header(server.recorded[0]["headers"], "x-test"), "1")
        self.assertEqual(_header(server.recorded[0]["headers"], "content-type"), "application/json")

    def test_default_transport_execute_reads_real_http_response_body(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() reads successful response bytes from the real
        # HTTP response path.
        with LocalHttpServer() as server:
            response = ReqwestTransport().execute(Request.new("GET", f"{server.url}/body"))

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["x-stream"], "1")
        self.assertEqual(response.body, b"alphabeta")
        self.assertEqual(server.recorded[0]["method"], "GET")

    def test_default_transport_streams_real_http_response_with_stdlib_sender(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: stream() returns a StreamResponse whose byte iterator is
        # backed by the real HTTP response body.
        with LocalHttpServer() as server:
            response = ReqwestTransport().stream(Request.new("GET", f"{server.url}/stream"))
            body = b"".join(response.bytes)

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["x-stream"], "1")
        self.assertEqual(body, b"alphabeta")
        self.assertEqual(server.recorded[0]["method"], "GET")
        self.assertEqual(server.recorded[0]["path"], "/stream")

    def test_stdlib_sender_request_target_preserves_path_and_query_only(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: ReqwestTransport hands the request URL to reqwest; the
        # HTTP request target uses path + query, defaults an empty path to
        # "/", and never sends the URL fragment.
        fake = FakeConnection(FakeResponse(body=b"ok"))

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        response = transport.execute(
            Request.new("GET", "http://localhost:8000/search?q=codex#ignored")
        )

        self.assertEqual(response.body, b"ok")
        self.assertEqual(fake.requests[0]["path"], "/search?q=codex")

        root_fake = FakeConnection(FakeResponse(body=b"root"))

        def root_factory(scheme, host, port, timeout, context):
            return root_fake

        root_response = ReqwestTransport(connection_factory=root_factory).execute(
            Request.new("GET", "http://localhost:8000?ready=1#fragment")
        )

        self.assertEqual(root_response.body, b"root")
        self.assertEqual(root_fake.requests[0]["path"], "/?ready=1")

    def test_stream_body_read_timeout_maps_to_timeout_error_item(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: bytes_stream().map(Self::map_error) maps timeout errors
        # raised while reading stream chunks to TransportError::Timeout.
        fake = FakeConnection(TimeoutDuringStreamResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        response = ReqwestTransport(connection_factory=factory).stream(
            Request.new("GET", "http://localhost:8000/events")
        )

        chunks = list(response.bytes)

        self.assertEqual(chunks[0], b"first")
        self.assertIsInstance(chunks[1], TransportError)
        self.assertEqual(str(chunks[1]), "timeout")
        self.assertTrue(fake.closed)

    def test_stream_body_read_error_maps_to_network_error_item(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: bytes_stream().map(Self::map_error) maps non-timeout
        # chunk-read failures to TransportError::Network stream items.
        fake = FakeConnection(ErrorDuringStreamResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        response = ReqwestTransport(connection_factory=factory).stream(
            Request.new("GET", "http://localhost:8000/events")
        )

        chunks = list(response.bytes)

        self.assertEqual(chunks[0], b"first")
        self.assertIsInstance(chunks[1], TransportError)
        self.assertEqual(chunks[1].kind, "network")
        self.assertEqual(str(chunks[1]), "network error: stream reset")
        self.assertTrue(fake.closed)

    def test_stream_non_success_body_read_error_still_returns_http_error(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: stream() uses resp.text().await.ok() for non-success
        # responses, so a body-read failure clears body without replacing the
        # HTTP status error with a network error.
        fake = FakeConnection(ErrorDuringHttpBodyReadResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.stream(Request.new("GET", "http://localhost:8000/unavailable"))

        err = caught.exception
        self.assertEqual(err.kind, "http")
        self.assertEqual(err.status, 503)
        self.assertEqual(err.url, "http://localhost:8000/unavailable")
        self.assertEqual(err.headers, {"retry-after": "2"})
        self.assertIsNone(err.body)
        self.assertTrue(fake.closed)

    def test_stream_non_success_body_read_timeout_still_returns_http_error(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: stream() uses resp.text().await.ok() for non-success
        # responses, so even a body-read timeout clears body without replacing
        # the HTTP status error with TransportError::Timeout.
        fake = FakeConnection(TimeoutDuringStreamHttpBodyReadResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.stream(Request.new("GET", "http://localhost:8000/rate-limited"))

        err = caught.exception
        self.assertEqual(err.kind, "http")
        self.assertEqual(err.status, 429)
        self.assertEqual(err.url, "http://localhost:8000/rate-limited")
        self.assertEqual(err.headers, {"retry-after": "7"})
        self.assertIsNone(err.body)
        self.assertTrue(fake.closed)

    def test_execute_non_success_body_read_timeout_maps_to_timeout_before_status(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() awaits resp.bytes().map_err(Self::map_error)
        # before checking status, so a body-read timeout returns
        # TransportError::Timeout instead of TransportError::Http.
        fake = FakeConnection(TimeoutDuringHttpBodyReadResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.execute(Request.new("GET", "http://localhost:8000/unavailable"))

        err = caught.exception
        self.assertEqual(err.kind, "timeout")
        self.assertEqual(str(err), "timeout")
        self.assertTrue(fake.closed)

    def test_execute_non_success_body_read_error_maps_to_network_before_status(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() awaits resp.bytes().map_err(Self::map_error)
        # before checking status, so a non-timeout body-read failure returns
        # TransportError::Network instead of the HTTP status error.
        fake = FakeConnection(ErrorDuringHttpBodyReadResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.execute(Request.new("GET", "http://localhost:8000/unavailable"))

        err = caught.exception
        self.assertEqual(err.kind, "network")
        self.assertEqual(str(err), "network error: body dropped")
        self.assertTrue(fake.closed)

    def test_execute_success_body_read_error_maps_to_network_before_response(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() awaits resp.bytes().map_err(Self::map_error)
        # before returning a Response, so a successful-status body-read
        # failure becomes TransportError::Network rather than an empty body.
        fake = FakeConnection(ErrorDuringSuccessBodyReadResponse())

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.execute(Request.new("GET", "http://localhost:8000/body-reset"))

        err = caught.exception
        self.assertEqual(err.kind, "network")
        self.assertEqual(str(err), "network error: body reset")
        self.assertTrue(fake.closed)

    def test_execute_send_timeout_before_response_maps_to_timeout(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: execute() maps builder.send().await failures through
        # ReqwestTransport::map_error before any response status/header/body
        # handling, so a timeout while sending/receiving headers returns
        # TransportError::Timeout.
        fake = TimeoutBeforeResponseConnection()

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.execute(Request.new("GET", "http://localhost:8000/connect-timeout"))

        err = caught.exception
        self.assertEqual(err.kind, "timeout")
        self.assertEqual(str(err), "timeout")
        self.assertTrue(fake.closed)

    def test_stream_send_error_before_response_maps_to_network(self) -> None:
        # Rust crate/module: codex-client/src/transport.rs
        # Contract: stream() uses the same builder.send().await.map_err()
        # boundary as execute(); non-timeout send failures become
        # TransportError::Network before a StreamResponse can be created.
        fake = ErrorBeforeResponseConnection()

        def factory(scheme, host, port, timeout, context):
            return fake

        transport = ReqwestTransport(connection_factory=factory)

        with self.assertRaises(TransportError) as caught:
            transport.stream(Request.new("GET", "http://localhost:8000/reset-before-headers"))

        err = caught.exception
        self.assertEqual(err.kind, "network")
        self.assertEqual(str(err), "network error: connection reset before headers")
        self.assertTrue(fake.closed)

    def test_https_transport_uses_custom_ca_env_for_ssl_context(self) -> None:
        # Rust crates/modules: codex-client/src/transport.rs with dependency
        # constraint from codex-client/src/custom_ca.rs.
        # Contract: HTTPS stdlib transport honors the selected custom CA bundle
        # before opening the connection.
        captured = {}
        fake = FakeConnection(FakeResponse(body=b"secure"))

        def factory(scheme, host, port, timeout, context):
            captured.update(
                {
                    "scheme": scheme,
                    "host": host,
                    "port": port,
                    "timeout": timeout,
                    "context": context,
                }
            )
            return fake

        transport = ReqwestTransport(
            env_source=MapEnv({CODEX_CA_CERT_ENV: TEST_CA}),
            connection_factory=factory,
        )

        response = transport.execute(Request.new("GET", "https://localhost:9443/secure"))

        self.assertEqual(response.body, b"secure")
        self.assertEqual(captured["scheme"], "https")
        self.assertEqual(captured["host"], "localhost")
        self.assertEqual(captured["port"], 9443)
        self.assertIsNotNone(captured["context"])
        self.assertEqual(fake.requests[0]["path"], "/secure")


if __name__ == "__main__":
    unittest.main()
