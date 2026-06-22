"""Rust-derived tests for ``codex-client/src/default_client.rs``.

Rust crate: ``codex-client``
Rust module: ``src/default_client.rs``

Rust test mirrored:
- ``inject_trace_headers_uses_current_span_context``

Additional behavior contracts are derived from the public builder methods in
``default_client.rs``.
"""

from __future__ import annotations

import asyncio
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from http.server import ThreadingHTTPServer

from pycodex.codex_client import CodexHttpClient
from pycodex.codex_client import CodexRequestBuilder
from pycodex.codex_client import CodexRequestSnapshot
from pycodex.codex_client import TransportError
from pycodex.codex_client import trace_headers


class _DefaultClientHandler(BaseHTTPRequestHandler):
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
        self.send_header("x-default-client", "ok")
        self.send_header("content-length", "0")
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A002 - stdlib signature
        return


class _ResponseLike:
    def __init__(self) -> None:
        self.status = 201
        self.headers = {"x-result": "created"}
        self.version = "HTTP/1.1"


class _ResponseMethodLike:
    def status(self) -> int:
        return 202

    def headers(self) -> dict[str, str]:
        return {"x-method": "accepted"}

    def version(self) -> str:
        return "HTTP/2"


class _StatusMethodError(Exception):
    def status(self) -> int:
        return 429


class LocalHttpServer:
    def __enter__(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _DefaultClientHandler)
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


