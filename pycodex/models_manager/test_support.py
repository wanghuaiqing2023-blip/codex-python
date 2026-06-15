"""Test-only helpers ported from ``codex-models-manager``.

Rust source:
- ``codex/codex-rs/models-manager/src/test_support.rs``
- ``codex/codex-rs/models-manager/src/manager.rs``
- ``codex/codex-rs/models-manager/src/model_info.rs``
- ``codex/codex-rs/models-manager/src/collaboration_mode_presets.rs``
"""

from __future__ import annotations

from typing import Any

from pycodex.protocol import (
    ModelInfo,
    ModelPreset,
    ModelsResponse,
)

from . import bundled_models_response
from .collaboration_mode_presets import (
    KNOWN_MODE_NAMES_TEMPLATE_KEY,
    builtin_collaboration_mode_presets,
    default_mode_instructions,
    format_mode_names,
)
from .config import ModelsManagerConfig
from .model_info import (
    BASE_INSTRUCTIONS,
    DEFAULT_PERSONALITY_HEADER,
    LOCAL_FRIENDLY_TEMPLATE,
    LOCAL_PRAGMATIC_TEMPLATE,
    PERSONALITY_PLACEHOLDER,
    model_info_from_slug,
    with_config_overrides,
)
from .manager import construct_model_info_from_candidates
from .model_presets import model_presets_from_models

def get_model_offline_for_tests(model: str | None = None) -> str:
    """Get model identifier without consulting remote state or cache."""

    if model is not None:
        return str(model)
    presets = _bundled_model_presets()
    default = next((preset for preset in presets if preset.show_in_picker), None)
    if default is None and presets:
        default = presets[0]
    return default.model if default is not None else ""


def construct_model_info_offline_for_tests(model: str, config: ModelsManagerConfig) -> ModelInfo:
    """Build ``ModelInfo`` without consulting remote state or cache."""

    candidates = _model_catalog_models(config.model_catalog)
    return construct_model_info_from_candidates(str(model), candidates, config)


def _bundled_model_presets() -> list[ModelPreset]:
    response = ModelsResponse.from_mapping(bundled_models_response())
    return model_presets_from_models(response.models)


def _model_catalog_models(model_catalog: Any) -> tuple[ModelInfo, ...]:
    if model_catalog is None:
        return ()
    if isinstance(model_catalog, ModelsResponse):
        return model_catalog.models
    if isinstance(model_catalog, dict):
        return ModelsResponse.from_mapping(model_catalog).models
    models = getattr(model_catalog, "models", None)
    if models is None:
        return ()
    return tuple(_coerce_model_info(model) for model in models)


def _coerce_model_info(value: Any) -> ModelInfo:
    if isinstance(value, ModelInfo):
        return value
    if isinstance(value, dict):
        return ModelInfo.from_mapping(value)
    raise TypeError("model catalog entries must be ModelInfo or mapping")


def _base_instructions() -> str:
    return BASE_INSTRUCTIONS


__all__ = [
    "BASE_INSTRUCTIONS",
    "DEFAULT_PERSONALITY_HEADER",
    "KNOWN_MODE_NAMES_TEMPLATE_KEY",
    "LOCAL_FRIENDLY_TEMPLATE",
    "LOCAL_PRAGMATIC_TEMPLATE",
    "PERSONALITY_PLACEHOLDER",
    "builtin_collaboration_mode_presets",
    "construct_model_info_from_candidates",
    "construct_model_info_offline_for_tests",
    "default_mode_instructions",
    "format_mode_names",
    "get_model_offline_for_tests",
    "model_info_from_slug",
    "with_config_overrides",
]
