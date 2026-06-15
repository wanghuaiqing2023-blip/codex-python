import asyncio

from pycodex.model_provider import (
    DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL,
    ConfiguredModelProvider,
    ProviderAccountError,
    ProviderAccountState,
    ProviderCapabilities,
    create_model_provider,
)
from pycodex.model_provider.amazon_bedrock import AmazonBedrockModelProvider
from pycodex.model_provider.models_endpoint import OpenAiModelsEndpoint
from pycodex.model_provider_info import ModelProviderInfo
from pycodex.models_manager import OpenAiModelsManager, StaticModelsManager
from pycodex.protocol import ProviderAccount
from pycodex.protocol.account import PlanType


class FakeAuth:
    def __init__(self, mode: str, *, email: str | None = None, plan_type="pro") -> None:
        self.mode = mode
        self.email = email
        self.plan_type = plan_type

    def auth_mode(self) -> str:
        return self.mode

    def is_api_key_auth(self) -> bool:
        return self.mode == "api_key"

    def is_chatgpt_auth(self) -> bool:
        return self.mode == "chatgpt"

    def uses_codex_backend(self) -> bool:
        return self.is_chatgpt_auth()

    def get_account_email(self):
        return self.email

    def account_plan_type(self):
        return self.plan_type


class FakeAuthManager:
    def __init__(self, auth=None) -> None:
        self._auth = auth

    async def auth(self):
        return self._auth

    def auth_cached(self):
        return self._auth

    def refresh_failure_for_auth(self, _auth):
        return None


def test_configured_provider_uses_default_capabilities_and_base_url() -> None:
    # Rust crate/module: codex-model-provider::provider
    provider_info = ModelProviderInfo.create_openai_provider("https://example.test/v1")
    provider = create_model_provider(provider_info)

    assert provider.info() is provider_info
    assert provider.capabilities() == ProviderCapabilities()
    assert provider.approval_review_preferred_model() == DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL
    assert provider.supports_attestation() is False
    assert asyncio.run(provider.runtime_base_url()) == "https://example.test/v1"


def test_configured_provider_account_state_for_openai_auth_modes() -> None:
    # Rust tests: openai_provider_returns_*_account_state.
    provider_info = ModelProviderInfo.create_openai_provider(None)

    unauthenticated = ConfiguredModelProvider(provider_info, None)
    assert unauthenticated.account_state() == ProviderAccountState(
        account=None,
        requires_openai_auth=True,
    )

    api_key = ConfiguredModelProvider(provider_info, FakeAuthManager(FakeAuth("api_key")))
    assert api_key.account_state() == ProviderAccountState(
        account=ProviderAccount.api_key(),
        requires_openai_auth=True,
    )

    chatgpt = ConfiguredModelProvider(
        provider_info,
        FakeAuthManager(FakeAuth("chatgpt", email="user@example.com", plan_type="pro")),
    )
    assert chatgpt.account_state() == ProviderAccountState(
        account=ProviderAccount.chatgpt("user@example.com", PlanType.PRO),
        requires_openai_auth=True,
    )

    missing_details = ConfiguredModelProvider(provider_info, FakeAuthManager(FakeAuth("chatgpt")))
    assert missing_details.account_state() is ProviderAccountError.MISSING_CHATGPT_ACCOUNT_DETAILS


def test_custom_non_openai_provider_returns_no_account_state() -> None:
    # Rust test: custom_non_openai_provider_returns_no_account_state.
    provider = create_model_provider(
        ModelProviderInfo(
            name="Custom",
            base_url="http://localhost:1234/v1",
            requires_openai_auth=False,
        )
    )

    assert provider.account_state() == ProviderAccountState(account=None, requires_openai_auth=False)


def test_configured_provider_models_manager_uses_static_catalog_when_present(tmp_path) -> None:
    # Rust contract: config model catalog selects StaticModelsManager.
    provider = create_model_provider(ModelProviderInfo.create_openai_provider(None), FakeAuthManager())
    catalog = {"models": []}

    manager = provider.models_manager(tmp_path, catalog)

    assert isinstance(manager, StaticModelsManager)
    assert manager.model_catalog.models == ()


def test_configured_provider_models_manager_uses_openai_endpoint_when_no_catalog(tmp_path) -> None:
    # Rust contract: default configured provider creates OpenAiModelsManager with endpoint client.
    auth_manager = FakeAuthManager(FakeAuth("chatgpt"))
    provider = create_model_provider(ModelProviderInfo.create_openai_provider(None), auth_manager)

    manager = provider.models_manager(tmp_path, None)

    assert isinstance(manager, OpenAiModelsManager)
    assert isinstance(manager.endpoint_client, OpenAiModelsEndpoint)
    assert manager.auth_manager is auth_manager


def test_create_model_provider_dispatches_amazon_bedrock() -> None:
    # Rust test: create_model_provider_does_not_use_openai_auth_manager_for_amazon_bedrock_provider.
    provider = create_model_provider(ModelProviderInfo.create_amazon_bedrock_provider(), FakeAuthManager())

    assert isinstance(provider, AmazonBedrockModelProvider)
    assert provider.auth_manager() is None
