import unittest

from pycodex.protocol import (
    ApplyPatchToolType,
    ConfigShellToolType,
    InputModality,
    ModelAvailabilityNux,
    ModelInfo,
    ModelInfoUpgrade,
    ModelInstructionsVariables,
    ModelMessages,
    ModelPreset,
    ModelServiceTier,
    ModelVisibility,
    Personality,
    ReasoningEffort,
    ReasoningEffortPreset,
    ReasoningSummary,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    ServiceTier,
    TruncationPolicyConfig,
    WebSearchToolType,
    default_input_modalities,
    nearest_effort,
    reasoning_effort_mapping_from_presets,
)


def personality_variables() -> ModelInstructionsVariables:
    return ModelInstructionsVariables(
        personality_default="default",
        personality_friendly="friendly",
        personality_pragmatic="pragmatic",
    )


def test_model(spec: ModelMessages | None = None) -> ModelInfo:
    return ModelInfo(
        slug="test-model",
        display_name="Test Model",
        description=None,
        default_reasoning_level=None,
        supported_reasoning_levels=(),
        shell_type=ConfigShellToolType.SHELL_COMMAND,
        visibility=ModelVisibility.LIST,
        supported_in_api=True,
        priority=1,
        upgrade=None,
        base_instructions="base",
        model_messages=spec,
        supports_reasoning_summaries=False,
        default_reasoning_summary=ReasoningSummary.AUTO,
        support_verbosity=False,
        default_verbosity=None,
        apply_patch_tool_type=None,
        web_search_tool_type=WebSearchToolType.TEXT,
        truncation_policy=TruncationPolicyConfig.bytes(10_000),
        supports_parallel_tool_calls=False,
        supports_image_detail_original=False,
        context_window=None,
        max_context_window=None,
        auto_compact_token_limit_value=None,
        effective_context_window_percent=95,
        experimental_supported_tools=(),
        input_modalities=default_input_modalities(),
        used_fallback_model_metadata=False,
        supports_search_tool=False,
    )


