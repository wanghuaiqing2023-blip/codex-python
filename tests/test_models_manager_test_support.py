from dataclasses import replace

from pycodex.models_manager import ModelsManagerConfig
from pycodex.models_manager.test_support import (
    construct_model_info_offline_for_tests,
    get_model_offline_for_tests,
)
from pycodex.models_manager.model_info import model_info_from_slug
from pycodex.protocol import ModelVisibility, ModelsResponse


def _catalog_model(slug: str, *, priority: int = 0, visibility: ModelVisibility = ModelVisibility.LIST):
    return replace(
        model_info_from_slug(slug),
        display_name=f"{slug} display",
        visibility=visibility,
        priority=priority,
        used_fallback_model_metadata=False,
    )


def _catalog_model_mapping(slug: str, *, priority: int = 0, visibility: ModelVisibility = ModelVisibility.LIST):
    model = _catalog_model(slug, priority=priority, visibility=visibility)
    return {
        "slug": model.slug,
        "display_name": model.display_name,
        "description": model.description,
        "supported_reasoning_levels": [],
        "shell_type": model.shell_type.value,
        "visibility": model.visibility.value,
        "supported_in_api": model.supported_in_api,
        "priority": model.priority,
        "additional_speed_tiers": [],
        "service_tiers": [],
        "default_service_tier": model.default_service_tier,
        "availability_nux": None,
        "upgrade": None,
        "base_instructions": model.base_instructions,
        "model_messages": None,
        "supports_reasoning_summaries": model.supports_reasoning_summaries,
        "default_reasoning_summary": model.default_reasoning_summary.value,
        "support_verbosity": model.support_verbosity,
        "default_verbosity": model.default_verbosity.value if model.default_verbosity is not None else None,
        "apply_patch_tool_type": (
            model.apply_patch_tool_type.value if model.apply_patch_tool_type is not None else None
        ),
        "web_search_tool_type": model.web_search_tool_type.value,
        "truncation_policy": model.truncation_policy.to_mapping(),
        "supports_parallel_tool_calls": model.supports_parallel_tool_calls,
        "supports_image_detail_original": model.supports_image_detail_original,
        "context_window": model.context_window,
        "max_context_window": model.max_context_window,
        "auto_compact_token_limit": model.auto_compact_token_limit_value,
        "effective_context_window_percent": model.effective_context_window_percent,
        "experimental_supported_tools": [],
        "input_modalities": [item.value for item in model.input_modalities],
        "supports_search_tool": model.supports_search_tool,
    }


def test_get_model_offline_for_tests_uses_explicit_model_or_bundled_default() -> None:
    # Rust crate/module: codex-models-manager::test_support::get_model_offline_for_tests
    assert get_model_offline_for_tests("custom-model") == "custom-model"
    assert get_model_offline_for_tests()


def test_get_model_offline_for_tests_prefers_first_visible_by_priority(monkeypatch) -> None:
    # Rust source: bundled models are sorted by priority, then the first
    # show_in_picker preset is selected, falling back to the first preset.
    from pycodex.models_manager import test_support

    monkeypatch.setattr(
        test_support,
        "bundled_models_response",
        lambda: {
            "models": [
                _catalog_model_mapping("later-visible", priority=2, visibility=ModelVisibility.LIST),
                _catalog_model_mapping("visible", priority=1, visibility=ModelVisibility.LIST),
                _catalog_model_mapping("hidden", priority=0, visibility=ModelVisibility.HIDE),
            ]
        },
    )

    assert get_model_offline_for_tests() == "visible"

    monkeypatch.setattr(
        test_support,
        "bundled_models_response",
        lambda: {
            "models": [
                _catalog_model_mapping("visible", priority=1, visibility=ModelVisibility.HIDE),
                _catalog_model_mapping("hidden", priority=0, visibility=ModelVisibility.HIDE),
            ]
        },
    )

    assert get_model_offline_for_tests() == "hidden"


def test_construct_model_info_offline_for_tests_uses_config_catalog_and_overrides() -> None:
    # Rust crate/module: codex-models-manager::test_support::construct_model_info_offline_for_tests
    config = ModelsManagerConfig(
        model_context_window=1234,
        model_catalog=ModelsResponse((_catalog_model("gpt-test"),)),
    )

    info = construct_model_info_offline_for_tests("gpt-test-preview", config)

    assert info.slug == "gpt-test-preview"
    assert info.display_name == "gpt-test display"
    assert info.context_window == 1234
    assert info.used_fallback_model_metadata is False