class CodexClientDefaultClientRsTests(unittest.TestCase):
    def test_client_get_post_and_request_create_builders_with_method_and_url(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: get()/post() pass the uppercase Method constants, while
        # request(method, url) stores the supplied Method without normalizing
        # valid extension tokens.
        client = CodexHttpClient()

        self.assertEqual(client.get("https://example.test").snapshot().method, "GET")
        self.assertEqual(client.post("https://example.test").snapshot().method, "POST")
        custom = client.request("patch", "https://example.test")

        self.assertIsInstance(custom, CodexRequestBuilder)
        self.assertEqual(custom.snapshot().method, "patch")
        self.assertEqual(custom.snapshot().url, "https://example.test")

    def test_builder_methods_chain_without_mutating_previous_builder(self) -> None:
        client = CodexHttpClient()
        base = client.post("https://example.test")
        configured = (
            base.headers({"x-one": "1"})
            .header("x-two", "2")
            .bearer_auth("token")
            .timeout(3.5)
            .body("hello")
        )

        self.assertEqual(base.snapshot().headers, {})
        snapshot = configured.snapshot()
        self.assertEqual(snapshot.headers["x-one"], "1")
        self.assertEqual(snapshot.headers["x-two"], "2")
        self.assertEqual(snapshot.headers["authorization"], "Bearer token")
        self.assertEqual(snapshot.timeout, 3.5)
        self.assertEqual(snapshot.body, b"hello")

    def test_bearer_auth_formats_display_token_and_replaces_authorization(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: bearer_auth<T: Display>() delegates to reqwest
        # RequestBuilder::bearer_auth, producing Authorization: Bearer {token};
        # the underlying HeaderMap replacement remains case-insensitive.
        snapshot = (
            CodexHttpClient()
            .get("https://example.test")
            .header("Authorization", "old")
            .bearer_auth(123)
            .snapshot()
        )

        self.assertEqual(snapshot.headers, {"authorization": "Bearer 123"})

    def test_bearer_auth_invalid_display_token_preserves_builder_error_until_send(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: bearer_auth() converts Display output into a header value
        # through reqwest; invalid header values poison the RequestBuilder and
        # the error is returned by send() without dispatching.
        sent: list[CodexRequestSnapshot] = []
        builder = CodexHttpClient(sender=lambda snapshot: sent.append(snapshot) or "ok").get(
            "https://example.test"
        ).bearer_auth("bad\ntoken")

        self.assertEqual(builder.snapshot().headers, {})
        with self.assertRaisesRegex(ValueError, "invalid HTTP header"):
            builder.send()
        self.assertEqual(sent, [])

    def test_json_sets_body_and_content_type_in_snapshot(self) -> None:
        snapshot = (
            CodexHttpClient()
            .post("https://example.test")
            .json({"model": "m"})
            .snapshot()
        )

        self.assertEqual(snapshot.body, b'{"model":"m"}')
        self.assertEqual(snapshot.headers["content-type"], "application/json")
        self.assertEqual(snapshot.json_value, {"model": "m"})

    def test_json_then_body_preserves_json_content_type_header(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: json() delegates to reqwest RequestBuilder::json(), which
        # inserts content-type when absent; a later body() replaces only the
        # body slot and leaves existing headers in place.
        snapshot = (
            CodexHttpClient()
            .post("https://example.test")
            .json({"model": "m"})
            .body("raw")
            .snapshot()
        )

        self.assertEqual(snapshot.body, b"raw")
        self.assertIsNone(snapshot.json_value)
        self.assertEqual(snapshot.headers["content-type"], "application/json")

    def test_body_then_json_replaces_raw_body_with_json_body(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: body() and json() both delegate through
        # CodexRequestBuilder::map over reqwest::RequestBuilder; a later
        # json() call replaces the previously configured raw body and inserts
        # JSON content-type when it is absent.
        snapshot = (
            CodexHttpClient()
            .post("https://example.test")
            .body("raw")
            .json({"model": "m"})
            .snapshot()
        )

        self.assertEqual(snapshot.body, b'{"model":"m"}')
        self.assertEqual(snapshot.json_value, {"model": "m"})
        self.assertEqual(snapshot.headers["content-type"], "application/json")

    def test_timeout_uses_last_configured_value(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: timeout() delegates to reqwest RequestBuilder::timeout()
        # through map(); repeated calls produce a builder with the later
        # timeout value.
        snapshot = (
            CodexHttpClient()
            .get("https://example.test")
            .timeout(1.0)
            .timeout(2.5)
            .snapshot()
        )

        self.assertEqual(snapshot.timeout, 2.5)

    def test_json_respects_existing_content_type_case_insensitively(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: reqwest RequestBuilder::json() checks
        # req.headers().contains_key(CONTENT_TYPE) before inserting the JSON
        # content type; HeaderMap lookup is case-insensitive.
        snapshot = (
            CodexHttpClient()
            .post("https://example.test")
            .header("Content-Type", "application/vnd.codex+json")
            .json({"model": "m"})
            .snapshot()
        )

        self.assertEqual(snapshot.body, b'{"model":"m"}')
        self.assertEqual(snapshot.headers, {"Content-Type": "application/vnd.codex+json"})

    def test_user_headers_replace_case_insensitively_like_header_map(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: header() and headers() delegate to reqwest RequestBuilder
        # methods backed by http::HeaderMap, where header names are
        # case-insensitive and later same-name inserts replace earlier values.
        snapshot = (
            CodexHttpClient()
            .get("https://example.test")
            .header("X-Test", "1")
            .header("x-test", "2")
            .headers({"AUTHORIZATION": "old", "authorization": "new"})
            .snapshot()
        )

        self.assertEqual(snapshot.headers, {"x-test": "2", "authorization": "new"})

    def test_send_injects_trace_headers_at_send_time(self) -> None:
        sent: list[CodexRequestSnapshot] = []
        client = CodexHttpClient(
            sender=lambda snapshot: sent.append(snapshot) or "ok",
            trace_header_provider=lambda: {"traceparent": "00-abc-def-01"},
        )
        builder = client.get("https://example.test").header("x-test", "1")

        self.assertEqual(builder.snapshot().headers, {"x-test": "1"})
        self.assertEqual(builder.send(), "ok")

        self.assertEqual(sent[0].headers["x-test"], "1")
        self.assertEqual(sent[0].headers["traceparent"], "00-abc-def-01")

    def test_send_trace_headers_override_existing_headers_at_send_time(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: send() calls builder.headers(trace_headers()) immediately
        # before reqwest send(); reqwest replace_headers() inserts trace
        # headers into the existing map, replacing same-name entries.
        sent: list[CodexRequestSnapshot] = []
        client = CodexHttpClient(
            sender=lambda snapshot: sent.append(snapshot) or "ok",
            trace_header_provider=lambda: {"traceparent": "00-abc-def-01"},
        )
        builder = client.get("https://example.test").header("traceparent", "user")

        self.assertEqual(builder.snapshot().headers["traceparent"], "user")
        self.assertEqual(builder.send(), "ok")
        self.assertEqual(sent[0].headers["traceparent"], "00-abc-def-01")

    def test_send_trace_headers_replace_existing_headers_case_insensitively(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: send() calls builder.headers(trace_headers()) immediately
        # before reqwest send(); reqwest replace_headers() replaces occupied
        # HeaderMap entries even when the prior spelling used different case.
        sent: list[CodexRequestSnapshot] = []
        client = CodexHttpClient(
            sender=lambda snapshot: sent.append(snapshot) or "ok",
            trace_header_provider=lambda: {"traceparent": "00-abc-def-01"},
        )
        builder = client.get("https://example.test").header("TraceParent", "user")

        self.assertEqual(builder.snapshot().headers, {"TraceParent": "user"})
        self.assertEqual(builder.send(), "ok")
        self.assertEqual(sent[0].headers, {"traceparent": "00-abc-def-01"})

    def test_send_filters_invalid_trace_headers_from_provider(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: HeaderMapInjector::set only inserts headers when both
        # HeaderName::from_bytes and HeaderValue::from_str succeed.
        sent: list[CodexRequestSnapshot] = []
        client = CodexHttpClient(
            sender=lambda snapshot: sent.append(snapshot) or "ok",
            trace_header_provider=lambda: {
                "traceparent": "00-abc-def-01",
                "bad key": "ignored",
                "bad:key": "ignored",
                "x-bad": "line\nbreak",
                "x-nul": "bad\0value",
                "x-nonascii": "snowman \u2603",
            },
        )

        builder = client.get("https://example.test")

        self.assertEqual(builder.snapshot().headers, {})
        self.assertEqual(builder.send(), "ok")
        self.assertEqual(sent[0].headers, {"traceparent": "00-abc-def-01"})

    def test_send_preserves_user_header_builder_errors_until_send(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: RequestBuilder::header stores invalid header conversion
        # errors in the builder; send() returns that failure without sending.
        sent: list[CodexRequestSnapshot] = []
        events: list[dict[str, object]] = []
        client = CodexHttpClient(
            sender=lambda snapshot: sent.append(snapshot) or "ok",
            debug_logger=events.append,
        )
        builder = (
            client.get("https://example.test")
            .header("x-valid", "1")
            .header("bad key", "ignored")
            .header("x-after", "2")
        )

        snapshot = builder.snapshot()
        self.assertEqual(snapshot.headers, {"x-valid": "1", "x-after": "2"})

        with self.assertRaisesRegex(ValueError, "invalid HTTP header"):
            builder.send()

        self.assertEqual(sent, [])
        self.assertEqual(events[0]["message"], "Request failed")
        self.assertEqual(events[0]["method"], "GET")
        self.assertEqual(events[0]["url"], "https://example.test")
        self.assertIn("invalid HTTP header", events[0]["error"])

    def test_headers_records_first_invalid_user_header_without_dropping_valid_ones(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract adaptation: Python dict input approximates Rust HeaderMap;
        # invalid entries poison the builder while valid entries remain visible
        # in the request snapshot.
        sent: list[CodexRequestSnapshot] = []
        client = CodexHttpClient(sender=lambda snapshot: sent.append(snapshot) or "ok")
        builder = client.post("https://example.test").headers(
            {
                "x-one": "1",
                "bad:key": "ignored",
                "x-two": "2",
            }
        )

        self.assertEqual(builder.snapshot().headers, {"x-one": "1", "x-two": "2"})
        with self.assertRaisesRegex(ValueError, "invalid HTTP header"):
            builder.send()
        self.assertEqual(sent, [])

    def test_send_logs_completed_request_after_sender_returns(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: CodexRequestBuilder::send emits the "Request completed"
        # debug event with method, URL, status, headers, and version.
        events: list[dict[str, object]] = []
        client = CodexHttpClient(
            sender=lambda _snapshot: _ResponseLike(),
            debug_logger=events.append,
        )

        response = client.post("https://example.test/responses").send()

        self.assertIsInstance(response, _ResponseLike)
        self.assertEqual(
            events,
            [
                {
                    "message": "Request completed",
                    "method": "POST",
                    "url": "https://example.test/responses",
                    "status": 201,
                    "headers": {"x-result": "created"},
                    "version": "HTTP/1.1",
                }
            ],
        )

    def test_send_async_preserves_trace_headers_debug_and_result(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: CodexRequestBuilder::send is async in Rust. Python's
        # dependency-light async facade delegates through the same send-time
        # trace header injection and debug side-effect path.
        sent: list[CodexRequestSnapshot] = []
        events: list[dict[str, object]] = []
        client = CodexHttpClient(
            sender=lambda snapshot: sent.append(snapshot) or _ResponseLike(),
            trace_header_provider=lambda: {"traceparent": "00-abc-def-01"},
            debug_logger=events.append,
        )

        response = asyncio.run(
            client.post("https://example.test/async")
            .header("x-test", "1")
            .send_async()
        )

        self.assertIsInstance(response, _ResponseLike)
        self.assertEqual(sent[0].headers["x-test"], "1")
        self.assertEqual(sent[0].headers["traceparent"], "00-abc-def-01")
        self.assertEqual(
            events,
            [
                {
                    "message": "Request completed",
                    "method": "POST",
                    "url": "https://example.test/async",
                    "status": 201,
                    "headers": {"x-result": "created"},
                    "version": "HTTP/1.1",
                }
            ],
        )

    def test_send_completed_debug_fields_use_response_methods(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: the success debug event reads response.status(),
        # response.headers(), and response.version() from the reqwest response.
        events: list[dict[str, object]] = []
        client = CodexHttpClient(
            sender=lambda _snapshot: _ResponseMethodLike(),
            debug_logger=events.append,
        )

        response = client.get("https://example.test/accepted").send()

        self.assertIsInstance(response, _ResponseMethodLike)
        self.assertEqual(
            events,
            [
                {
                    "message": "Request completed",
                    "method": "GET",
                    "url": "https://example.test/accepted",
                    "status": 202,
                    "headers": {"x-method": "accepted"},
                    "version": "HTTP/2",
                }
            ],
        )

    def test_send_logs_failed_request_before_reraising_error(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: CodexRequestBuilder::send emits the "Request failed"
        # debug event with method, URL, status, and error, then returns the
        # original send error to the caller.
        events: list[dict[str, object]] = []
        error = TransportError.http(503, body="busy")

        def fail(_snapshot: CodexRequestSnapshot) -> object:
            raise error

        client = CodexHttpClient(sender=fail, debug_logger=events.append)

        with self.assertRaises(TransportError) as raised:
            client.get("https://example.test/fail").send()

        self.assertIs(raised.exception, error)
        self.assertEqual(
            events,
            [
                {
                    "message": "Request failed",
                    "method": "GET",
                    "url": "https://example.test/fail",
                    "status": 503,
                    "error": "http 503: 'busy'",
                }
            ],
        )

    def test_send_failed_debug_status_uses_error_status_method(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: the failure debug event uses reqwest::Error::status(), so
        # a send error carrying an HTTP status projects that status into the
        # event while preserving the original error.
        events: list[dict[str, object]] = []
        error = _StatusMethodError("rate limited")

        def fail(_snapshot: CodexRequestSnapshot) -> object:
            raise error

        client = CodexHttpClient(sender=fail, debug_logger=events.append)

        with self.assertRaises(_StatusMethodError) as raised:
            client.post("https://example.test/rate-limit").send()

        self.assertIs(raised.exception, error)
        self.assertEqual(
            events,
            [
                {
                    "message": "Request failed",
                    "method": "POST",
                    "url": "https://example.test/rate-limit",
                    "status": 429,
                    "error": "rate limited",
                }
            ],
        )

    def test_inject_trace_headers_uses_current_span_context(self) -> None:
        headers = trace_headers({"traceparent": "00-abc-def-01"})

        self.assertEqual(headers, {"traceparent": "00-abc-def-01"})

    def test_trace_headers_builds_traceparent_from_span_context_fields(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Rust test: inject_trace_headers_uses_current_span_context.
        # Contract: TraceContextPropagator injects the current span context
        # into a W3C traceparent header through HeaderMapInjector.
        headers = trace_headers(
            {
                "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                "span_id": "00f067aa0ba902b7",
                "trace_flags": "01",
            }
        )

        self.assertEqual(
            headers,
            {
                "traceparent": (
                    "00-4bf92f3577b34da6a3ce929d0e0e4736-"
                    "00f067aa0ba902b7-01"
                )
            },
        )

    def test_trace_headers_ignores_invalid_span_context_fields(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: invalid OpenTelemetry span contexts are not injected as
        # trace headers; the Rust test asserts extraction from a valid context.
        self.assertEqual(
            trace_headers(
                {
                    "trace_id": "0" * 32,
                    "span_id": "00f067aa0ba902b7",
                    "trace_flags": "01",
                }
            ),
            {},
        )
        self.assertEqual(
            trace_headers(
                {
                    "trace_id": "4bf92f3577b34da6a3ce929d0e0e4736",
                    "span_id": "not-hex",
                    "trace_flags": "01",
                }
            ),
            {},
        )

    def test_trace_headers_ignores_invalid_propagator_values(self) -> None:
        headers = trace_headers(
            {"traceparent": "ignored"},
            lambda _context: {
                "traceparent": "00-abc-def-01",
                "bad key": "value",
                "bad:key": "value",
                "x-bad": "line\nbreak",
                "x-nul": "bad\0value",
                "x-nonascii": "snowman \u2603",
            },
        )

        self.assertEqual(headers, {"traceparent": "00-abc-def-01"})

    def test_default_send_uses_real_http_sender_after_trace_injection(self) -> None:
        # Rust crate/module: codex-client/src/default_client.rs
        # Contract: CodexRequestBuilder::send injects trace headers at send
        # time and delegates to the real client request builder.
        client = CodexHttpClient(
            trace_header_provider=lambda: {"traceparent": "00-abc-def-01"}
        )

        with LocalHttpServer() as server:
            response = (
                client.post(f"{server.url}/responses")
                .header("x-test", "1")
                .json({"model": "m"})
                .send()
            )

        self.assertEqual(response.status, 200)
        self.assertEqual(response.headers["x-default-client"], "ok")
        self.assertEqual(server.recorded[0]["method"], "POST")
        self.assertEqual(server.recorded[0]["path"], "/responses")
        self.assertEqual(server.recorded[0]["body"], b'{"model":"m"}')
        self.assertEqual(_header(server.recorded[0]["headers"], "x-test"), "1")
        self.assertEqual(
            _header(server.recorded[0]["headers"], "traceparent"),
            "00-abc-def-01",
        )
        self.assertEqual(
            _header(server.recorded[0]["headers"], "content-type"),
            "application/json",
        )


if __name__ == "__main__":
    unittest.main()