class ProtocolOpenAiModelsTests(unittest.TestCase):
    def test_model_instructions_uses_template(self):
        model = test_model(ModelMessages("Hello {{ personality }}", personality_variables()))

        self.assertEqual(model.get_model_instructions(Personality.FRIENDLY), "Hello friendly")
        self.assertTrue(model.supports_personality())

    def test_model_instructions_always_strips_placeholder(self):
        model = test_model(
            ModelMessages(
                "Hello\n{{ personality }}",
                ModelInstructionsVariables(personality_friendly="friendly"),
            )
        )

        self.assertEqual(model.get_model_instructions(Personality.FRIENDLY), "Hello\nfriendly")
        self.assertEqual(model.get_model_instructions(Personality.PRAGMATIC), "Hello\n")
        self.assertEqual(model.get_model_instructions(Personality.NONE), "Hello\n")
        self.assertEqual(model.get_model_instructions(None), "Hello\n")
        self.assertFalse(model.supports_personality())

    def test_model_instructions_falls_back_without_template(self):
        model = test_model(ModelMessages(None, ModelInstructionsVariables()))

        self.assertEqual(model.get_model_instructions(Personality.FRIENDLY), "base")

    def test_personality_message_selection(self):
        variables = personality_variables()

        self.assertEqual(variables.get_personality_message(None), "default")
        self.assertEqual(variables.get_personality_message(Personality.FRIENDLY), "friendly")
        self.assertEqual(variables.get_personality_message(Personality.PRAGMATIC), "pragmatic")
        self.assertEqual(variables.get_personality_message(Personality.NONE), "")

    def test_model_info_from_mapping_defaults(self):
        model = ModelInfo.from_mapping(
            {
                "slug": "test-model",
                "display_name": "Test Model",
                "description": None,
                "supported_reasoning_levels": [],
                "shell_type": "shell_command",
                "visibility": "list",
                "supported_in_api": True,
                "priority": 1,
                "upgrade": None,
                "base_instructions": "base",
                "model_messages": None,
                "supports_reasoning_summaries": False,
                "default_reasoning_summary": "auto",
                "support_verbosity": False,
                "default_verbosity": None,
                "apply_patch_tool_type": None,
                "truncation_policy": {"mode": "bytes", "limit": 10000},
                "supports_parallel_tool_calls": False,
                "context_window": None,
                "auto_compact_token_limit": None,
                "effective_context_window_percent": 95,
                "experimental_supported_tools": [],
            }
        )

        self.assertIsNone(model.availability_nux)
        self.assertFalse(model.supports_image_detail_original)
        self.assertEqual(model.web_search_tool_type, WebSearchToolType.TEXT)
        self.assertFalse(model.supports_search_tool)
        self.assertEqual(model.input_modalities, (InputModality.TEXT, InputModality.IMAGE))

    def test_resolved_context_window_and_auto_compact_limit(self):
        model = test_model()

        self.assertIsNone(model.resolved_context_window())
        self.assertIsNone(model.auto_compact_token_limit())
        self.assertEqual(ModelInfo(**_model_kwargs(model, context_window=273_000, max_context_window=400_000)).resolved_context_window(), 273_000)
        fallback = ModelInfo(**_model_kwargs(model, context_window=None, max_context_window=400_000))
        self.assertEqual(fallback.resolved_context_window(), 400_000)
        self.assertEqual(fallback.auto_compact_token_limit(), 360_000)
        clamped = ModelInfo(**_model_kwargs(model, context_window=100_000, auto_compact_token_limit_value=95_000))
        self.assertEqual(clamped.auto_compact_token_limit(), 90_000)

    def test_model_info_to_preset_preserves_fields_and_upgrade(self):
        model = ModelInfo(**_model_kwargs(
            test_model(),
            supported_reasoning_levels=(
                ReasoningEffortPreset(ReasoningEffort.LOW, "Low"),
                ReasoningEffortPreset(ReasoningEffort.HIGH, "High"),
            ),
            default_reasoning_level=ReasoningEffort.HIGH,
            availability_nux=ModelAvailabilityNux("Try Spark."),
            additional_speed_tiers=("fast",),
            default_service_tier=ServiceTier.FAST.request_value(),
            upgrade=ModelInfoUpgrade("next-model", "migrate"),
            description="desc",
        ))

        preset = model.to_preset()

        self.assertEqual(preset.id, "test-model")
        self.assertEqual(preset.description, "desc")
        self.assertEqual(preset.default_reasoning_effort, ReasoningEffort.HIGH)
        self.assertTrue(preset.supports_fast_mode())
        self.assertEqual(preset.availability_nux, ModelAvailabilityNux("Try Spark."))
        self.assertIsNotNone(preset.upgrade)
        self.assertEqual(preset.upgrade.id, "next-model")
        self.assertEqual(preset.upgrade.migration_config_key, "test-model")
        self.assertEqual(preset.upgrade.migration_markdown, "migrate")

    def test_model_preset_supports_fast_mode_from_service_tiers(self):
        preset = ModelPreset.from_model_info(
            ModelInfo(**_model_kwargs(
                test_model(),
                service_tiers=(ModelServiceTier(ServiceTier.FAST.request_value(), "Fast", "Priority"),),
            ))
        )

        self.assertTrue(preset.supports_fast_mode())

    def test_service_tier_for_request(self):
        model = ModelInfo(**_model_kwargs(
            test_model(),
            default_service_tier=ServiceTier.FAST.request_value(),
            service_tiers=(ModelServiceTier(ServiceTier.FAST.request_value(), "Fast", "Priority"),),
        ))

        self.assertIsNone(model.service_tier_for_request(SERVICE_TIER_DEFAULT_REQUEST_VALUE))
        self.assertEqual(model.service_tier_for_request(ServiceTier.FAST.request_value()), "priority")
        self.assertIsNone(model.service_tier_for_request("unsupported"))
        self.assertIsNone(model.service_tier_for_request(None))

    def test_filter_and_mark_default_by_picker_visibility(self):
        listed = ModelPreset.from_model_info(test_model())
        hidden_info = ModelInfo(**_model_kwargs(test_model(), visibility=ModelVisibility.HIDE, supported_in_api=False))
        hidden = ModelPreset.from_model_info(hidden_info)

        self.assertEqual(ModelPreset.filter_by_auth([hidden, listed], chatgpt_mode=False), [listed])
        self.assertEqual(ModelPreset.filter_by_auth([hidden, listed], chatgpt_mode=True), [hidden, listed])
        ModelPreset.mark_default_by_picker_visibility([hidden, listed])
        self.assertFalse(hidden.is_default)
        self.assertTrue(listed.is_default)

    def test_reasoning_effort_mapping_uses_nearest_supported_effort(self):
        presets = (
            ReasoningEffortPreset(ReasoningEffort.LOW, "Low"),
            ReasoningEffortPreset(ReasoningEffort.HIGH, "High"),
        )
        mapping = reasoning_effort_mapping_from_presets(presets)

        self.assertEqual(nearest_effort(ReasoningEffort.MEDIUM, (ReasoningEffort.LOW, ReasoningEffort.HIGH)), ReasoningEffort.LOW)
        self.assertEqual(mapping[ReasoningEffort.NONE], ReasoningEffort.LOW)
        self.assertEqual(mapping[ReasoningEffort.XHIGH], ReasoningEffort.HIGH)
        self.assertIsNone(reasoning_effort_mapping_from_presets(()))

    def test_truncation_and_tool_types_from_mapping(self):
        self.assertEqual(TruncationPolicyConfig.from_mapping({"mode": "tokens", "limit": 123}), TruncationPolicyConfig.tokens(123))
        self.assertEqual(ApplyPatchToolType("freeform"), ApplyPatchToolType.FREEFORM)


