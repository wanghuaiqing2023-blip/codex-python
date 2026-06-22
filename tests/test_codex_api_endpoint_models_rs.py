import asyncio
import json
import unittest
from dataclasses import dataclass
from typing import Mapping

from pycodex.codex_api import ApiError
from pycodex.codex_api import AuthProvider
from pycodex.codex_api import ModelsClient
from pycodex.codex_api import Provider
from pycodex.codex_api import RetryConfig
from pycodex.codex_client import Request
from pycodex.codex_client import Response


class CapturingTransport:
    def __init__(
        self,
        body: Mapping[str, object] | bytes | None = None,
        etag: str | None = None,
    ) -> None:
        self.last_request: Request | None = None
        self.body = body if body is not None else {"models": []}
        self.etag = etag

    def execute(self, req: Request) -> Response:
        self.last_request = req
        body = self.body if isinstance(self.body, bytes) else json.dumps(self.body).encode()
        headers = {"etag": self.etag} if self.etag is not None else {}
        return Response(status=200, headers=headers, body=body)

    def stream(self, _req: Request):  # pragma: no cover - Rust test asserts this path is unused.
        raise AssertionError("stream should not run")


@dataclass(frozen=True)
class DummyAuth:
    headers: Mapping[str, str] | None = None

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers.update(dict(self.headers or {}))


def provider(
    base_url: str,
    *,
    query_params: Mapping[str, str] | None = None,
) -> Provider:
    return Provider(
        name="test",
        base_url=base_url,
        query_params=query_params,
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


def model_payload() -> dict[str, object]:
    return {
        "slug": "gpt-test",
        "display_name": "gpt-test",
        "description": "desc",
        "default_reasoning_level": "medium",
        "supported_reasoning_levels": [
            {"effort": "low", "description": "low"},
            {"effort": "medium", "description": "medium"},
            {"effort": "high", "description": "high"},
        ],
        "shell_type": "shell_command",
        "visibility": "list",
        "minimal_client_version": [0, 99, 0],
        "supported_in_api": True,
        "priority": 1,
        "upgrade": None,
        "base_instructions": "base instructions",
        "supports_reasoning_summaries": False,
        "support_verbosity": False,
        "default_verbosity": None,
        "apply_patch_tool_type": None,
        "truncation_policy": {"mode": "bytes", "limit": 10_000},
        "supports_parallel_tool_calls": False,
        "supports_image_detail_original": False,
        "context_window": 272_000,
        "experimental_supported_tools": [],
    }


class CodexApiEndpointModelsRsTests(unittest.TestCase):
    # Rust: codex-api/src/endpoint/models.rs
    # tests::appends_client_version_query.
    def test_appends_client_version_query(self) -> None:
        transport = CapturingTransport()
        client = ModelsClient(
            transport=transport,
            provider=provider("https://example.com/api/codex"),
            auth=DummyAuth(),
        )

        models, _etag = asyncio.run(client.list_models("0.99.0", {}))

        self.assertEqual(len(models), 0)
        self.assertIsNotNone(transport.last_request)
        self.assertEqual(
            transport.last_request.url,
            "https://example.com/api/codex/models?client_version=0.99.0",
        )
        self.assertEqual(transport.last_request.method, "GET")

    # Rust: codex-api/src/endpoint/models.rs
    # tests::parses_models_response.
    def test_parses_models_response(self) -> None:
        transport = CapturingTransport({"models": [model_payload()]})
        client = ModelsClient(
            transport=transport,
            provider=provider("https://example.com/api/codex"),
            auth=DummyAuth(),
        )

        models, _etag = asyncio.run(client.list_models("0.99.0", {}))

        self.assertEqual(len(models), 1)
        self.assertEqual(models[0].slug, "gpt-test")
        self.assertTrue(models[0].supported_in_api)
        self.assertEqual(models[0].priority, 1)

    # Rust: codex-api/src/endpoint/models.rs
    # tests::list_models_includes_etag.
    def test_list_models_includes_etag(self) -> None:
        transport = CapturingTransport(etag='"abc"')
        client = ModelsClient(
            transport=transport,
            provider=provider("https://example.com/api/codex"),
            auth=DummyAuth(),
        )

        models, etag = asyncio.run(client.list_models("0.1.0", {}))

        self.assertEqual(len(models), 0)
        self.assertEqual(etag, '"abc"')

    # Rust: codex-api/src/endpoint/models.rs
    # Contract: with_telemetry returns a new client with request telemetry configured.
    def test_with_telemetry_returns_new_client(self) -> None:
        transport = CapturingTransport()
        client = ModelsClient(
            transport=transport,
            provider=provider("https://example.com/api/codex"),
            auth=DummyAuth(),
        )
        telemetry = object()

        updated = client.with_telemetry(telemetry)

        self.assertIsNone(client.request_telemetry)
        self.assertIs(updated.request_telemetry, telemetry)
        self.assertIs(updated.transport, client.transport)
        self.assertIs(updated.provider, client.provider)
        self.assertIs(updated.auth, client.auth)

    # Rust: codex-api/tests/models_integration.rs
    # models_client_hits_models_endpoint plus endpoint module error mapping.
    def test_extra_headers_auth_and_decode_error_mapping(self) -> None:
        transport = CapturingTransport(b"{")
        client = ModelsClient(
            transport=transport,
            provider=provider(
                "https://example.com/api/codex",
                query_params={"api-version": "1"},
            ),
            auth=DummyAuth({"authorization": "Bearer secret"}),
        )

        with self.assertRaises(ApiError) as caught:
            asyncio.run(client.list_models("0.1.0", {"x-test": "present"}))

        self.assertEqual(caught.exception.kind, "stream")
        self.assertIn("failed to decode models response", str(caught.exception))
        self.assertIsNotNone(transport.last_request)
        self.assertEqual(
            transport.last_request.url,
            "https://example.com/api/codex/models?api-version=1&client_version=0.1.0",
        )
        self.assertEqual(
            dict(transport.last_request.headers or {}),
            {"x-test": "present", "authorization": "Bearer secret"},
        )


if __name__ == "__main__":
    unittest.main()
