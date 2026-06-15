from dataclasses import replace
from pathlib import Path

from pycodex.models_manager import (
    BASE_INSTRUCTIONS,
    ModelsManagerConfig,
    local_personality_messages_for_slug,
    model_info_from_slug,
    with_config_overrides,
)
from pycodex.protocol import TruncationPolicyConfig
from pycodex.utils.string import approx_bytes_for_tokens


def test_model_info_from_slug_matches_rust_fallback_contract() -> None:
    # Rust crate/module: codex-models-manager::model_info
    # Behavior contract: model_info_from_slug builds fallback model metadata.
    model = model_info_from_slug("unknown-model")

    assert model.slug == "unknown-model"
    assert model.display_name == "unknown-model"
    assert model.visibility.value == "none"
    assert model.supported_in_api is True
    assert model.priority == 99
    assert model.truncation_policy == TruncationPolicyConfig.bytes(10_000)
    assert model.context_window == 272_000
    assert model.max_context_window == 272_000
    assert model.effective_context_window_percent == 95
    assert model.used_fallback_model_metadata is True
    assert model.base_instructions == BASE_INSTRUCTIONS


def test_base_instructions_come_from_rust_prompt_fixture() -> None:
    # Rust source: model_info.rs const BASE_INSTRUCTIONS = include_str!("../prompt.md").
    prompt = Path("codex/codex-rs/models-manager/prompt.md").read_text(encoding="utf-8")

    assert BASE_INSTRUCTIONS == prompt


def test_local_personality_messages_are_enabled_for_matching_slugs() -> None:
    # Rust source: local_personality_messages_for_slug.
    messages = local_personality_messages_for_slug("gpt-5.2-codex")

    assert messages is not None
    assert "{{ personality }}" in (messages.instructions_template or "")
    assert messages.instructions_variables is not None
    assert messages.instructions_variables.personality_default == ""
    assert local_personality_messages_for_slug("unknown-model") is None


def test_reasoning_summaries_override_true_enables_support() -> None:
    # Rust test: model_info_tests.rs::reasoning_summaries_override_true_enables_support.
    model = model_info_from_slug("unknown-model")
    updated = with_config_overrides(
        model,
        ModelsManagerConfig(model_supports_reasoning_summaries=True),
    )

    assert updated == replace(model, supports_reasoning_summaries=True)


def test_reasoning_summaries_override_false_does_not_disable_support() -> None:
    # Rust tests: false override is no-op when model support is true or false.
    model = replace(model_info_from_slug("unknown-model"), supports_reasoning_summaries=True)

    assert with_config_overrides(model, ModelsManagerConfig(model_supports_reasoning_summaries=False)) == model
    fallback = model_info_from_slug("unknown-model")
    assert with_config_overrides(fallback, ModelsManagerConfig(model_supports_reasoning_summaries=False)) == fallback


def test_model_context_window_override_clamps_to_max_context_window() -> None:
    # Rust test: model_info_tests.rs::model_context_window_override_clamps_to_max_context_window.
    model = replace(model_info_from_slug("unknown-model"), context_window=273_000, max_context_window=400_000)
    updated = with_config_overrides(model, ModelsManagerConfig(model_context_window=500_000))

    assert updated == replace(model, context_window=400_000)


def test_model_context_window_uses_model_value_without_override() -> None:
    # Rust test: model_info_tests.rs::model_context_window_uses_model_value_without_override.
    model = replace(model_info_from_slug("unknown-model"), context_window=273_000, max_context_window=400_000)

    assert with_config_overrides(model, ModelsManagerConfig()) == model


def test_tool_output_token_override_preserves_rust_truncation_mode_semantics() -> None:
    # Rust source: with_config_overrides switches bytes mode through approx_bytes_for_tokens
    # and tokens mode through the token limit directly.
    byte_model = model_info_from_slug("unknown-model")
    token_model = replace(byte_model, truncation_policy=TruncationPolicyConfig.tokens(10_000))

    assert with_config_overrides(
        byte_model,
        ModelsManagerConfig(tool_output_token_limit=123),
    ).truncation_policy == TruncationPolicyConfig.bytes(approx_bytes_for_tokens(123))
    assert with_config_overrides(
        token_model,
        ModelsManagerConfig(tool_output_token_limit=123),
    ).truncation_policy == TruncationPolicyConfig.tokens(123)


def test_base_instructions_override_clears_model_messages() -> None:
    # Rust source: explicit base_instructions replaces the base prompt and disables model_messages.
    model = model_info_from_slug("gpt-5.2-codex")
    assert model.model_messages is not None

    updated = with_config_overrides(model, ModelsManagerConfig(base_instructions="custom"))

    assert updated.base_instructions == "custom"
    assert updated.model_messages is None


def test_personality_disabled_clears_model_messages_without_base_override() -> None:
    # Rust source: !personality_enabled clears model_messages when no base override is present.
    model = model_info_from_slug("gpt-5.2-codex")

    disabled = with_config_overrides(model, ModelsManagerConfig(personality_enabled=False))
    enabled = with_config_overrides(model, ModelsManagerConfig(personality_enabled=True))

    assert disabled.model_messages is None
    assert enabled.model_messages == model.model_messages