def _model_kwargs(model: ModelInfo, **overrides) -> dict:
    data = {
        "slug": model.slug,
        "display_name": model.display_name,
        "description": model.description,
        "default_reasoning_level": model.default_reasoning_level,
        "supported_reasoning_levels": model.supported_reasoning_levels,
        "shell_type": model.shell_type,
        "visibility": model.visibility,
        "supported_in_api": model.supported_in_api,
        "priority": model.priority,
        "additional_speed_tiers": model.additional_speed_tiers,
        "service_tiers": model.service_tiers,
        "default_service_tier": model.default_service_tier,
        "availability_nux": model.availability_nux,
        "upgrade": model.upgrade,
        "base_instructions": model.base_instructions,
        "model_messages": model.model_messages,
        "supports_reasoning_summaries": model.supports_reasoning_summaries,
        "default_reasoning_summary": model.default_reasoning_summary,
        "support_verbosity": model.support_verbosity,
        "default_verbosity": model.default_verbosity,
        "apply_patch_tool_type": model.apply_patch_tool_type,
        "web_search_tool_type": model.web_search_tool_type,
        "truncation_policy": model.truncation_policy,
        "supports_parallel_tool_calls": model.supports_parallel_tool_calls,
        "supports_image_detail_original": model.supports_image_detail_original,
        "context_window": model.context_window,
        "max_context_window": model.max_context_window,
        "auto_compact_token_limit_value": model.auto_compact_token_limit_value,
        "effective_context_window_percent": model.effective_context_window_percent,
        "experimental_supported_tools": model.experimental_supported_tools,
        "input_modalities": model.input_modalities,
        "used_fallback_model_metadata": model.used_fallback_model_metadata,
        "supports_search_tool": model.supports_search_tool,
    }
    data.update(overrides)
    return data


if __name__ == "__main__":
    unittest.main()
