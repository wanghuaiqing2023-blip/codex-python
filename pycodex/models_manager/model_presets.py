"""Model preset compatibility constants for ``codex-models-manager::model_presets``."""

from __future__ import annotations

from pycodex.protocol import ModelInfo, ModelPreset


HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG = "hide_gpt5_1_migration_prompt"
HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG = "hide_gpt-5.1-codex-max_migration_prompt"


def model_presets_from_models(models: list[ModelInfo] | tuple[ModelInfo, ...]) -> list[ModelPreset]:
    """Derive sorted presets from active catalog metadata.

    Rust removed hardcoded model presets from this module; callers now derive
    listings from the active catalog and mark one visible model as default.
    """

    presets = [ModelPreset.from_model_info(model) for model in sorted(models, key=lambda item: item.priority)]
    ModelPreset.mark_default_by_picker_visibility(presets)
    return presets


__all__ = [
    "HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG",
    "HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG",
    "model_presets_from_models",
]
