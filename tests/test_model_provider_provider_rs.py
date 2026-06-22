import asyncio
import tempfile
import unittest
from pathlib import Path

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
from pycodex.model_provider_info import ModelProviderAwsAuthInfo, ModelProviderInfo
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
        return self.mode in {"chatgpt", "agent_identity"}

    def uses_codex_backend(self) -> bool:
        return self.is_chatgpt_auth()

    def get_account_email(self):
        return self.email

    def account_plan_type(self):
        return self.plan_type


class FakeAuthManager:
    def __init__(self, auth=None, *, refresh_failure=False) -> None:
        self._auth = auth
        self.refresh_failure = refresh_failure

    async def auth(self):
        return self._auth

    def auth_cached(self):
        return self._auth

    def refresh_failure_for_auth(self, _auth):
        return "failed" if self.refresh_failure else None


class ModelProviderProviderRsTests(unittest.TestCase):
    def test_configured_provider_uses_default_capabilities(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # configured_provider_uses_default_capabilities.
        provider = create_model_provider(ModelProviderInfo.create_openai_provider(None), None)

        self.assertEqual(provider.capabilities(), ProviderCapabilities())

    def test_configured_provider_uses_default_approval_review_preferred_model(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # configured_provider_uses_default_approval_review_preferred_model.
        provider = create_model_provider(ModelProviderInfo.create_openai_provider(None), None)

        self.assertEqual(provider.approval_review_preferred_model(), DEFAULT_APPROVAL_REVIEW_PREFERRED_MODEL)

    def test_configured_provider_runtime_base_url_uses_configured_base_url(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # configured_provider_runtime_base_url_uses_configured_base_url.
        provider = create_model_provider(
            ModelProviderInfo(name="mock", base_url="https://example.test/v1"),
            None,
        )

        self.assertEqual(asyncio.run(provider.runtime_base_url()), "https://example.test/v1")

    def test_create_model_provider_builds_command_auth_manager_without_base_manager(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # create_model_provider_builds_command_auth_manager_without_base_manager.
        provider = create_model_provider(
            ModelProviderInfo(auth={"command": "print-token", "cwd": "."}),
            None,
        )

        self.assertIsNotNone(provider.auth_manager())

    def test_create_model_provider_does_not_use_openai_auth_manager_for_amazon_bedrock_provider(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # create_model_provider_does_not_use_openai_auth_manager_for_amazon_bedrock_provider.
        provider = create_model_provider(
            ModelProviderInfo.create_amazon_bedrock_provider(ModelProviderAwsAuthInfo(profile="codex-bedrock")),
            FakeAuthManager(FakeAuth("api_key")),
        )

        self.assertIsInstance(provider, AmazonBedrockModelProvider)
        self.assertIsNone(provider.auth_manager())

    def test_openai_provider_returns_unauthenticated_openai_account_state(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # openai_provider_returns_unauthenticated_openai_account_state.
        provider = create_model_provider(ModelProviderInfo.create_openai_provider(None), None)

        self.assertEqual(provider.account_state(), ProviderAccountState(account=None, requires_openai_auth=True))

    def test_openai_provider_returns_api_key_account_state(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # openai_provider_returns_api_key_account_state.
        provider = create_model_provider(
            ModelProviderInfo.create_openai_provider(None),
            FakeAuthManager(FakeAuth("api_key")),
        )

        self.assertEqual(
            provider.account_state(),
            ProviderAccountState(account=ProviderAccount.api_key(), requires_openai_auth=True),
        )

    def test_openai_provider_returns_chatgpt_account_state_or_missing_details_error(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/provider.rs
        # ChatGPT-like auth requires email and plan type for app-visible state.
        provider_info = ModelProviderInfo.create_openai_provider(None)
        chatgpt = ConfiguredModelProvider(
            provider_info,
            FakeAuthManager(FakeAuth("chatgpt", email="user@example.com", plan_type="pro")),
        )
        missing = ConfiguredModelProvider(provider_info, FakeAuthManager(FakeAuth("chatgpt")))

        self.assertEqual(
            chatgpt.account_state(),
            ProviderAccountState(
                account=ProviderAccount.chatgpt("user@example.com", PlanType.PRO),
                requires_openai_auth=True,
            ),
        )
        self.assertIs(missing.account_state(), ProviderAccountError.MISSING_CHATGPT_ACCOUNT_DETAILS)

    def test_refresh_failure_suppresses_openai_account_state(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/provider.rs
        # account_state ignores cached auth when refresh_failure_for_auth is set.
        provider = ConfiguredModelProvider(
            ModelProviderInfo.create_openai_provider(None),
            FakeAuthManager(FakeAuth("api_key"), refresh_failure=True),
        )

        self.assertEqual(provider.account_state(), ProviderAccountState(account=None, requires_openai_auth=True))

    def test_custom_non_openai_provider_returns_no_account_state(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # custom_non_openai_provider_returns_no_account_state.
        provider = create_model_provider(
            ModelProviderInfo(name="Custom", base_url="http://localhost:1234/v1", requires_openai_auth=False),
            None,
        )

        self.assertEqual(provider.account_state(), ProviderAccountState(account=None, requires_openai_auth=False))

    def test_amazon_bedrock_provider_returns_bedrock_account_state(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/provider.rs
        # amazon_bedrock_provider_returns_bedrock_account_state.
        provider = create_model_provider(ModelProviderInfo.create_amazon_bedrock_provider(None), None)

        self.assertEqual(
            provider.account_state(),
            ProviderAccountState(account=ProviderAccount.amazon_bedrock(), requires_openai_auth=False),
        )

    def test_models_manager_uses_static_catalog_or_openai_endpoint(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/provider.rs
        # models_manager chooses StaticModelsManager for configured catalogs and
        # OpenAiModelsManager/OpenAiModelsEndpoint otherwise.
        auth_manager = FakeAuthManager(FakeAuth("chatgpt"))
        provider = create_model_provider(ModelProviderInfo.create_openai_provider(None), auth_manager)
        with tempfile.TemporaryDirectory() as tmpdir:
            static_manager = provider.models_manager(Path(tmpdir), {"models": []})
            remote_manager = provider.models_manager(Path(tmpdir), None)

        self.assertIsInstance(static_manager, StaticModelsManager)
        self.assertEqual(static_manager.model_catalog.models, ())
        self.assertIsInstance(remote_manager, OpenAiModelsManager)
        self.assertIsInstance(remote_manager.endpoint_client, OpenAiModelsEndpoint)
        self.assertIs(remote_manager.auth_manager, auth_manager)


if __name__ == "__main__":
    unittest.main()
