import asyncio
import tempfile
import unittest
from pathlib import Path

from pycodex.model_provider import ProviderAccountState, ProviderCapabilities
from pycodex.model_provider.amazon_bedrock import AmazonBedrockModelProvider
from pycodex.model_provider_info import AMAZON_BEDROCK_GPT_5_4_MODEL_ID, ModelProviderAwsAuthInfo, ModelProviderInfo
from pycodex.models_manager import StaticModelsManager
from pycodex.protocol import ProviderAccount
from pycodex.protocol.openai_models import ModelsResponse
from pycodex.models_manager.model_info import model_info_from_slug


class Context:
    def __init__(self, region: str) -> None:
        self.region = region


class ModelProviderAmazonBedrockModRsTests(unittest.TestCase):
    def test_api_provider_for_bedrock_bearer_token_uses_configured_region_endpoint(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mod.rs
        # api_provider_for_bedrock_bearer_token_uses_configured_region_endpoint.
        provider = AmazonBedrockModelProvider.new(
            ModelProviderInfo.create_amazon_bedrock_provider(ModelProviderAwsAuthInfo(region="eu-central-1")),
            aws_context_loader=lambda _config: Context("eu-central-1"),
        )

        api_provider = asyncio.run(provider.api_provider())

        self.assertEqual(api_provider.base_url, "https://bedrock-mantle.eu-central-1.api.aws/openai/v1")

    def test_runtime_base_url_returns_resolved_bedrock_endpoint(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mod.rs
        # runtime_base_url wraps mantle::runtime_base_url.
        provider = AmazonBedrockModelProvider.new(
            ModelProviderInfo.create_amazon_bedrock_provider(ModelProviderAwsAuthInfo(region="ap-south-1")),
            aws_context_loader=lambda _config: Context("ap-south-1"),
        )

        self.assertEqual(
            asyncio.run(provider.runtime_base_url()),
            "https://bedrock-mantle.ap-south-1.api.aws/openai/v1",
        )

    def test_capabilities_disable_unsupported_hosted_tools(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mod.rs
        # capabilities_disable_unsupported_hosted_tools.
        provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider(None))

        self.assertEqual(
            provider.capabilities(),
            ProviderCapabilities(namespace_tools=True, image_generation=False, web_search=False),
        )

    def test_approval_review_preferred_model_uses_bedrock_gpt_5_4(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/mod.rs
        # approval_review_preferred_model_uses_bedrock_gpt_5_4.
        provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider(None))

        self.assertEqual(provider.approval_review_preferred_model(), AMAZON_BEDROCK_GPT_5_4_MODEL_ID)

    def test_bedrock_provider_exposes_no_openai_auth_manager_or_auth(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mod.rs
        # auth_manager and auth return None for Bedrock.
        provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider(None))

        self.assertIsNone(provider.auth_manager())
        self.assertIsNone(asyncio.run(provider.auth()))

    def test_bedrock_provider_account_state(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mod.rs
        # account_state returns AmazonBedrock without OpenAI auth.
        provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider(None))

        self.assertEqual(
            provider.account_state(),
            ProviderAccountState(account=ProviderAccount.amazon_bedrock(), requires_openai_auth=False),
        )

    def test_models_manager_uses_static_catalog_or_configured_catalog(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/mod.rs
        # models_manager always returns StaticModelsManager and honors an
        # explicitly configured model catalog.
        provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider(None))
        custom_model = model_info_from_slug("custom-bedrock-model")

        with tempfile.TemporaryDirectory() as tmpdir:
            default_manager = provider.models_manager(Path(tmpdir), None)
            custom_manager = provider.models_manager(Path(tmpdir), ModelsResponse((custom_model,)))

        self.assertIsInstance(default_manager, StaticModelsManager)
        self.assertEqual(
            [model.slug for model in asyncio.run(default_manager.raw_model_catalog()).models],
            ["openai.gpt-5.4", "openai.gpt-oss-120b", "openai.gpt-oss-20b"],
        )
        self.assertIsInstance(custom_manager, StaticModelsManager)
        self.assertEqual(
            [model.slug for model in asyncio.run(custom_manager.raw_model_catalog()).models],
            ["custom-bedrock-model"],
        )


if __name__ == "__main__":
    unittest.main()
