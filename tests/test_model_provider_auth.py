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


def test_unauthenticated_auth_provider_adds_no_headers() -> None:
    # Rust crate/module: codex-model-provider::auth::unauthenticated_auth_provider
    provider = unauthenticated_auth_provider()

    assert isinstance(provider, UnauthenticatedAuthProvider)
    assert provider.to_auth_headers() == {}


def test_bearer_auth_for_provider_prefers_api_key_then_experimental_token(monkeypatch) -> None:
    # Rust crate/module: codex-model-provider::auth::bearer_auth_for_provider
    monkeypatch.setenv("OPENAI_API_KEY_FOR_TEST", "env-token")
    env_provider = ModelProviderInfo(env_key="OPENAI_API_KEY_FOR_TEST", experimental_bearer_token="fallback")

    env_auth = bearer_auth_for_provider(env_provider)
    assert isinstance(env_auth, BearerAuthProvider)
    assert env_auth.to_auth_headers() == {"Authorization": "Bearer env-token"}

    token_provider = ModelProviderInfo(experimental_bearer_token="literal-token")
    token_auth = bearer_auth_for_provider(token_provider)
    assert isinstance(token_auth, BearerAuthProvider)
    assert token_auth.to_auth_headers() == {"Authorization": "Bearer literal-token"}


def test_resolve_provider_auth_prefers_provider_bearer_over_codex_auth(monkeypatch) -> None:
    # Rust crate/module: codex-model-provider::auth::resolve_provider_auth
    monkeypatch.setenv("OPENAI_API_KEY_FOR_TEST", "provider-token")
    provider = ModelProviderInfo(env_key="OPENAI_API_KEY_FOR_TEST")

    auth = resolve_provider_auth(FakeAuth("codex-token"), provider)

    assert auth.to_auth_headers() == {"Authorization": "Bearer provider-token"}


def test_resolve_provider_auth_uses_codex_auth_or_unauthenticated() -> None:
    # Rust crate/module: codex-model-provider::auth::resolve_provider_auth
    provider = ModelProviderInfo()

    auth = resolve_provider_auth(FakeAuth("codex-token", "workspace-1", True), provider)
    assert auth.to_auth_headers() == {
        "Authorization": "Bearer codex-token",
        "ChatGPT-Account-ID": "workspace-1",
        "X-OpenAI-Fedramp": "true",
    }

    assert resolve_provider_auth(None, provider).to_auth_headers() == {}


def test_auth_provider_from_auth_maps_bearer_like_auth() -> None:
    # Rust crate/module: codex-model-provider::auth::auth_provider_from_auth
    auth = auth_provider_from_auth(FakeAuth("token", "workspace", False))

    assert isinstance(auth, BearerAuthProvider)
    assert auth.to_auth_headers() == {
        "Authorization": "Bearer token",
        "ChatGPT-Account-ID": "workspace",
    }


def test_agent_identity_auth_provider_skips_failed_authorization_but_keeps_routing_headers() -> None:
    # Rust behavior: failed authorization header creation does not block account/FedRAMP headers.
    record = AgentIdentityAuthRecord(
        agent_runtime_id="runtime",
        agent_private_key="private",
        account_id="workspace",
        chatgpt_user_id="user",
        email="user@example.com",
        plan_type="pro",
        chatgpt_account_is_fedramp=True,
    )
    identity = AgentIdentityAuth(record, "task")
    provider = AgentIdentityAuthProvider(identity, signer=lambda _key, _target: (_ for _ in ()).throw(ValueError("bad")))

    assert provider.to_auth_headers() == {
        "ChatGPT-Account-ID": "workspace",
        "X-OpenAI-Fedramp": "true",
    }


def test_agent_identity_auth_provider_adds_signed_authorization_header() -> None:
    # Rust crate/module: codex-model-provider::auth::AgentIdentityAuthProvider
    record = AgentIdentityAuthRecord(
        agent_runtime_id="runtime",
        agent_private_key="private",
        account_id="workspace",
        chatgpt_user_id="user",
        email="user@example.com",
        plan_type="pro",
        chatgpt_account_is_fedramp=False,
    )
    identity = AgentIdentityAuth(record, "task")
    provider = AgentIdentityAuthProvider(identity, signer=lambda key, target: f"signed:{key.agent_runtime_id}:{target['task_id']}")

    assert provider.to_auth_headers() == {
        "Authorization": "signed:runtime:task",
        "ChatGPT-Account-ID": "workspace",
    }


def test_auth_manager_for_provider_wraps_command_auth_config() -> None:
    # Rust crate/module: codex-model-provider::auth::auth_manager_for_provider
    base = object()
    assert auth_manager_for_provider(base, ModelProviderInfo()) is base

    manager = auth_manager_for_provider(base, ModelProviderInfo(auth={"command": "print-token", "cwd": "."}))
    assert manager is not base
    assert manager is not None
