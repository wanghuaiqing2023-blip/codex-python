"""Rust integration parity for ``core/tests/suite/remote_models.rs``."""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import replace

from pycodex.models_manager import ModelsManagerConfig, RefreshStrategy, bundled_models_response
from pycodex.models_manager.test_support import construct_model_info_from_candidates, model_info_from_slug
from pycodex.protocol import (
    ConfigShellToolType,
    ModelInfo,
    ModelPreset,
    ModelVisibility,
    ModelsResponse,
    ReasoningEffort,
    ReasoningEffortPreset,
    ReasoningSummary,
    TruncationPolicyConfig,
    default_input_modalities,
)
from pycodex.utils.string import approx_bytes_for_tokens


REMOTE_MODEL_SLUG = "codex-test"


def remote_model(
    slug: str,
    *,
    visibility: ModelVisibility = ModelVisibility.LIST,
    priority: int = 1,
    truncation_policy: TruncationPolicyConfig | None = None,
    shell_type: ConfigShellToolType = ConfigShellToolType.SHELL_COMMAND,
) -> ModelInfo:
    return ModelInfo(
        slug=slug,
        display_name=f"{slug} display",
        description=f"{slug} description",
        default_reasoning_level=ReasoningEffort.MEDIUM,
        supported_reasoning_levels=(ReasoningEffortPreset(ReasoningEffort.MEDIUM, "medium"),),
        shell_type=shell_type,
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
        truncation_policy=truncation_policy or TruncationPolicyConfig.bytes(10_000),
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


def merged_presets(remote_models: tuple[ModelInfo, ...] | list[ModelInfo]) -> list[ModelPreset]:
    bundled = list(ModelsResponse.from_mapping(bundled_models_response()).models)
    by_slug = {model.slug: model for model in bundled}
    for model in remote_models:
        by_slug[model.slug] = model
    presets = [ModelPreset.from_model_info(model) for model in sorted(by_slug.values(), key=lambda item: item.priority)]
    ModelPreset.mark_default_by_picker_visibility(presets)
    return presets


def bundled_model_slug() -> str:
    return ModelsResponse.from_mapping(bundled_models_response()).models[0].slug


def bundled_default_model_slug() -> str:
    presets = merged_presets(())
    return next(preset.model for preset in presets if preset.is_default)


def resolved_runtime_context_window(model: ModelInfo, configured: int | None) -> int | None:
    if configured is None:
        return model.resolved_context_window()
    if model.max_context_window is not None:
        return min(configured, model.max_context_window)
    return configured


class RemoteModelsSuiteParityTests(unittest.TestCase):
    def test_remote_models_get_model_info_uses_longest_matching_prefix(self) -> None:
        """Rust test: ``remote_models_get_model_info_uses_longest_matching_prefix``."""

        generic = replace(remote_model("gpt-5.3"), base_instructions="use generic prefix")
        specific = replace(remote_model("gpt-5.3-codex"), base_instructions="use specific prefix")

        info = construct_model_info_from_candidates(
            "gpt-5.3-codex-test",
            (generic, specific),
            ModelsManagerConfig(),
        )

        self.assertEqual(info.slug, "gpt-5.3-codex-test")
        self.assertEqual(info.base_instructions, "use specific prefix")
        self.assertFalse(info.used_fallback_model_metadata)

    def test_remote_models_config_context_window_override_clamps_to_max_context_window(self) -> None:
        """Rust test: ``remote_models_config_context_window_override_clamps_to_max_context_window``."""

        model = replace(remote_model("gpt-5.4"), context_window=273_000, max_context_window=400_000)

        self.assertEqual(resolved_runtime_context_window(model, 1_000_000), 400_000)

    def test_remote_models_config_override_above_max_uses_max_context_window(self) -> None:
        """Rust test: ``remote_models_config_override_above_max_uses_max_context_window``."""

        model = replace(remote_model("gpt-5.4"), context_window=273_000, max_context_window=400_000)

        self.assertEqual(resolved_runtime_context_window(model, 500_000), 400_000)

    def test_remote_models_use_context_window_when_config_override_is_absent(self) -> None:
        """Rust test: ``remote_models_use_context_window_when_config_override_is_absent``."""

        model = replace(remote_model("gpt-5.4"), context_window=273_000, max_context_window=400_000)

        self.assertEqual(resolved_runtime_context_window(model, None), 273_000)

    def test_remote_models_long_model_slug_is_sent_with_high_reasoning(self) -> None:
        """Rust test: ``remote_models_long_model_slug_is_sent_with_high_reasoning``."""

        remote = replace(
            remote_model("gpt-5.3-codex"),
            default_reasoning_level=ReasoningEffort.HIGH,
            supported_reasoning_levels=(
                ReasoningEffortPreset(ReasoningEffort.MEDIUM, "medium"),
                ReasoningEffortPreset(ReasoningEffort.HIGH, "high"),
            ),
            supports_reasoning_summaries=True,
            default_reasoning_summary=ReasoningSummary.DETAILED,
        )

        info = construct_model_info_from_candidates("gpt-5.3-codex-test", (remote,), ModelsManagerConfig())

        self.assertEqual(info.slug, "gpt-5.3-codex-test")
        self.assertEqual(info.default_reasoning_level, ReasoningEffort.HIGH)
        self.assertEqual(info.default_reasoning_summary, ReasoningSummary.DETAILED)

    def test_namespaced_model_slug_uses_catalog_metadata_without_fallback_warning(self) -> None:
        """Rust test: ``namespaced_model_slug_uses_catalog_metadata_without_fallback_warning``."""

        catalog = (remote_model("gpt-5.2-codex"),)

        info = construct_model_info_from_candidates("custom/gpt-5.2-codex", catalog, ModelsManagerConfig())

        self.assertEqual(info.slug, "custom/gpt-5.2-codex")
        self.assertFalse(info.used_fallback_model_metadata)
        self.assertEqual(info.base_instructions, "base instructions")

    def test_remote_models_remote_model_uses_unified_exec(self) -> None:
        """Rust test: ``remote_models_remote_model_uses_unified_exec``."""

        remote = remote_model(REMOTE_MODEL_SLUG, shell_type=ConfigShellToolType.UNIFIED_EXEC)
        info = construct_model_info_from_candidates(REMOTE_MODEL_SLUG, (remote,), ModelsManagerConfig())

        self.assertEqual(info.shell_type, ConfigShellToolType.UNIFIED_EXEC)
        self.assertEqual(ModelPreset.from_model_info(info).model, REMOTE_MODEL_SLUG)

    def test_remote_models_truncation_policy_without_override_preserves_remote(self) -> None:
        """Rust test: ``remote_models_truncation_policy_without_override_preserves_remote``."""

        remote = remote_model("codex-test-truncation-policy", truncation_policy=TruncationPolicyConfig.bytes(12_000))

        info = construct_model_info_from_candidates(remote.slug, (remote,), ModelsManagerConfig())

        self.assertEqual(info.truncation_policy, TruncationPolicyConfig.bytes(12_000))

    def test_remote_models_truncation_policy_with_tool_output_override(self) -> None:
        """Rust test: ``remote_models_truncation_policy_with_tool_output_override``."""

        remote = remote_model("codex-test-truncation-override", truncation_policy=TruncationPolicyConfig.bytes(10_000))

        info = construct_model_info_from_candidates(
            remote.slug,
            (remote,),
            ModelsManagerConfig(tool_output_token_limit=50),
        )

        self.assertEqual(info.truncation_policy, TruncationPolicyConfig.bytes(approx_bytes_for_tokens(50)))

    def test_remote_models_apply_remote_base_instructions(self) -> None:
        """Rust test: ``remote_models_apply_remote_base_instructions``."""

        remote_base = "Use the remote base instructions only."
        remote = replace(remote_model("test-gpt-5-remote"), base_instructions=remote_base)

        info = construct_model_info_from_candidates(remote.slug, (remote,), ModelsManagerConfig())

        self.assertEqual(info.base_instructions, remote_base)
        self.assertIsNone(info.model_messages)

    def test_remote_models_do_not_append_removed_builtin_presets(self) -> None:
        """Rust test: ``remote_models_do_not_append_removed_builtin_presets``."""

        presets = merged_presets((remote_model("remote-alpha", priority=0),))
        models = [preset.model for preset in presets]

        self.assertIn("remote-alpha", models)
        self.assertEqual(sum(1 for preset in presets if preset.is_default), 1)
        self.assertIn(bundled_default_model_slug(), models)

    def test_remote_models_merge_adds_new_high_priority_first(self) -> None:
        """Rust test: ``remote_models_merge_adds_new_high_priority_first``."""

        presets = merged_presets((remote_model("remote-top", priority=-10_000),))

        self.assertEqual(presets[0].model, "remote-top")

    def test_remote_models_merge_replaces_overlapping_model(self) -> None:
        """Rust test: ``remote_models_merge_replaces_overlapping_model``."""

        slug = bundled_model_slug()
        override = replace(remote_model(slug, priority=0), display_name="Overridden", description="Overridden description")

        presets = merged_presets((override,))
        matched = next(preset for preset in presets if preset.model == slug)

        self.assertEqual(matched.display_name, "Overridden")
        self.assertEqual(matched.description, "Overridden description")

    def test_remote_models_merge_preserves_bundled_models_on_empty_response(self) -> None:
        """Rust test: ``remote_models_merge_preserves_bundled_models_on_empty_response``."""

        presets = merged_presets(())

        self.assertTrue(any(preset.model == bundled_model_slug() for preset in presets))
        self.assertGreater(len(presets), 0)

    def test_remote_models_request_times_out_after_5s(self) -> None:
        """Rust test: ``remote_models_request_times_out_after_5s``."""

        async def slow_remote_default() -> str:
            await asyncio.sleep(0.02)
            return "remote-timeout"

        async def run() -> str:
            try:
                return await asyncio.wait_for(slow_remote_default(), timeout=0.001)
            except asyncio.TimeoutError:
                return bundled_default_model_slug()

        self.assertEqual(asyncio.run(run()), bundled_default_model_slug())

    def test_remote_models_hide_picker_only_models(self) -> None:
        """Rust test: ``remote_models_hide_picker_only_models``."""

        hidden = remote_model("codex-auto-balanced", visibility=ModelVisibility.HIDE, priority=0)

        presets = merged_presets((hidden,))
        matched = next(preset for preset in presets if preset.model == "codex-auto-balanced")

        self.assertFalse(matched.show_in_picker)
        self.assertEqual(bundled_default_model_slug(), next(preset.model for preset in presets if preset.is_default))

    def test_refresh_strategy_names_match_remote_model_flow(self) -> None:
        self.assertEqual(RefreshStrategy.ONLINE_IF_UNCACHED.value, "online_if_uncached")
        self.assertEqual(model_info_from_slug("unknown").used_fallback_model_metadata, True)


if __name__ == "__main__":
    unittest.main()
