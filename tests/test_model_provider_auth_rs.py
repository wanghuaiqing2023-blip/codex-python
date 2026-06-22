import unittest

from pycodex.agent_identity import generate_agent_key_material
from pycodex.login.auth.agent_identity import AgentIdentityAuth, AgentIdentityAuthRecord
from pycodex.model_provider.auth import (
    AgentIdentityAuthProvider,
    UnauthenticatedAuthProvider,
    auth_manager_for_provider,
    auth_provider_from_auth,
    bearer_auth_for_provider,
    resolve_provider_auth,
    unauthenticated_auth_provider,
)
from pycodex.model_provider.bearer_auth_provider import BearerAuthProvider
from pycodex.model_provider_info import ModelProviderInfo


class FakeAuth:
    def __init__(self, token=None, account_id=None, fedramp=False) -> None:
        self.token = token
        self.account_id = account_id
        self.fedramp = fedramp

    def get_token(self):
        return self.token

    def get_account_id(self):
        return self.account_id

    def is_fedramp_account(self):
        return self.fedramp


class ModelProviderAuthRsTests(unittest.TestCase):
    def test_unauthenticated_auth_provider_adds_no_headers(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/auth.rs
        # unauthenticated_auth_provider_adds_no_headers.
        provider = unauthenticated_auth_provider()

        self.assertIsInstance(provider, UnauthenticatedAuthProvider)
        self.assertEqual(provider.to_auth_headers(), {})

    def test_bearer_auth_for_provider_prefers_api_key_then_experimental_token(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # bearer_auth_for_provider checks provider.api_key() before
        # experimental_bearer_token.
        provider = ModelProviderInfo(env_key="OPENAI_API_KEY_FOR_TEST", experimental_bearer_token="fallback")

        env_auth = bearer_auth_for_provider(provider_with_env(provider, {"OPENAI_API_KEY_FOR_TEST": "env-token"}))
        self.assertIsInstance(env_auth, BearerAuthProvider)
        self.assertEqual(env_auth.to_auth_headers(), {"Authorization": "Bearer env-token"})

        token_provider = ModelProviderInfo(experimental_bearer_token="literal-token")
        token_auth = bearer_auth_for_provider(token_provider)
        self.assertIsInstance(token_auth, BearerAuthProvider)
        self.assertEqual(token_auth.to_auth_headers(), {"Authorization": "Bearer literal-token"})

    def test_resolve_provider_auth_prefers_provider_bearer_over_codex_auth(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # resolve_provider_auth returns provider-scoped bearer auth before
        # falling back to caller-supplied CodexAuth.
        provider = provider_with_env(ModelProviderInfo(env_key="OPENAI_API_KEY_FOR_TEST"), {"OPENAI_API_KEY_FOR_TEST": "provider-token"})

        auth = resolve_provider_auth(FakeAuth("codex-token"), provider)

        self.assertEqual(auth.to_auth_headers(), {"Authorization": "Bearer provider-token"})

    def test_resolve_provider_auth_uses_codex_auth_or_unauthenticated(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # resolve_provider_auth maps a first-party CodexAuth or returns the
        # no-header provider when no auth is available.
        provider = ModelProviderInfo()

        auth = resolve_provider_auth(FakeAuth("codex-token", "workspace-1", True), provider)
        self.assertEqual(
            auth.to_auth_headers(),
            {
                "Authorization": "Bearer codex-token",
                "ChatGPT-Account-ID": "workspace-1",
                "X-OpenAI-Fedramp": "true",
            },
        )
        self.assertEqual(resolve_provider_auth(None, provider).to_auth_headers(), {})

    def test_auth_provider_from_auth_maps_bearer_like_auth(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # CodexAuth::ApiKey/Chatgpt/ChatgptAuthTokens map to BearerAuthProvider.
        auth = auth_provider_from_auth(FakeAuth("token", "workspace", False))

        self.assertIsInstance(auth, BearerAuthProvider)
        self.assertEqual(
            auth.to_auth_headers(),
            {
                "Authorization": "Bearer token",
                "ChatGPT-Account-ID": "workspace",
            },
        )

    def test_agent_identity_auth_provider_adds_signed_authorization_header(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # AgentIdentityAuthProvider signs an AgentAssertion auth header and
        # keeps account routing headers.
        identity = agent_identity_auth(account_id="workspace", fedramp=False)

        headers = AgentIdentityAuthProvider(identity).to_auth_headers()

        self.assertTrue(headers["Authorization"].startswith("AgentAssertion "))
        self.assertEqual(headers["ChatGPT-Account-ID"], "workspace")
        self.assertNotIn("X-OpenAI-Fedramp", headers)

    def test_agent_identity_auth_provider_skips_failed_authorization_but_keeps_routing_headers(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # add_auth_headers ignores authorization_header_for_agent_task errors
        # and still inserts valid account/FedRAMP headers.
        identity = agent_identity_auth(account_id="workspace", fedramp=True)
        provider = AgentIdentityAuthProvider(identity, signer=lambda _key, _target: (_ for _ in ()).throw(ValueError("bad")))

        self.assertEqual(
            provider.to_auth_headers(),
            {
                "ChatGPT-Account-ID": "workspace",
                "X-OpenAI-Fedramp": "true",
            },
        )

    def test_agent_identity_auth_provider_skips_invalid_header_values(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # HeaderValue::from_str(...).ok() skips invalid Authorization and
        # account-id values without blocking the FedRAMP static header.
        identity = agent_identity_auth(account_id="bad\nworkspace", fedramp=True)
        provider = AgentIdentityAuthProvider(identity, signer=lambda _key, _target: "bad\nauthorization")

        self.assertEqual(provider.to_auth_headers(), {"X-OpenAI-Fedramp": "true"})

    def test_auth_manager_for_provider_wraps_command_auth_config(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/auth.rs
        # auth_manager_for_provider swaps in external bearer-only auth when
        # provider.auth exists, otherwise keeping the caller manager.
        base = object()
        self.assertIs(auth_manager_for_provider(base, ModelProviderInfo()), base)

        manager = auth_manager_for_provider(base, ModelProviderInfo(auth={"command": "print-token", "cwd": "."}))
        self.assertIsNot(manager, base)
        self.assertIsNotNone(manager)


def provider_with_env(provider: ModelProviderInfo, env: dict[str, str]):
    class ProviderWithEnv:
        experimental_bearer_token = provider.experimental_bearer_token
        auth = provider.auth

        def api_key(self):
            return provider.api_key(env)

    return ProviderWithEnv()


def agent_identity_auth(account_id: str, fedramp: bool) -> AgentIdentityAuth:
    key_material = generate_agent_key_material(seed=b"\x01" * 32)
    record = AgentIdentityAuthRecord(
        agent_runtime_id="runtime",
        agent_private_key=key_material.private_key_pkcs8_base64,
        account_id=account_id,
        chatgpt_user_id="user",
        email="user@example.com",
        plan_type="pro",
        chatgpt_account_is_fedramp=fedramp,
    )
    return AgentIdentityAuth(record, "task")


if __name__ == "__main__":
    unittest.main()
