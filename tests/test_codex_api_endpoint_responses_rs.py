"""Rust-derived tests for ``codex-api/src/endpoint/responses.rs``.

Rust crate: ``codex-api``
Rust module: ``src/endpoint/responses.rs``
Contract: Responses HTTP endpoint request/header/compression shaping and
handoff to the SSE response stream boundary.
"""

from __future__ import annotations

import asyncio
import unittest

from pycodex.codex_api.common import ResponsesApiRequest
from pycodex.codex_api.endpoint.responses import ResponsesClient
from pycodex.codex_api.endpoint.responses import ResponsesOptions
from pycodex.codex_api.provider import Provider
from pycodex.codex_api.provider import RetryConfig
from pycodex.codex_api.requests import Compression
from pycodex.codex_api.requests import SessionSource
from pycodex.codex_api.requests import SubAgentSource
from pycodex.codex_client import Request
from pycodex.codex_client import RequestCompression
from pycodex.codex_client import StreamResponse


class OriginalItem:
    def __init__(self, item_type: str, item_id: str) -> None:
        self.type = item_type
        self.id = item_id

    def to_json_dict(self) -> dict[str, str]:
        return {"type": self.type}


def _provider(name: str = "openai", base_url: str = "https://api.example.test/v1") -> Provider:
    return Provider(
        name=name,
        base_url=base_url,
        query_params=None,
        headers={"x-provider": "1"},
        retry=RetryConfig(
            max_attempts=0,
            base_delay=0,
            retry_429=False,
            retry_5xx=False,
            retry_transport=False,
        ),
        stream_idle_timeout=7,
    )


class HeaderAuth:
    def add_auth_headers(self, headers) -> None:
        headers["authorization"] = "Bearer token"

    async def apply_auth(self, request: Request) -> Request:
        headers = dict(request.headers or {})
        self.add_auth_headers(headers)
        return request.with_headers(headers)


class RecordingTransport:
    def __init__(self) -> None:
        self.requests: list[Request] = []

    async def stream(self, request: Request) -> StreamResponse:
        self.requests.append(request)
        return StreamResponse(
            status=200,
            headers={"x-request-id": "req-1", "x-codex-turn-state": "turn-1"},
            bytes=[
                b'event: response.completed\n'
                b'data: {"type":"response.completed","response":{"id":"resp-1"}}\n\n'
            ],
        )


class ResponsesClientRsTests(unittest.TestCase):
    def test_stream_sets_path_accept_header_and_compression(self) -> None:
        transport = RecordingTransport()
        client = ResponsesClient.new(transport, _provider(), HeaderAuth())
        turn_state: dict[str, str] = {}

        stream = asyncio.run(
            client.stream(
                {"model": "test-model"},
                {"x-extra": "2"},
                Compression.ZSTD,
                turn_state,
            )
        )

        sent = transport.requests[0]
        self.assertEqual(sent.method, "POST")
        self.assertEqual(sent.url, "https://api.example.test/v1/responses")
        self.assertEqual(sent.headers["x-provider"], "1")
        self.assertEqual(sent.headers["x-extra"], "2")
        self.assertEqual(sent.headers["accept"], "text/event-stream")
        self.assertEqual(sent.headers["authorization"], "Bearer token")
        self.assertEqual(sent.compression, RequestCompression.ZSTD)
        self.assertEqual(sent.body.json_value(), {"model": "test-model"})
        self.assertEqual(stream.upstream_request_id, "req-1")
        self.assertEqual(turn_state, {"value": "turn-1"})
        events = list(stream)
        self.assertEqual([event.kind for event in events], ["rate_limits", "completed"])
        self.assertEqual(events[1].value["response_id"], "resp-1")

    def test_stream_request_builds_headers_and_subagent(self) -> None:
        transport = RecordingTransport()
        client = ResponsesClient.new(transport, _provider(), HeaderAuth())
        request = ResponsesApiRequest(model="test-model", input=[{"type": "message"}])
        options = ResponsesOptions(
            session_id="sess-1",
            thread_id="thread-1",
            session_source=SessionSource.sub_agent(SubAgentSource.REVIEW),
            extra_headers={"x-extra": "2"},
        )

        asyncio.run(client.stream_request(request, options))

        sent = transport.requests[0]
        self.assertEqual(sent.headers["x-client-request-id"], "thread-1")
        self.assertEqual(sent.headers["session-id"], "sess-1")
        self.assertEqual(sent.headers["thread-id"], "thread-1")
        self.assertEqual(sent.headers["x-openai-subagent"], "review")
        self.assertEqual(sent.headers["accept"], "text/event-stream")

    def test_stream_request_attaches_item_ids_for_azure_stored_requests(self) -> None:
        transport = RecordingTransport()
        client = ResponsesClient.new(transport, _provider(name="azure"), HeaderAuth())
        original = OriginalItem("message", "item-1")
        request = ResponsesApiRequest(
            model="test-model",
            input=[original],
            store=True,
        )

        asyncio.run(client.stream_request(request, ResponsesOptions()))

        sent_body = transport.requests[0].body.json_value()
        self.assertEqual(sent_body["input"][0]["id"], "item-1")

    def test_with_telemetry_returns_client_with_updated_session_and_sse(self) -> None:
        client = ResponsesClient.new(RecordingTransport(), _provider(), HeaderAuth())
        telemetry = object()
        sse = object()

        updated = client.with_telemetry(telemetry, sse)

        self.assertIs(updated.sse_telemetry, sse)
        self.assertIs(updated.session.request_telemetry, telemetry)
        self.assertIsNone(client.sse_telemetry)


if __name__ == "__main__":
    unittest.main()
