import asyncio
import json
import unittest
from dataclasses import dataclass

from pycodex.codex_api import CompactClient
from pycodex.codex_api import CompactionInput
from pycodex.codex_api import Provider
from pycodex.codex_api import RetryConfig
from pycodex.codex_client import Request
from pycodex.codex_client import Response


class CapturingTransport:
    def __init__(self, response_body: bytes) -> None:
        self.last_request: Request | None = None
        self.response_body = response_body

    def execute(self, req: Request) -> Response:
        self.last_request = req
        return Response(status=200, headers={}, body=self.response_body)

    def stream(self, _req: Request):  # pragma: no cover - Rust test asserts this path is unused.
        raise AssertionError("stream should not run")


@dataclass(frozen=True)
class DummyAuth:
    def add_auth_headers(self, _headers: dict[str, str]) -> None:
        return None


def provider() -> Provider:
    return Provider(
        name="test",
        base_url="https://example.com/api/codex",
        query_params=None,
        headers={},
        retry=RetryConfig(
            max_attempts=1,
            base_delay=0.001,
            retry_429=False,
            retry_5xx=True,
            retry_transport=True,
        ),
        stream_idle_timeout=1,
    )


class CodexApiEndpointCompactRsTests(unittest.TestCase):
    # Rust: codex-api/src/endpoint/compact.rs
    # tests::path_is_responses_compact.
    def test_path_is_responses_compact(self) -> None:
        self.assertEqual(CompactClient.path(), "responses/compact")

    # Rust: codex-api/src/endpoint/compact.rs
    # Contract: compact posts JSON body with request timeout and parses output.
    def test_compact_posts_body_timeout_and_parses_output(self) -> None:
        transport = CapturingTransport(
            json.dumps(
                {
                    "output": [
                        {
                            "type": "message",
                            "role": "assistant",
                            "content": [{"type": "output_text", "text": "summary"}],
                        }
                    ]
                }
            ).encode()
        )
        client = CompactClient(transport=transport, provider=provider(), auth=DummyAuth())

        output = asyncio.run(
            client.compact({"model": "gpt-test", "input": []}, {}, request_timeout=12.5)
        )

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0].type, "message")
        self.assertEqual(output[0].content[0].text, "summary")
        self.assertIsNotNone(transport.last_request)
        self.assertEqual(transport.last_request.method, "POST")
        self.assertEqual(
            transport.last_request.url,
            "https://example.com/api/codex/responses/compact",
        )
        self.assertEqual(
            transport.last_request.body.json_value(),
            {"model": "gpt-test", "input": []},
        )
        self.assertEqual(transport.last_request.timeout, 12.5)

    # Rust: codex-api/src/endpoint/compact.rs
    # Contract: compact accepts serde_json::Value and passes the value unchanged.
    def test_compact_preserves_arbitrary_json_value_body(self) -> None:
        transport = CapturingTransport(json.dumps({"output": []}).encode())
        client = CompactClient(transport=transport, provider=provider(), auth=DummyAuth())

        asyncio.run(client.compact([{"kind": "raw"}], {}, request_timeout=1.0))

        self.assertIsNotNone(transport.last_request)
        self.assertEqual(
            transport.last_request.body.json_value(),
            [{"kind": "raw"}],
        )

    # Rust: codex-api/src/endpoint/compact.rs
    # Contract: with_telemetry returns a new client with request telemetry configured.
    def test_with_telemetry_returns_new_client(self) -> None:
        transport = CapturingTransport(json.dumps({"output": []}).encode())
        client = CompactClient(transport=transport, provider=provider(), auth=DummyAuth())
        telemetry = object()

        updated = client.with_telemetry(telemetry)

        self.assertIsNone(client.request_telemetry)
        self.assertIs(updated.request_telemetry, telemetry)
        self.assertIs(updated.transport, client.transport)
        self.assertIs(updated.provider, client.provider)
        self.assertIs(updated.auth, client.auth)

    # Rust: codex-api/src/endpoint/compact.rs
    # Contract: compact_input serializes CompactionInput before delegating.
    def test_compact_input_serializes_compaction_input(self) -> None:
        transport = CapturingTransport(json.dumps({"output": []}).encode())
        client = CompactClient(transport=transport, provider=provider(), auth=DummyAuth())

        asyncio.run(
            client.compact_input(
                CompactionInput(
                    model="gpt-test",
                    input=[{"type": "message", "role": "user", "content": []}],
                    tools=[],
                    parallel_tool_calls=False,
                ),
                {},
                request_timeout=3,
            )
        )

        self.assertIsNotNone(transport.last_request)
        self.assertEqual(
            transport.last_request.body.json_value(),
            {
                "model": "gpt-test",
                "input": [{"type": "message", "role": "user", "content": []}],
                "tools": [],
                "parallel_tool_calls": False,
            },
        )


if __name__ == "__main__":
    unittest.main()
