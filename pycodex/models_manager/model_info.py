"""Model metadata helpers ported from ``codex-models-manager::model_info``."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import Any

from pycodex.protocol import (
    ConfigShellToolType,
    ModelInfo,
    ModelInstructionsVariables,
    ModelMessages,
    ModelVisibility,
    ReasoningSummary,
    TruncationMode,
    TruncationPolicyConfig,
    WebSearchToolType,
    default_input_modalities,
)
from pycodex.utils.string import approx_bytes_for_tokens


DEFAULT_PERSONALITY_HEADER = (
    "You are Codex, a coding agent based on GPT-5. You and the user share the same "
    "workspace and collaborate to achieve the user's goals."
)
LOCAL_FRIENDLY_TEMPLATE = (
    "You optimize for team morale and being a supportive teammate as much as code quality."
)
LOCAL_PRAGMATIC_TEMPLATE = "You are a deeply pragmatic, effective software engineer."
PERSONALITY_PLACEHOLDER = "{{ personality }}"
BASE_INSTRUCTIONS = (
    Path(__file__).resolve().parents[2]
    .joinpath("codex", "codex-rs", "models-manager", "prompt.md")
    .read_text(encoding="utf-8")
)


def with_config_overrides(model: ModelInfo, config: Any) -> ModelInfo:
    """Apply Rust ``ModelsManagerConfig`` overrides to one ``ModelInfo``."""

    if getattr(config, "model_supports_reasoning_summaries", None) is True:
        model = replace(model, supports_reasoning_summaries=True)

    model_context_window = getattr(config, "model_context_window", None)
    if model_context_window is not None:
        context_window = int(model_context_window)
        if model.max_context_window is not None:
            context_window = min(context_window, model.max_context_window)
        model = replace(model, context_window=context_window)

    model_auto_compact_token_limit = getattr(config, "model_auto_compact_token_limit", None)
    if model_auto_compact_token_limit is not None:
        model = replace(model, auto_compact_token_limit_value=int(model_auto_compact_token_limit))

    tool_output_token_limit = getattr(config, "tool_output_token_limit", None)
    if tool_output_token_limit is not None:
        token_limit = int(tool_output_token_limit)
        if model.truncation_policy.mode is TruncationMode.BYTES:
            truncation_policy = TruncationPolicyConfig.bytes(approx_bytes_for_tokens(token_limit))
        else:
            truncation_policy = TruncationPolicyConfig.tokens(token_limit)
        model = replace(model, truncation_policy=truncation_policy)

    base_instructions = getattr(config, "base_instructions", None)
    if base_instructions is not None:
        model = replace(model, base_instructions=str(base_instructions), model_messages=None)
    elif not getattr(config, "personality_enabled", False):
        model = replace(model, model_messages=None)

    return model


def model_info_from_slug(slug: str) -> ModelInfo:
    """Build Rust's minimal fallback model descriptor for an unknown slug."""

    return ModelInfo(
        slug=str(slug),
        display_name=str(slug),
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
        base_instructions=BASE_INSTRUCTIONS,
        model_messages=local_personality_messages_for_slug(str(slug)),
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


def local_personality_messages_for_slug(slug: str) -> ModelMessages | None:
    if slug not in {"gpt-5.2-codex", "exp-codex-personality"}:
        return None
    return ModelMessages(
        instructions_template=f"{DEFAULT_PERSONALITY_HEADER}\n\n{PERSONALITY_PLACEHOLDER}\n\n{BASE_INSTRUCTIONS}",
        instructions_variables=ModelInstructionsVariables(
            personality_default="",
            personality_friendly=LOCAL_FRIENDLY_TEMPLATE,
            personality_pragmatic=LOCAL_PRAGMATIC_TEMPLATE,
        ),
    )


__all__ = [
    "BASE_INSTRUCTIONS",
    "DEFAULT_PERSONALITY_HEADER",
    "LOCAL_FRIENDLY_TEMPLATE",
    "LOCAL_PRAGMATIC_TEMPLATE",
    "PERSONALITY_PLACEHOLDER",
    "local_personality_messages_for_slug",
    "model_info_from_slug",
    "with_config_overrides",
]
