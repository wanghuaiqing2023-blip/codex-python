"""Rust-derived tests for ``codex-api/src/endpoint/session.rs``.

Rust crate: ``codex-api``
Rust module: ``src/endpoint/session.rs``
Contract: shared endpoint session request construction, auth application,
transport delegation, and request-telemetry retry wrapping.

The Rust module has no local unit tests; these tests are derived from the
source contract in ``EndpointSession::{new, with_request_telemetry, provider,
execute, execute_with, stream_with}``.
"""

from __future__ import annotations

import asyncio
import unittest

from pycodex.codex_api.endpoint.session import EndpointSession
from pycodex.codex_api.provider import Provider
from pycodex.codex_api.provider import RetryConfig
from pycodex.codex_client import Request
from pycodex.codex_client import Response
from pycodex.codex_client import StreamResponse
from pycodex.codex_client import TransportError


def _provider() -> Provider:
    return Provider(
        name="openai",
        base_url="https://api.example.test/v1",
        query_params={"client": "py"},
        headers={"x-provider": "1"},
        retry=RetryConfig(
            max_attempts=1,
            base_delay=0,
            retry_429=False,
            retry_5xx=False,
            retry_transport=True,
        ),
        stream_idle_timeout=5,
    )


class RecordingAuth:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    def add_auth_headers(self, headers) -> None:
        headers["authorization"] = "Bearer token"

    async def apply_auth(self, request: Request) -> Request:
        self.requests.append(request)
        headers = dict(request.headers or {})
        headers["authorization"] = "Bearer token"
        return request.with_headers(headers)


class RecordingTransport:
    def __init__(self) -> None:
        self.execute_requests: list[Request] = []
        self.stream_requests: list[Request] = []
        self.fail_first = False

    async def execute(self, request: Request) -> Response:
        self.execute_requests.append(request)
        if self.fail_first and len(self.execute_requests) == 1:
            raise TransportError.network("temporary")
        return Response(status=200, headers={"x-response": "ok"}, body=b"done")

    async def stream(self, request: Request) -> StreamResponse:
        self.stream_requests.append(request)
        return StreamResponse(status=200, headers={"x-stream": "ok"}, bytes=[b"a"])


class RecordingTelemetry:
    def __init__(self) -> None:
        self.calls: list[tuple[int, int | None, str | None]] = []

    def on_request(self, attempt, status, error, duration) -> None:
        self.calls.append((attempt, status, error.kind if error else None))


class EndpointSessionRsTests(unittest.TestCase):
    def test_execute_builds_request_applies_auth_and_delegates_transport(self) -> None:
        transport = RecordingTransport()
        auth = RecordingAuth()
        session = EndpointSession.new(transport, _provider(), auth)

        response = asyncio.run(
            session.execute(
                "POST",
                "responses",
                {"x-extra": "2"},
                {"model": "test-model"},
            )
        )

        self.assertEqual(response.body, b"done")
        self.assertEqual(len(auth.requests), 1)
        self.assertEqual(len(transport.execute_requests), 1)
        pre_auth = auth.requests[0]
        sent = transport.execute_requests[0]
        self.assertEqual(pre_auth.url, "https://api.example.test/v1/responses?client=py")
        self.assertEqual(pre_auth.headers, {"x-provider": "1", "x-extra": "2"})
        self.assertEqual(pre_auth.body.json_value(), {"model": "test-model"})
        self.assertEqual(sent.headers["authorization"], "Bearer token")

    def test_execute_with_configure_runs_before_auth_and_send(self) -> None:
        transport = RecordingTransport()
        auth = RecordingAuth()
        session = EndpointSession.new(transport, _provider(), auth)

        def configure(request: Request) -> None:
            request.headers["x-configured"] = "yes"

        asyncio.run(session.execute_with("GET", "models", {}, None, configure))

        self.assertEqual(auth.requests[0].headers["x-configured"], "yes")
        self.assertEqual(transport.execute_requests[0].headers["x-configured"], "yes")

    def test_stream_with_uses_stream_transport(self) -> None:
        transport = RecordingTransport()
        session = EndpointSession.new(transport, _provider(), RecordingAuth())

        stream = asyncio.run(
            session.stream_with("POST", "responses", {"accept": "text/event-stream"}, {}, lambda _req: None)
        )

        self.assertEqual(stream.status, 200)
        self.assertEqual(list(stream.bytes), [b"a"])
        self.assertEqual(transport.stream_requests[0].headers["accept"], "text/event-stream")

    def test_with_request_telemetry_retries_and_rebuilds_request(self) -> None:
        transport = RecordingTransport()
        transport.fail_first = True
        telemetry = RecordingTelemetry()
        session = EndpointSession.new(transport, _provider(), RecordingAuth())
        session = session.with_request_telemetry(telemetry)

        response = asyncio.run(session.execute("POST", "responses", {}, {"n": 1}))

        self.assertEqual(response.status, 200)
        self.assertEqual(len(transport.execute_requests), 2)
        self.assertIsNot(transport.execute_requests[0], transport.execute_requests[1])
        self.assertEqual(
            telemetry.calls,
            [(0, None, "network"), (1, 200, None)],
        )

    def test_transport_error_is_mapped_to_api_error(self) -> None:
        class FailingTransport(RecordingTransport):
            async def execute(self, request: Request) -> Response:
                raise TransportError.build("bad request")

        session = EndpointSession.new(FailingTransport(), _provider(), RecordingAuth())

        with self.assertRaisesRegex(Exception, "request build error: bad request") as caught:
            asyncio.run(session.execute("POST", "responses", {}, {}))

        self.assertEqual(caught.exception.kind, "transport")


if __name__ == "__main__":
    unittest.main()
