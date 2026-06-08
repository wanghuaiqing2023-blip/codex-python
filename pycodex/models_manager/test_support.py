"""Test-only helpers ported from ``codex-models-manager``.

Rust source:
- ``codex/codex-rs/models-manager/src/test_support.rs``
- ``codex/codex-rs/models-manager/src/manager.rs``
- ``codex/codex-rs/models-manager/src/model_info.rs``
- ``codex/codex-rs/models-manager/src/collaboration_mode_presets.rs``
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable, Sequence

from pycodex.protocol import (
    CollaborationModeMask,
    ConfigShellToolType,
    ModelInfo,
    ModelInstructionsVariables,
    ModelMessages,
    ModelPreset,
    ModelVisibility,
    ModeKind,
    ModelsResponse,
    ReasoningEffort,
    ReasoningSummary,
    TruncationMode,
    TruncationPolicyConfig,
    WebSearchToolType,
    default_input_modalities,
)
from pycodex.utils.string import approx_bytes_for_tokens

from . import ModelsManagerConfig, bundled_models_response


KNOWN_MODE_NAMES_TEMPLATE_KEY = "{{KNOWN_MODE_NAMES}}"
DEFAULT_PERSONALITY_HEADER = (
    "You are Codex, a coding agent based on GPT-5. You and the user share the same "
    "workspace and collaborate to achieve the user's goals."
)
LOCAL_FRIENDLY_TEMPLATE = (
    "You optimize for team morale and being a supportive teammate as much as code quality."
)
LOCAL_PRAGMATIC_TEMPLATE = "You are a deeply pragmatic, effective software engineer."
PERSONALITY_PLACEHOLDER = "{{ personality }}"


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


def construct_model_info_from_candidates(
    model: str,
    candidates: Sequence[ModelInfo],
    config: ModelsManagerConfig,
) -> ModelInfo:
    remote = _find_model_by_longest_prefix(model, candidates)
    if remote is None:
        remote = _find_model_by_namespaced_suffix(model, candidates)
    if remote is not None:
        model_info = replace(remote, slug=model, used_fallback_model_metadata=False)
    else:
        model_info = model_info_from_slug(model)
    return with_config_overrides(model_info, config)


def model_info_from_slug(slug: str) -> ModelInfo:
    """Build a minimal fallback model descriptor for missing/unknown slugs."""

    return ModelInfo(
        slug=slug,
        display_name=slug,
        description=None,
        default_reasoning_level=None,
        supported_reasoning_levels=(),
        shell_type=ConfigShellToolType.DEFAULT,
        visibility=ModelVisibility.NONE,
        supported_in_api=True,
        priority=99,
        additional_speed_tiers=(),
        service_tiers=(),
        default_service_tier=None,
        availability_nux=None,
        upgrade=None,
        base_instructions=_base_instructions(),
        model_messages=_local_personality_messages_for_slug(slug),
        supports_reasoning_summaries=False,
        default_reasoning_summary=ReasoningSummary.AUTO,
        support_verbosity=False,
        default_verbosity=None,
        apply_patch_tool_type=None,
        web_search_tool_type=WebSearchToolType.TEXT,
        truncation_policy=TruncationPolicyConfig.bytes(10_000),
        supports_parallel_tool_calls=False,
        supports_image_detail_original=False,
        context_window=272_000,
        max_context_window=272_000,
        auto_compact_token_limit_value=None,
        effective_context_window_percent=95,
        experimental_supported_tools=(),
        input_modalities=default_input_modalities(),
        used_fallback_model_metadata=True,
        supports_search_tool=False,
    )


def with_config_overrides(model: ModelInfo, config: ModelsManagerConfig) -> ModelInfo:
    if config.model_supports_reasoning_summaries is True:
        model = replace(model, supports_reasoning_summaries=True)
    if config.model_context_window is not None:
        context_window = int(config.model_context_window)
        if model.max_context_window is not None:
            context_window = min(context_window, model.max_context_window)
        model = replace(model, context_window=context_window)
    if config.model_auto_compact_token_limit is not None:
        model = replace(model, auto_compact_token_limit_value=int(config.model_auto_compact_token_limit))
    if config.tool_output_token_limit is not None:
        token_limit = int(config.tool_output_token_limit)
        if model.truncation_policy.mode is TruncationMode.BYTES:
            truncation_policy = TruncationPolicyConfig.bytes(approx_bytes_for_tokens(token_limit))
        else:
            truncation_policy = TruncationPolicyConfig.tokens(token_limit)
        model = replace(model, truncation_policy=truncation_policy)
    if config.base_instructions is not None:
        model = replace(model, base_instructions=str(config.base_instructions), model_messages=None)
    elif not config.personality_enabled:
        model = replace(model, model_messages=None)
    return model


def builtin_collaboration_mode_presets() -> list[CollaborationModeMask]:
    """Return the static collaboration-mode presets used by models-manager."""

    return [_plan_preset(), _default_preset()]


def _plan_preset() -> CollaborationModeMask:
    return CollaborationModeMask(
        name=ModeKind.PLAN.display_name(),
        mode=ModeKind.PLAN,
        model=None,
        reasoning_effort=ReasoningEffort.MEDIUM,
        developer_instructions=_template_text("plan.md"),
    )


def _default_preset() -> CollaborationModeMask:
    return CollaborationModeMask(
        name=ModeKind.DEFAULT.display_name(),
        mode=ModeKind.DEFAULT,
        model=None,
        developer_instructions=_default_mode_instructions(),
    )


def _default_mode_instructions() -> str:
    known_mode_names = _format_mode_names((ModeKind.DEFAULT, ModeKind.PLAN))
    return _template_text("default.md").replace(KNOWN_MODE_NAMES_TEMPLATE_KEY, known_mode_names)


def _format_mode_names(modes: Sequence[ModeKind]) -> str:
    names = [mode.display_name() for mode in modes]
    if not names:
        return "none"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names)


def _bundled_model_presets() -> list[ModelPreset]:
    response = ModelsResponse.from_mapping(bundled_models_response())
    models = sorted(response.models, key=lambda info: info.priority)
    presets = [ModelPreset.from_model_info(info) for info in models]
    ModelPreset.mark_default_by_picker_visibility(presets)
    return presets


def _find_model_by_longest_prefix(model: str, candidates: Sequence[ModelInfo]) -> ModelInfo | None:
    best: ModelInfo | None = None
    for candidate in candidates:
        if not model.startswith(candidate.slug):
            continue
        if best is None or len(candidate.slug) > len(best.slug):
            best = candidate
    return best


def _find_model_by_namespaced_suffix(model: str, candidates: Sequence[ModelInfo]) -> ModelInfo | None:
    parts = model.split("/", 1)
    if len(parts) != 2:
        return None
    namespace, suffix = parts
    if "/" in suffix:
        return None
    if not namespace or not all(character.isascii() and (character.isalnum() or character in "_-") for character in namespace):
        return None
    return _find_model_by_longest_prefix(suffix, candidates)


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


def _local_personality_messages_for_slug(slug: str) -> ModelMessages | None:
    if slug not in {"gpt-5.2-codex", "exp-codex-personality"}:
        return None
    return ModelMessages(
        instructions_template=f"{DEFAULT_PERSONALITY_HEADER}\n\n{PERSONALITY_PLACEHOLDER}\n\n{_base_instructions()}",
        instructions_variables=ModelInstructionsVariables(
            personality_default="",
            personality_friendly=LOCAL_FRIENDLY_TEMPLATE,
            personality_pragmatic=LOCAL_PRAGMATIC_TEMPLATE,
        ),
    )


def _base_instructions() -> str:
    return _models_manager_root().joinpath("prompt.md").read_text(encoding="utf-8")


def _template_text(name: str) -> str:
    path = Path(__file__).resolve().parents[2] / "codex" / "codex-rs" / "collaboration-mode-templates" / "templates" / name
    return path.read_text(encoding="utf-8")


def _models_manager_root() -> Path:
    return Path(__file__).resolve().parents[2] / "codex" / "codex-rs" / "models-manager"


__all__ = [
    "builtin_collaboration_mode_presets",
    "construct_model_info_from_candidates",
    "construct_model_info_offline_for_tests",
    "get_model_offline_for_tests",
    "model_info_from_slug",
    "with_config_overrides",
]
