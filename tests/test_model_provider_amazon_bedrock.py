import asyncio

from pycodex.model_provider import ProviderAccountState, ProviderCapabilities, create_model_provider
from pycodex.model_provider.amazon_bedrock import AmazonBedrockModelProvider, static_model_catalog
from pycodex.model_provider_info import AMAZON_BEDROCK_GPT_5_4_MODEL_ID, ModelProviderInfo
from pycodex.models_manager import RefreshStrategy, StaticModelsManager
from pycodex.models_manager.model_info import model_info_from_slug
from pycodex.protocol import ProviderAccount
from pycodex.protocol.openai_models import ModelsResponse


def test_amazon_bedrock_provider_capabilities_and_approval_model() -> None:
    # Rust crate/module: codex-model-provider::amazon_bedrock
    provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider())

    assert provider.capabilities() == ProviderCapabilities(
        namespace_tools=True,
        image_generation=False,
        web_search=False,
    )
    assert provider.approval_review_preferred_model() == AMAZON_BEDROCK_GPT_5_4_MODEL_ID
    assert provider.auth_manager() is None
    assert asyncio.run(provider.auth()) is None


def test_amazon_bedrock_provider_account_state() -> None:
    # Rust contract: Amazon Bedrock exposes an app-visible Bedrock account without OpenAI auth.
    provider = AmazonBedrockModelProvider.new(ModelProviderInfo.create_amazon_bedrock_provider())

    assert provider.account_state() == ProviderAccountState(
        account=ProviderAccount.amazon_bedrock(),
        requires_openai_auth=False,
    )


def test_amazon_bedrock_provider_creates_static_models_manager(tmp_path) -> None:
    # Rust test: amazon_bedrock_provider_creates_static_models_manager.
    provider = create_model_provider(ModelProviderInfo.create_amazon_bedrock_provider())

    manager = provider.models_manager(tmp_path, None)
    catalog = asyncio.run(manager.raw_model_catalog(RefreshStrategy.ONLINE))

    assert isinstance(manager, StaticModelsManager)
    assert [model.slug for model in catalog.models] == [
        "openai.gpt-5.4",
        "openai.gpt-oss-120b",
        "openai.gpt-oss-20b",
    ]
    default = next(preset for preset in asyncio.run(manager.list_models(RefreshStrategy.ONLINE)) if preset.is_default)
    assert default.model == "openai.gpt-5.4"


def test_amazon_bedrock_provider_uses_configured_static_catalog_when_present(tmp_path) -> None:
    # Rust test: amazon_bedrock_provider_uses_configured_static_catalog_when_present.
    custom_model = model_info_from_slug("custom-bedrock-model")
    provider = create_model_provider(ModelProviderInfo.create_amazon_bedrock_provider())

    manager = provider.models_manager(tmp_path, ModelsResponse((custom_model,)))
    catalog = asyncio.run(manager.raw_model_catalog(RefreshStrategy.ONLINE))

    assert isinstance(manager, StaticModelsManager)
    assert [model.slug for model in catalog.models] == ["custom-bedrock-model"]


def test_static_model_catalog_matches_bedrock_default_order() -> None:
    # Rust crate/module: codex-model-provider::amazon_bedrock::catalog
    catalog = static_model_catalog()

    assert [model.slug for model in catalog.models] == [
        "openai.gpt-5.4",
        "openai.gpt-oss-120b",
        "openai.gpt-oss-20b",
    ]
