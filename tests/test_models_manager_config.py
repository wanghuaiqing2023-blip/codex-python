import pytest

from pycodex.models_manager import ModelsManagerConfig, model_info_from_slug, with_config_overrides
from pycodex.protocol import ModelsResponse


def test_models_manager_config_defaults_match_rust_default() -> None:
    # Rust crate/module: codex-models-manager::config
    # Behavior contract: derived Default leaves options unset and personality disabled.
    config = ModelsManagerConfig()

    assert config.model_context_window is None
    assert config.model_auto_compact_token_limit is None
    assert config.tool_output_token_limit is None
    assert config.base_instructions is None
    assert config.personality_enabled is False
    assert config.model_supports_reasoning_summaries is None
    assert config.model_catalog is None
    assert config.to_mapping() == {}


def test_models_manager_config_from_mapping_parses_supported_fields() -> None:
    config = ModelsManagerConfig.from_mapping(
        {
            "model_context_window": 123,
            "model_auto_compact_token_limit": 100,
            "tool_output_token_limit": 50,
            "base_instructions": "base",
            "personality_enabled": True,
            "model_supports_reasoning_summaries": True,
            "model_catalog": {"models": []},
        }
    )

    assert config.model_context_window == 123
    assert config.model_auto_compact_token_limit == 100
    assert config.tool_output_token_limit == 50
    assert config.base_instructions == "base"
    assert config.personality_enabled is True
    assert config.model_supports_reasoning_summaries is True
    assert config.model_catalog == ModelsResponse()
    assert config.to_mapping()["model_catalog"] == ModelsResponse()


def test_models_manager_config_accepts_models_response_catalog() -> None:
    catalog = ModelsResponse()

    assert ModelsManagerConfig(model_catalog=catalog).model_catalog is catalog


def test_models_manager_config_rejects_non_rust_field_shapes() -> None:
    with pytest.raises(TypeError, match="model_context_window"):
        ModelsManagerConfig(model_context_window=True)
    with pytest.raises(TypeError, match="tool_output_token_limit"):
        ModelsManagerConfig(tool_output_token_limit="50")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="base_instructions"):
        ModelsManagerConfig(base_instructions=123)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="personality_enabled"):
        ModelsManagerConfig(personality_enabled=None)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="model_supports_reasoning_summaries"):
        ModelsManagerConfig(model_supports_reasoning_summaries="yes")  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="model_catalog"):
        ModelsManagerConfig(model_catalog=[])  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="unknown"):
        ModelsManagerConfig.from_mapping({"unknown": True})


def test_models_manager_config_feeds_model_info_overrides() -> None:
    # Integration edge: model_info::with_config_overrides consumes this config shape.
    model = model_info_from_slug("unknown-model")
    config = ModelsManagerConfig(model_context_window=1_000, model_supports_reasoning_summaries=True)

    updated = with_config_overrides(model, config)

    assert updated.context_window == 1_000
    assert updated.supports_reasoning_summaries is True
