import asyncio
import json
import unittest
from dataclasses import dataclass

from pycodex.codex_api import MemoriesClient
from pycodex.codex_api import MemorySummarizeInput
from pycodex.codex_api import Provider
from pycodex.codex_api import RawMemory
from pycodex.codex_api import RawMemoryMetadata
from pycodex.codex_api import RetryConfig
from pycodex.codex_client import Request
from pycodex.codex_client import Response


@dataclass
class CapturingTransport:
    response_body: bytes
    request: Request | None = None

    def execute(self, request: Request) -> Response:
        self.request = request
        return Response(status=200, headers={}, body=self.response_body)

    def stream(self, request: Request):  # pragma: no cover - memories uses execute.
        raise AssertionError("unexpected stream call")


class DummyAuth:
    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["authorization"] = "Bearer token"


def provider() -> Provider:
    return Provider(
        name="test",
        base_url="https://example.com/api/codex",
        query_params={},
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


class MemoriesEndpointTests(unittest.TestCase):
    # Rust source: codex-api/src/endpoint/memories.rs
    # Contract: keep the memory summarize path wire-compatible.
    def test_path_is_memories_trace_summarize_for_wire_compatibility(self) -> None:
        self.assertEqual(MemoriesClient.path(), "memories/trace_summarize")

    # Rust source: codex-api/src/endpoint/memories.rs
    # Contract: summarize_input posts the serialized input and decodes output.
    def test_summarize_input_posts_expected_payload_and_parses_output(self) -> None:
        response_body = json.dumps(
            {
                "output": [
                    {
                        "trace_summary": "raw summary",
                        "memory_summary": "memory summary",
                    }
                ]
            }
        ).encode("utf-8")
        transport = CapturingTransport(response_body=response_body)
        client = MemoriesClient(transport=transport, provider=provider(), auth=DummyAuth())
        summarize_input = MemorySummarizeInput(
            model="gpt-test",
            raw_memories=[
                RawMemory(
                    id="trace-1",
                    metadata=RawMemoryMetadata(source_path="/tmp/trace.json"),
                    items=[{"type": "message", "role": "user", "content": []}],
                )
            ],
        )

        output = asyncio.run(client.summarize_input(summarize_input, {"x-extra": "yes"}))

        self.assertEqual(len(output), 1)
        self.assertEqual(output[0].raw_memory, "raw summary")
        self.assertEqual(output[0].memory_summary, "memory summary")
        self.assertIsNotNone(transport.request)
        assert transport.request is not None
        self.assertEqual(transport.request.method, "POST")
        self.assertEqual(
            transport.request.url,
            "https://example.com/api/codex/memories/trace_summarize",
        )
        self.assertEqual(transport.request.headers["authorization"], "Bearer token")
        self.assertEqual(transport.request.headers["x-extra"], "yes")
        self.assertIsNotNone(transport.request.body)
        assert transport.request.body is not None
        payload = transport.request.body.json_value()
        self.assertEqual(payload["model"], "gpt-test")
        self.assertEqual(payload["traces"][0]["id"], "trace-1")
        self.assertEqual(payload["traces"][0]["metadata"]["source_path"], "/tmp/trace.json")

    # Rust source: codex-api/src/endpoint/memories.rs
    # Contract: summarize accepts a raw JSON body and decodes the raw_memory alias.
    def test_summarize_posts_raw_body_and_decodes_raw_memory_alias(self) -> None:
        response_body = json.dumps(
            {"output": [{"raw_memory": "alias", "memory_summary": "summary"}]}
        ).encode("utf-8")
        transport = CapturingTransport(response_body=response_body)
        client = MemoriesClient(transport=transport, provider=provider(), auth=DummyAuth())

        output = asyncio.run(client.summarize({"model": "gpt-test", "traces": []}, {}))

        self.assertEqual(output[0].raw_memory, "alias")
        self.assertIsNotNone(transport.request)
        assert transport.request is not None
        self.assertIsNotNone(transport.request.body)
        assert transport.request.body is not None
        self.assertEqual(transport.request.body.json_value(), {"model": "gpt-test", "traces": []})

    # Rust source: codex-api/src/endpoint/memories.rs
    # Contract: summarize accepts serde_json::Value and passes the value unchanged.
    def test_summarize_preserves_arbitrary_json_value_body(self) -> None:
        response_body = json.dumps({"output": []}).encode("utf-8")
        transport = CapturingTransport(response_body=response_body)
        client = MemoriesClient(transport=transport, provider=provider(), auth=DummyAuth())

        asyncio.run(client.summarize([{"kind": "raw"}], {}))

        self.assertIsNotNone(transport.request)
        assert transport.request is not None
        self.assertIsNotNone(transport.request.body)
        assert transport.request.body is not None
        self.assertEqual(transport.request.body.json_value(), [{"kind": "raw"}])

    # Rust source: codex-api/src/endpoint/memories.rs
    # Contract: with_telemetry returns a new client with request telemetry configured.
    def test_with_telemetry_returns_new_client(self) -> None:
        transport = CapturingTransport(response_body=json.dumps({"output": []}).encode("utf-8"))
        client = MemoriesClient(transport=transport, provider=provider(), auth=DummyAuth())
        telemetry = object()

        updated = client.with_telemetry(telemetry)

        self.assertIsNone(client.request_telemetry)
        self.assertIs(updated.request_telemetry, telemetry)
        self.assertIs(updated.transport, client.transport)
        self.assertIs(updated.provider, client.provider)
        self.assertIs(updated.auth, client.auth)


if __name__ == "__main__":
    unittest.main()
