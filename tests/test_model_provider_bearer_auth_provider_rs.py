import unittest

from pycodex.api import auth_header_telemetry
from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider


class ModelProviderBearerAuthProviderRsTests(unittest.TestCase):
    def test_bearer_auth_provider_reports_when_auth_header_will_attach(self):
        # Rust crate: codex-model-provider
        # Rust module: src/bearer_auth_provider.rs
        # Rust test: bearer_auth_provider_reports_when_auth_header_will_attach
        # Contract: auth telemetry observes that Authorization will be attached.
        auth = BearerAuthProvider(token="access-token")

        telemetry = auth_header_telemetry(auth)

        self.assertTrue(telemetry.has_auth_header)
        self.assertEqual(telemetry.auth_kind, "bearer")

    def test_bearer_auth_provider_adds_auth_headers(self):
        # Rust crate: codex-model-provider
        # Rust module: src/bearer_auth_provider.rs
        # Rust test: bearer_auth_provider_adds_auth_headers
        auth = BearerAuthProvider.for_test("access-token", "workspace-123")
        headers: dict[str, str] = {}

        auth.add_auth_headers(headers)

        self.assertEqual(headers.get("Authorization"), "Bearer access-token")
        self.assertEqual(headers.get("ChatGPT-Account-ID"), "workspace-123")

    def test_bearer_auth_provider_adds_fedramp_routing_header_for_fedramp_accounts(self):
        # Rust crate: codex-model-provider
        # Rust module: src/bearer_auth_provider.rs
        # Rust test: bearer_auth_provider_adds_fedramp_routing_header_for_fedramp_accounts
        auth = BearerAuthProvider(
            token="access-token",
            account_id="workspace-123",
            is_fedramp_account=True,
        )

        headers = auth.to_auth_headers()

        self.assertEqual(headers.get("X-OpenAI-Fedramp"), "true")

    def test_invalid_header_values_are_skipped_like_header_value_from_str(self):
        # Rust crate: codex-model-provider
        # Rust module: src/bearer_auth_provider.rs
        # Contract: invalid HeaderValue strings are ignored instead of inserted.
        auth = BearerAuthProvider(
            token="access-token\nbad",
            account_id="workspace-123\rbad",
            is_fedramp_account=True,
        )

        self.assertEqual(auth.to_auth_headers(), {"X-OpenAI-Fedramp": "true"})


if __name__ == "__main__":
    unittest.main()
