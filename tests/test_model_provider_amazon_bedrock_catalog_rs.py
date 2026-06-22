import unittest

from pycodex.model_provider.amazon_bedrock.catalog import (
    GPT_5_4_CONTEXT_WINDOW,
    GPT_5_4_MAX_CONTEXT_WINDOW,
    GPT_OSS_CONTEXT_WINDOW,
    bedrock_oss_model,
    gpt_5_4_cmb_reasoning_levels,
    reasoning_effort_preset,
    static_model_catalog,
)
from pycodex.model_provider_info import AMAZON_BEDROCK_GPT_5_4_MODEL_ID
from pycodex.models_manager.model_info import BASE_INSTRUCTIONS
from pycodex.protocol.config_types import ReasoningEffort, ReasoningSummary, ServiceTier, Verbosity
from pycodex.protocol.openai_models import (
    ApplyPatchToolType,
    ConfigShellToolType,
    InputModality,
    ModelVisibility,
    SPEED_TIER_FAST,
    TruncationMode,
    WebSearchToolType,
)


class ModelProviderAmazonBedrockCatalogRsTests(unittest.TestCase):
    def test_catalog_uses_mantle_model_ids_as_slugs(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/catalog.rs
        # catalog_uses_mantle_model_ids_as_slugs.
        catalog = static_model_catalog()

        self.assertEqual(len(catalog.models), 3)
        self.assertEqual(catalog.models[0].slug, AMAZON_BEDROCK_GPT_5_4_MODEL_ID)
        self.assertEqual(catalog.models[1].slug, "openai.gpt-oss-120b")
        self.assertEqual(catalog.models[2].slug, "openai.gpt-oss-20b")

    def test_gpt_5_4_cmb_advertises_only_bedrock_supported_reasoning_levels(self) -> None:
        # Rust crate/module/test: codex-model-provider/src/amazon_bedrock/catalog.rs
        # gpt_5_4_cmb_advertises_only_bedrock_supported_reasoning_levels.
        catalog = static_model_catalog()
        model = next(item for item in catalog.models if item.slug == AMAZON_BEDROCK_GPT_5_4_MODEL_ID)

        self.assertEqual(model.supported_reasoning_levels, tuple(gpt_5_4_cmb_reasoning_levels()))

    def test_gpt_5_4_cmb_model_fields_match_rust_static_metadata(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/catalog.rs
        # gpt_5_4_cmb_bedrock_model field construction.
        model = static_model_catalog().models[0]

        self.assertEqual(model.display_name, "gpt-5.4")
        self.assertEqual(model.description, "Strong model for everyday coding.")
        self.assertEqual(model.default_reasoning_level, ReasoningEffort.MEDIUM)
        self.assertEqual(model.shell_type, ConfigShellToolType.SHELL_COMMAND)
        self.assertEqual(model.visibility, ModelVisibility.LIST)
        self.assertTrue(model.supported_in_api)
        self.assertEqual(model.priority, 0)
        self.assertEqual(model.service_tiers[0].id, ServiceTier.FAST.request_value())
        self.assertEqual(model.service_tiers[0].name, SPEED_TIER_FAST)
        self.assertEqual(model.service_tiers[0].description, "Fastest inference with increased plan usage")
        self.assertIsNone(model.default_service_tier)
        self.assertIsNone(model.upgrade)
        self.assertEqual(model.base_instructions, BASE_INSTRUCTIONS)
        self.assertIsNone(model.model_messages)
        self.assertTrue(model.supports_reasoning_summaries)
        self.assertEqual(model.default_reasoning_summary, ReasoningSummary.NONE)
        self.assertTrue(model.support_verbosity)
        self.assertEqual(model.default_verbosity, Verbosity.MEDIUM)
        self.assertEqual(model.apply_patch_tool_type, ApplyPatchToolType.FREEFORM)
        self.assertEqual(model.web_search_tool_type, WebSearchToolType.TEXT_AND_IMAGE)
        self.assertEqual(model.truncation_policy.mode, TruncationMode.TOKENS)
        self.assertEqual(model.truncation_policy.limit, 10_000)
        self.assertTrue(model.supports_parallel_tool_calls)
        self.assertTrue(model.supports_image_detail_original)
        self.assertEqual(model.context_window, GPT_5_4_CONTEXT_WINDOW)
        self.assertEqual(model.max_context_window, GPT_5_4_MAX_CONTEXT_WINDOW)
        self.assertIsNone(model.auto_compact_token_limit_value)
        self.assertEqual(model.effective_context_window_percent, 95)
        self.assertEqual(model.experimental_supported_tools, ())
        self.assertEqual(model.input_modalities, (InputModality.TEXT, InputModality.IMAGE))
        self.assertFalse(model.used_fallback_model_metadata)
        self.assertTrue(model.supports_search_tool)

    def test_bedrock_oss_model_fields_match_rust_static_metadata(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/catalog.rs
        # bedrock_oss_model field construction.
        model = bedrock_oss_model("openai.gpt-oss-test", "GPT OSS Test", 7)

        self.assertEqual(model.slug, "openai.gpt-oss-test")
        self.assertEqual(model.display_name, "GPT OSS Test")
        self.assertEqual(model.description, "GPT OSS Test")
        self.assertEqual(model.default_reasoning_level, ReasoningEffort.MEDIUM)
        self.assertEqual(
            [preset.effort for preset in model.supported_reasoning_levels],
            [ReasoningEffort.LOW, ReasoningEffort.MEDIUM, ReasoningEffort.HIGH],
        )
        self.assertEqual(model.shell_type, ConfigShellToolType.SHELL_COMMAND)
        self.assertEqual(model.visibility, ModelVisibility.LIST)
        self.assertTrue(model.supported_in_api)
        self.assertEqual(model.priority, 7)
        self.assertEqual(model.service_tiers, ())
        self.assertEqual(model.base_instructions, BASE_INSTRUCTIONS)
        self.assertTrue(model.supports_reasoning_summaries)
        self.assertEqual(model.default_reasoning_summary, ReasoningSummary.NONE)
        self.assertFalse(model.support_verbosity)
        self.assertIsNone(model.default_verbosity)
        self.assertIsNone(model.apply_patch_tool_type)
        self.assertEqual(model.web_search_tool_type, WebSearchToolType.TEXT)
        self.assertEqual(model.truncation_policy.mode, TruncationMode.TOKENS)
        self.assertEqual(model.truncation_policy.limit, 10_000)
        self.assertTrue(model.supports_parallel_tool_calls)
        self.assertFalse(model.supports_image_detail_original)
        self.assertEqual(model.context_window, GPT_OSS_CONTEXT_WINDOW)
        self.assertEqual(model.max_context_window, GPT_OSS_CONTEXT_WINDOW)
        self.assertEqual(model.input_modalities, (InputModality.TEXT,))
        self.assertFalse(model.supports_search_tool)

    def test_reasoning_effort_preset_descriptions_match_rust(self) -> None:
        # Rust crate/module/contract: codex-model-provider/src/amazon_bedrock/catalog.rs
        # reasoning_effort_preset maps every ReasoningEffort description.
        expected = {
            ReasoningEffort.NONE: "No reasoning",
            ReasoningEffort.MINIMAL: "Minimal reasoning",
            ReasoningEffort.LOW: "Fast responses with lighter reasoning",
            ReasoningEffort.MEDIUM: "Balances speed and reasoning depth for everyday tasks",
            ReasoningEffort.HIGH: "Greater reasoning depth for complex problems",
            ReasoningEffort.XHIGH: "Extra high reasoning depth for complex problems",
        }

        self.assertEqual(
            {effort: reasoning_effort_preset(effort).description for effort in expected},
            expected,
        )


if __name__ == "__main__":
    unittest.main()
