import asyncio
import json
import unittest
from dataclasses import dataclass

from pycodex.codex_api import AllowedCaller
from pycodex.codex_api import ApiError
from pycodex.codex_api import ApproximateLocation
from pycodex.codex_api import OpenOperation
from pycodex.codex_api import Provider
from pycodex.codex_api import RetryConfig
from pycodex.codex_api import SearchClient
from pycodex.codex_api import SearchCommands
from pycodex.codex_api import SearchContextSize
from pycodex.codex_api import SearchFilters
from pycodex.codex_api import SearchImageSettings
from pycodex.codex_api import SearchInput
from pycodex.codex_api import SearchQuery
from pycodex.codex_api import SearchRequest
from pycodex.codex_api import SearchSettings
from pycodex.codex_client import Request
from pycodex.codex_client import Response
from pycodex.protocol import ContentItem
from pycodex.protocol import ResponseItem


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


@dataclass(frozen=True)
class HeaderAuth:
    value: str = "Bearer token"

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["authorization"] = self.value


def provider() -> Provider:
    return Provider(
        name="test",
        base_url="https://example.com/v1",
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


def typed_search_request() -> SearchRequest:
    return SearchRequest(
        id="search-session",
        model="gpt-test",
        input=SearchInput.items(
            [
                ResponseItem.message(
                    role="user",
                    content=[
                        ContentItem.input_text("find this"),
                        ContentItem.input_image("https://example.com/image.png"),
                    ],
                )
            ]
        ),
        commands=SearchCommands(
            search_query=[
                SearchQuery(q="OpenAI news", recency=7, domains=["openai.com"])
            ],
            open=[OpenOperation(ref_id="https://openai.com", lineno=12)],
        ),
        settings=SearchSettings(
            user_location=ApproximateLocation(country="US", city="San Francisco"),
            search_context_size=SearchContextSize.LOW,
            filters=SearchFilters(
                allowed_domains=["openai.com"],
                blocked_domains=["example.com"],
            ),
            image_settings=SearchImageSettings(max_results=4, caption=True),
            allowed_callers=[AllowedCaller.DIRECT],
            external_web_access=True,
        ),
        max_output_tokens=2500,
    )


class CodexApiEndpointSearchRsTests(unittest.TestCase):
    # Rust: codex-api/src/endpoint/search.rs
    # tests::search_posts_typed_request_and_parses_encrypted_output.
    def test_search_posts_typed_request_and_parses_encrypted_output(self) -> None:
        transport = CapturingTransport(json.dumps({"encrypted_output": "ciphertext"}).encode())
        client = SearchClient(transport=transport, provider=provider(), auth=DummyAuth())

        response = asyncio.run(client.search(typed_search_request(), {}))

        self.assertEqual(response.encrypted_output, "ciphertext")
        self.assertIsNotNone(transport.last_request)
        self.assertEqual(transport.last_request.method, "POST")
        self.assertEqual(
            transport.last_request.url,
            "https://example.com/v1/alpha/search",
        )
        self.assertEqual(
            transport.last_request.body.json_value(),
            {
                "id": "search-session",
                "model": "gpt-test",
                "input": [
                    {
                        "type": "message",
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": "find this"},
                            {
                                "type": "input_image",
                                "image_url": "https://example.com/image.png",
                            },
                        ],
                    }
                ],
                "commands": {
                    "search_query": [
                        {
                            "q": "OpenAI news",
                            "recency": 7,
                            "domains": ["openai.com"],
                        }
                    ],
                    "open": [{"ref_id": "https://openai.com", "lineno": 12}],
                },
                "settings": {
                    "user_location": {
                        "type": "approximate",
                        "country": "US",
                        "city": "San Francisco",
                    },
                    "search_context_size": "low",
                    "filters": {
                        "allowed_domains": ["openai.com"],
                        "blocked_domains": ["example.com"],
                    },
                    "image_settings": {"max_results": 4, "caption": True},
                    "allowed_callers": ["direct"],
                    "external_web_access": True,
                },
                "max_output_tokens": 2500,
            },
        )

    # Rust: codex-api/src/endpoint/search.rs
    # Contract: search delegates through EndpointSession with extra headers and auth.
    def test_search_applies_extra_headers_and_auth(self) -> None:
        transport = CapturingTransport(json.dumps({"encrypted_output": "ciphertext"}).encode())
        client = SearchClient(transport=transport, provider=provider(), auth=HeaderAuth())

        asyncio.run(client.search(SearchRequest(id="search-session"), {"x-extra": "yes"}))

        self.assertIsNotNone(transport.last_request)
        self.assertEqual(transport.last_request.headers["x-extra"], "yes")
        self.assertEqual(transport.last_request.headers["authorization"], "Bearer token")

    def test_search_response_decode_error_maps_to_stream_error(self) -> None:
        transport = CapturingTransport(b"{}")
        client = SearchClient(transport=transport, provider=provider(), auth=DummyAuth())

        with self.assertRaises(ApiError) as caught:
            asyncio.run(client.search(SearchRequest(id="search-session"), {}))

        self.assertEqual(caught.exception.kind, "stream")
        self.assertIn("failed to decode search response", str(caught.exception))
        self.assertIn("encrypted_output", str(caught.exception))

    # Rust: codex-api/src/endpoint/search.rs
    # Contract: with_telemetry returns a new client with request telemetry configured.
    def test_with_telemetry_returns_new_client(self) -> None:
        transport = CapturingTransport(json.dumps({"encrypted_output": "ciphertext"}).encode())
        client = SearchClient(transport=transport, provider=provider(), auth=DummyAuth())
        telemetry = object()

        updated = client.with_telemetry(telemetry)

        self.assertIsNone(client.request_telemetry)
        self.assertIs(updated.request_telemetry, telemetry)
        self.assertIs(updated.transport, client.transport)
        self.assertIs(updated.provider, client.provider)
        self.assertIs(updated.auth, client.auth)


if __name__ == "__main__":
    unittest.main()
