"""Rust-derived tests for ``codex-api/src/provider.rs``."""

from __future__ import annotations

import unittest

from pycodex.codex_api import Provider
from pycodex.codex_api import RetryConfig
from pycodex.codex_api import is_azure_responses_provider
from pycodex.codex_client import RequestCompression
from pycodex.codex_client import RetryOn
from pycodex.codex_client import RetryPolicy


class CodexApiProviderRsTests(unittest.TestCase):
    def test_retry_config_converts_to_retry_policy(self) -> None:
        # Rust crate/module: codex-api/src/provider.rs
        # Contract: RetryConfig::to_policy copies max_attempts/base_delay and
        # wraps retry flags in RetryOn.
        config = RetryConfig(
            max_attempts=3,
            base_delay=0.25,
            retry_429=True,
            retry_5xx=False,
            retry_transport=True,
        )

        self.assertEqual(
            config.to_policy(),
            RetryPolicy(
                max_attempts=3,
                base_delay=0.25,
                retry_on=RetryOn(True, False, True),
            ),
        )

    def test_url_for_path_trims_slashes_and_appends_query_params(self) -> None:
        # Rust crate/module: codex-api/src/provider.rs
        # Contract: Provider::url_for_path trims base trailing slashes, path
        # leading slashes, and directly joins query params as key=value pairs.
        provider = _provider(
            base_url="https://api.example.test/v1/",
            query_params={"api-version": "2025-01-01", "extra": "yes"},
        )

        self.assertEqual(
            provider.url_for_path("/responses"),
            "https://api.example.test/v1/responses?api-version=2025-01-01&extra=yes",
        )
        self.assertEqual(
            provider.url_for_path(""),
            "https://api.example.test/v1?api-version=2025-01-01&extra=yes",
        )

    def test_build_request_uses_provider_headers_and_default_body_fields(self) -> None:
        # Rust crate/module: codex-api/src/provider.rs
        # Contract: Provider::build_request constructs a codex-client Request
        # with cloned headers, no body, no timeout, and no compression.
        provider = _provider(headers={"x-default": "1"})

        request = provider.build_request("POST", "responses")

        self.assertEqual(request.method, "POST")
        self.assertEqual(request.url, "https://api.example.test/responses")
        self.assertEqual(request.headers, {"x-default": "1"})
        self.assertIsNone(request.body)
        self.assertEqual(request.compression, RequestCompression.NONE)
        self.assertIsNone(request.timeout)

    def test_websocket_url_for_path_rewrites_http_schemes(self) -> None:
        # Rust crate/module: codex-api/src/provider.rs
        # Contract: http -> ws, https -> wss, ws/wss and unknown schemes are
        # returned unchanged after URL construction.
        self.assertEqual(
            _provider(base_url="http://api.example.test").websocket_url_for_path("stream"),
            "ws://api.example.test/stream",
        )
        self.assertEqual(
            _provider(base_url="https://api.example.test").websocket_url_for_path("stream"),
            "wss://api.example.test/stream",
        )
        self.assertEqual(
            _provider(base_url="wss://api.example.test").websocket_url_for_path("stream"),
            "wss://api.example.test/stream",
        )
        self.assertEqual(
            _provider(base_url="unix://api.example.test").websocket_url_for_path("stream"),
            "unix://api.example.test/stream",
        )

    def test_detects_azure_responses_base_urls(self) -> None:
        # Rust test: detects_azure_responses_base_urls.
        positive_cases = [
            "https://foo.openai.azure.com/openai",
            "https://foo.openai.azure.us/openai/deployments/bar",
            "https://foo.cognitiveservices.azure.cn/openai",
            "https://foo.aoai.azure.com/openai",
            "https://foo.openai.azure-api.net/openai",
            "https://foo.z01.azurefd.net/",
        ]

        for base_url in positive_cases:
            with self.subTest(base_url=base_url):
                self.assertTrue(is_azure_responses_provider("test", base_url))

        self.assertTrue(is_azure_responses_provider("Azure", "https://example.com"))

        negative_cases = [
            "https://api.openai.com/v1",
            "https://example.com/openai",
            "https://myproxy.azurewebsites.net/openai",
        ]

        for base_url in negative_cases:
            with self.subTest(base_url=base_url):
                self.assertFalse(is_azure_responses_provider("test", base_url))

    def test_provider_azure_detection_delegates_to_name_and_base_url(self) -> None:
        # Rust crate/module: codex-api/src/provider.rs
        # Contract: Provider::is_azure_responses_endpoint delegates to
        # is_azure_responses_provider(name, base_url).
        self.assertTrue(_provider(name="azure").is_azure_responses_endpoint())
        self.assertTrue(
            _provider(
                name="proxy",
                base_url="https://foo.openai.azure.com/openai",
            ).is_azure_responses_endpoint()
        )
        self.assertFalse(_provider(name="openai").is_azure_responses_endpoint())


def _provider(
    *,
    name: str = "openai",
    base_url: str = "https://api.example.test",
    query_params: dict[str, str] | None = None,
    headers: dict[str, str] | None = None,
) -> Provider:
    return Provider(
        name=name,
        base_url=base_url,
        query_params=query_params,
        headers=headers or {},
        retry=RetryConfig(
            max_attempts=2,
            base_delay=0.1,
            retry_429=True,
            retry_5xx=True,
            retry_transport=True,
        ),
        stream_idle_timeout=30.0,
    )


if __name__ == "__main__":
    unittest.main()
