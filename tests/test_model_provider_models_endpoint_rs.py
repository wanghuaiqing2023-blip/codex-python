import asyncio
import unittest
from unittest.mock import patch

from pycodex.model_provider.models_endpoint import (
    MODELS_ENDPOINT,
    OpenAiModelsEndpoint,
    _append_client_version_query,
    _endpoint_url,
)
from pycodex.model_provider_info import ModelProviderInfo


class ModelProviderModelsEndpointRsTests(unittest.TestCase):
    def test_command_auth_provider_reports_command_auth_without_cached_auth(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/models_endpoint.rs
        # command_auth_provider_reports_command_auth_without_cached_auth.
        endpoint = OpenAiModelsEndpoint(
            ModelProviderInfo(auth={"command": "print-token", "cwd": "."}),
            None,
        )

        self.assertTrue(endpoint.has_command_auth())

    def test_provider_without_command_auth_reports_no_command_auth(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/models_endpoint.rs
        # provider_without_command_auth_reports_no_command_auth.
        endpoint = OpenAiModelsEndpoint(ModelProviderInfo.create_openai_provider(None), None)

        self.assertFalse(endpoint.has_command_auth())

    def test_models_endpoint_constant_and_url_shape_match_rust_endpoint(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/models_endpoint.rs
        # MODELS_ENDPOINT is "/models" and list_models calls that endpoint.
        self.assertEqual(MODELS_ENDPOINT, "/models")
        self.assertEqual(_endpoint_url("https://example.test/v1"), "https://example.test/v1/models")
        self.assertEqual(_endpoint_url("https://example.test/v1/models"), "https://example.test/v1/models")
        self.assertEqual(
            _append_client_version_query("https://example.test/v1/models?api-version=1", "0.99.0"),
            "https://example.test/v1/models?api-version=1&client_version=0.99.0",
        )

    def test_list_models_uses_default_client_headers_before_provider_headers(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/models_endpoint.rs
        # list_models builds ReqwestTransport with login::default_client and the
        # request-level provider headers take precedence over client defaults.
        provider = ModelProviderInfo(
            base_url="https://example.test/v1",
            http_headers={"originator": "provider-origin", "x-provider": "present"},
        )
        endpoint = OpenAiModelsEndpoint(provider, None)
        captured: dict[str, object] = {}

        def fetch(url: str, headers: dict[str, str]):
            captured["url"] = url
            captured["headers"] = headers
            return object(), None

        with (
            patch(
                "pycodex.model_provider.models_endpoint.default_headers",
                return_value={
                    "originator": "default-origin",
                    "user-agent": "codex-test/1",
                },
            ),
            patch("pycodex.model_provider.models_endpoint._fetch_models", side_effect=fetch),
        ):
            asyncio.run(endpoint.list_models("0.99.0"))

        self.assertEqual(
            captured["url"],
            "https://example.test/v1/models?client_version=0.99.0",
        )
        self.assertEqual(
            captured["headers"],
            {
                "originator": "provider-origin",
                "user-agent": "codex-test/1",
                "x-provider": "present",
            },
        )


if __name__ == "__main__":
    unittest.main()
