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
    PERSONALITY_PLACEHOLDER,
    ReasoningEffort,
    ReasoningEffortPreset,
    ReasoningSummary,
    SERVICE_TIER_DEFAULT_REQUEST_VALUE,
    SPEED_TIER_FAST,
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


test_model.__test__ = False


class ProtocolOpenAiModelsTests(unittest.TestCase):
    def test_reasoning_effort_from_str_accepts_known_values_and_rejects_unknown(self):
        # Rust parity: codex-protocol/src/openai_models.rs
        # tests reasoning_effort_from_str_accepts_known_values and
        # reasoning_effort_from_str_rejects_unknown_values.
        self.assertEqual(ReasoningEffort.parse("high"), ReasoningEffort.HIGH)
        self.assertEqual(ReasoningEffort.parse("minimal"), ReasoningEffort.MINIMAL)
        self.assertEqual(ReasoningEffort.parse("max"), ReasoningEffort.MAX)
        self.assertEqual(ReasoningEffort.parse("ultra"), ReasoningEffort.ULTRA)
        with self.assertRaisesRegex(ValueError, "invalid ReasoningEffort value `unsupported`"):
            ReasoningEffort.parse("unsupported")

    def test_gpt_5_6_reasoning_efforts_parse_from_model_catalog(self):
        # Rust owner: codex-protocol::openai_models. Newer Codex model-cache
        # payloads advertise GPT-5.6 Sol with max and ultra reasoning levels;
        # the shared protocol must parse the catalog before TUI model_popups
        # can project it.
        payload = _model_info_payload()
        payload["slug"] = "gpt-5.6-sol"
        payload["supported_reasoning_levels"] = [
            {"effort": "max", "description": "Maximum reasoning depth"},
            {"effort": "ultra", "description": "Automatic task delegation"},
        ]

        model = ModelInfo.from_mapping(payload)

        self.assertEqual(
            [preset.effort for preset in model.supported_reasoning_levels],
            [ReasoningEffort.MAX, ReasoningEffort.ULTRA],
        )

    def test_input_modality_defaults_and_explicit_values(self):
        # Rust parity: codex-protocol/src/openai_models.rs
        # ModelInfo::default_input_modalities returns text then image, while
        # deserialized model metadata may narrow the supported modalities.
        self.assertEqual(default_input_modalities(), (InputModality.TEXT, InputModality.IMAGE))
        self.assertEqual(InputModality.TEXT.value, "text")
        self.assertEqual(InputModality.IMAGE.value, "image")

        defaulted = ModelInfo.from_mapping(_model_info_payload())
        explicit = ModelInfo.from_mapping(_model_info_payload(input_modalities=["text"]))

        self.assertEqual(defaulted.input_modalities, (InputModality.TEXT, InputModality.IMAGE))
        self.assertEqual(explicit.input_modalities, (InputModality.TEXT,))

    def test_model_instructions_uses_template(self):
        # Rust parity: codex-protocol/src/openai_models.rs
        # get_model_instructions_uses_template_when_placeholder_present.
        model = test_model(ModelMessages(f"Hello {PERSONALITY_PLACEHOLDER}", personality_variables()))

        self.assertEqual(model.get_model_instructions(Personality.FRIENDLY), "Hello friendly")
        self.assertTrue(model.supports_personality())

    def test_model_instructions_always_strips_placeholder(self):
        # Rust parity: codex-protocol/src/openai_models.rs
        # get_model_instructions_always_strips_placeholder.
        model = test_model(
            ModelMessages(
                f"Hello\n{PERSONALITY_PLACEHOLDER}",
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
        # Rust parity: codex-protocol/src/openai_models.rs
        # model_info_defaults_availability_nux_to_none_when_omitted plus
        # Python coverage for Rust ModelInfo serde(default) fields.
        model = ModelInfo.from_mapping(_model_info_payload())

        self.assertIsNone(model.availability_nux)
        self.assertFalse(model.supports_image_detail_original)
        self.assertEqual(model.web_search_tool_type, WebSearchToolType.TEXT)
        self.assertFalse(model.supports_search_tool)
        self.assertEqual(model.input_modalities, (InputModality.TEXT, InputModality.IMAGE))
        self.assertEqual(model.default_reasoning_summary, ReasoningSummary.AUTO)
        self.assertEqual(model.effective_context_window_percent, 95)

    def test_model_info_from_mapping_rejects_non_rust_wire_shapes(self):
        payload = _model_info_payload()
        payload["supports_search_tool"] = "yes"
        with self.assertRaisesRegex(TypeError, "supports_search_tool must be a bool"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["supports_image_detail_original"] = 1
        with self.assertRaisesRegex(TypeError, "supports_image_detail_original must be a bool"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["input_modalities"] = ["text", 5]
        with self.assertRaisesRegex(TypeError, "input_modalities entries must be strings"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["additional_speed_tiers"] = ["fast", 5]
        with self.assertRaisesRegex(TypeError, "additional_speed_tiers entries must be strings"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["experimental_supported_tools"] = ["web_search", 5]
        with self.assertRaisesRegex(TypeError, "experimental_supported_tools entries must be strings"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["priority"] = 2**31
        with self.assertRaisesRegex(ValueError, "priority must fit in i32"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["truncation_policy"] = {"mode": "bytes", "limit": 2**63}
        with self.assertRaisesRegex(ValueError, "limit must fit in i64"):
            ModelInfo.from_mapping(payload)

        payload = _model_info_payload()
        payload["effective_context_window_percent"] = 0
        self.assertEqual(ModelInfo.from_mapping(payload).effective_context_window_percent, 0)

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
        # Rust parity: codex-protocol/src/openai_models.rs
        # model_preset_supports_fast_mode_from_service_tiers.
        preset = ModelPreset.from_model_info(
            ModelInfo(**_model_kwargs(
                test_model(),
                service_tiers=(ModelServiceTier(SPEED_TIER_FAST, "Fast", "Priority"),),
            ))
        )

        self.assertTrue(preset.supports_fast_mode())

    def test_service_tier_for_request(self):
        # Rust parity: codex-protocol/src/openai_models.rs
        # service_tier_for_request_omits_explicit_default_tier,
        # service_tier_for_request_filters_unsupported_tiers, and
        # service_tier_for_request_does_not_apply_catalog_default.
        model = ModelInfo(**_model_kwargs(
            test_model(),
            default_service_tier=ServiceTier.FAST.request_value(),
            service_tiers=(ModelServiceTier(ServiceTier.FAST.request_value(), "Fast", "Priority"),),
        ))

        self.assertIsNone(model.service_tier_for_request(SERVICE_TIER_DEFAULT_REQUEST_VALUE))
        self.assertEqual(model.service_tier_for_request(ServiceTier.FAST.request_value()), "priority")
        self.assertIsNone(model.service_tier_for_request("unsupported"))
        self.assertIsNone(model.service_tier_for_request(None))

        catalog_default_only = ModelInfo(**_model_kwargs(
            test_model(),
            default_service_tier=ServiceTier.FAST.request_value(),
            service_tiers=(ModelServiceTier(ServiceTier.FAST.request_value(), "Fast", "Priority"),),
        ))
        self.assertIsNone(catalog_default_only.service_tier_for_request(None))

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


def _model_info_payload(**overrides) -> dict:
    data = {
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
    data.update(overrides)
    return data


if __name__ == "__main__":
    unittest.main()
