import asyncio
import json
import unittest
from dataclasses import dataclass

from pycodex.codex_api import ApiError
from pycodex.codex_api import ImageBackground
from pycodex.codex_api import ImageEditRequest
from pycodex.codex_api import ImageGenerationRequest
from pycodex.codex_api import ImageQuality
from pycodex.codex_api import ImageUrl
from pycodex.codex_api import ImagesClient
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


@dataclass(frozen=True)
class HeaderAuth:
    value: str = "Bearer token"

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        headers["authorization"] = self.value


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


def response_body() -> bytes:
    return json.dumps(
        {
            "created": 1778832973,
            "background": "opaque",
            "data": [{"b64_json": "REDACT"}],
            "output_format": "png",
            "quality": "medium",
            "size": "1024x1536",
            "usage": {
                "input_tokens": 1474,
                "output_tokens": 1372,
                "total_tokens": 2846,
            },
        }
    ).encode()


class CodexApiEndpointImagesRsTests(unittest.TestCase):
    # Rust: codex-api/src/endpoint/images.rs
    # tests::generate_posts_typed_request_and_parses_image_response.
    def test_generate_posts_typed_request_and_parses_image_response(self) -> None:
        transport = CapturingTransport(response_body())
        client = ImagesClient(transport=transport, provider=provider(), auth=DummyAuth())

        response = asyncio.run(
            client.generate(
                ImageGenerationRequest(
                    prompt="a red fox in a field",
                    background=ImageBackground.OPAQUE,
                    model="gpt-image-1.5",
                    quality=ImageQuality.MEDIUM,
                    size="1024x1536",
                ),
                {},
            )
        )

        self.assertEqual(response.created, 1778832973)
        self.assertEqual(response.background, ImageBackground.OPAQUE)
        self.assertEqual(response.quality, ImageQuality.MEDIUM)
        self.assertEqual(response.size, "1024x1536")
        self.assertEqual(response.data[0].b64_json, "REDACT")
        self.assertIsNotNone(transport.last_request)
        self.assertEqual(
            transport.last_request.url,
            "https://example.com/api/codex/images/generations",
        )
        self.assertEqual(transport.last_request.method, "POST")
        self.assertEqual(
            transport.last_request.body.json_value(),
            {
                "prompt": "a red fox in a field",
                "background": "opaque",
                "model": "gpt-image-1.5",
                "quality": "medium",
                "size": "1024x1536",
            },
        )

    # Rust: codex-api/src/endpoint/images.rs
    # Contract: generate delegates through EndpointSession with extra headers and auth.
    def test_generate_applies_extra_headers_and_auth(self) -> None:
        transport = CapturingTransport(response_body())
        client = ImagesClient(transport=transport, provider=provider(), auth=HeaderAuth())

        asyncio.run(
            client.generate(
                ImageGenerationRequest(
                    prompt="a red fox in a field",
                    model="gpt-image-1.5",
                ),
                {"x-extra": "yes"},
            )
        )

        self.assertIsNotNone(transport.last_request)
        self.assertEqual(transport.last_request.headers["x-extra"], "yes")
        self.assertEqual(transport.last_request.headers["authorization"], "Bearer token")

    # Rust: codex-api/src/endpoint/images.rs
    # tests::edit_posts_typed_request_and_parses_image_response.
    def test_edit_posts_typed_request_and_parses_image_response(self) -> None:
        transport = CapturingTransport(response_body())
        client = ImagesClient(transport=transport, provider=provider(), auth=DummyAuth())

        response = asyncio.run(
            client.edit(
                ImageEditRequest(
                    images=[ImageUrl("data:image/png;base64,Zm9v")],
                    prompt="add a red hat",
                    model="gpt-image-1.5",
                ),
                {},
            )
        )

        self.assertEqual(response.created, 1778832973)
        self.assertIsNotNone(transport.last_request)
        self.assertEqual(
            transport.last_request.url,
            "https://example.com/api/codex/images/edits",
        )
        self.assertEqual(
            transport.last_request.body.json_value(),
            {
                "images": [{"image_url": "data:image/png;base64,Zm9v"}],
                "prompt": "add a red hat",
                "model": "gpt-image-1.5",
            },
        )

    # Rust: codex-api/src/endpoint/images.rs
    # tests::image_response_requires_image_data.
    def test_image_response_requires_image_data(self) -> None:
        transport = CapturingTransport(json.dumps({"created": 1778832973}).encode())
        client = ImagesClient(transport=transport, provider=provider(), auth=DummyAuth())

        with self.assertRaises(ApiError) as caught:
            asyncio.run(
                client.generate(
                    ImageGenerationRequest(
                        prompt="a red fox in a field",
                        model="gpt-image-1.5",
                    ),
                    {},
                )
            )

        self.assertEqual(caught.exception.kind, "stream")
        self.assertIn("failed to decode image generation response", str(caught.exception))
        self.assertIn("data", str(caught.exception))

    # Rust: codex-api/src/endpoint/images.rs
    # Contract: with_telemetry returns a new client with request telemetry configured.
    def test_with_telemetry_returns_new_client(self) -> None:
        transport = CapturingTransport(response_body())
        client = ImagesClient(transport=transport, provider=provider(), auth=DummyAuth())
        telemetry = object()

        updated = client.with_telemetry(telemetry)

        self.assertIsNone(client.request_telemetry)
        self.assertIs(updated.request_telemetry, telemetry)
        self.assertIs(updated.transport, client.transport)
        self.assertIs(updated.provider, client.provider)
        self.assertIs(updated.auth, client.auth)


if __name__ == "__main__":
    unittest.main()
