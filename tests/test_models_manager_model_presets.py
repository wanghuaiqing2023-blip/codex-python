from dataclasses import replace

from pycodex.models_manager import (
    HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG,
    HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG,
    model_presets_from_models,
)
from pycodex.protocol import (
    ConfigShellToolType,
    ModelInfo,
    ModelVisibility,
    ReasoningEffort,
    ReasoningEffortPreset,
    ReasoningSummary,
    TruncationPolicyConfig,
    default_input_modalities,
)


def test_legacy_notice_keys_match_rust_constants() -> None:
    # Rust crate/module: codex-models-manager::model_presets
    assert HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG == "hide_gpt5_1_migration_prompt"
    assert HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG == "hide_gpt-5.1-codex-max_migration_prompt"


def test_model_presets_are_derived_from_active_catalog_only() -> None:
    # Rust source: hardcoded presets were removed; listings derive from active catalog.
    first = remote_model("remote-b", priority=2)
    second = remote_model("remote-a", priority=1)

    presets = model_presets_from_models((first, second))

    assert [preset.model for preset in presets] == ["remote-a", "remote-b"]
    assert sum(1 for preset in presets if preset.is_default) == 1
    assert presets[0].is_default is True


def test_default_model_prefers_first_visible_picker_entry() -> None:
    hidden = remote_model("hidden", visibility=ModelVisibility.HIDE, priority=0)
    visible = remote_model("visible", visibility=ModelVisibility.LIST, priority=1)

    presets = model_presets_from_models((hidden, visible))

    assert [preset.model for preset in presets] == ["hidden", "visible"]
    assert next(preset.model for preset in presets if preset.is_default) == "visible"


def test_default_model_falls_back_to_first_entry_when_none_visible() -> None:
    hidden = remote_model("hidden", visibility=ModelVisibility.HIDE, priority=0)
    none = replace(remote_model("none", priority=1), visibility=ModelVisibility.NONE)

    presets = model_presets_from_models((none, hidden))

    assert next(preset.model for preset in presets if preset.is_default) == "hidden"


def remote_model(
    slug: str,
    *,
    visibility: ModelVisibility = ModelVisibility.LIST,
    priority: int = 1,
) -> ModelInfo:
    return ModelInfo(
        slug=slug,
        display_name=f"{slug} display",
        description=f"{slug} description",
        default_reasoning_level=ReasoningEffort.MEDIUM,
        supported_reasoning_levels=(ReasoningEffortPreset(ReasoningEffort.MEDIUM, "medium"),),
        shell_type=ConfigShellToolType.SHELL_COMMAND,
        visibility=visibility,
        supported_in_api=True,
        priority=priority,
        additional_speed_tiers=(),
        service_tiers=(),
        default_service_tier=None,
        availability_nux=None,
        upgrade=None,
        base_instructions="base instructions",
        model_messages=None,
        supports_reasoning_summaries=False,
        default_reasoning_summary=ReasoningSummary.AUTO,
        support_verbosity=False,
        default_verbosity=None,
        apply_patch_tool_type=None,
        truncation_policy=TruncationPolicyConfig.bytes(10_000),
        supports_parallel_tool_calls=False,
        supports_image_detail_original=False,
        context_window=272_000,
        max_context_window=None,
        auto_compact_token_limit_value=None,
        effective_context_window_percent=95,
        experimental_supported_tools=(),
        input_modalities=default_input_modalities(),
        used_fallback_model_metadata=False,
        supports_search_tool=False,
    )
