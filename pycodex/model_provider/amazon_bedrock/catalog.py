"""Port of Rust ``codex-model-provider::amazon_bedrock::catalog``.

Rust source:
- ``codex/codex-rs/model-provider/src/amazon_bedrock/catalog.rs``
"""

from __future__ import annotations

from pycodex.models_manager.model_info import BASE_INSTRUCTIONS
from pycodex.model_provider_info import AMAZON_BEDROCK_GPT_5_4_MODEL_ID
from pycodex.protocol.config_types import ReasoningEffort, ReasoningSummary, ServiceTier, Verbosity
from pycodex.protocol.openai_models import (
    ApplyPatchToolType,
    ConfigShellToolType,
    InputModality,
    ModelInfo,
    ModelServiceTier,
    ModelsResponse,
    ModelVisibility,
    ReasoningEffortPreset,
    SPEED_TIER_FAST,
    TruncationPolicyConfig,
    WebSearchToolType,
)


GPT_OSS_CONTEXT_WINDOW = 128_000
GPT_5_4_CONTEXT_WINDOW = 272_000
GPT_5_4_MAX_CONTEXT_WINDOW = 1_000_000


def static_model_catalog() -> ModelsResponse:
    return ModelsResponse(
        models=(
            gpt_5_4_cmb_bedrock_model(0),
            bedrock_oss_model("openai.gpt-oss-120b", "GPT OSS 120B on Bedrock", 1),
            bedrock_oss_model("openai.gpt-oss-20b", "GPT OSS 20B on Bedrock", 2),
        )
    )


def gpt_5_4_cmb_bedrock_model(priority: int) -> ModelInfo:
    return ModelInfo(
        slug=AMAZON_BEDROCK_GPT_5_4_MODEL_ID,
        display_name="gpt-5.4",
        description="Strong model for everyday coding.",
        default_reasoning_level=ReasoningEffort.MEDIUM,
        supported_reasoning_levels=tuple(gpt_5_4_cmb_reasoning_levels()),
        shell_type=ConfigShellToolType.SHELL_COMMAND,
        visibility=ModelVisibility.LIST,
        supported_in_api=True,
        priority=priority,
        additional_speed_tiers=(),
        service_tiers=(
            ModelServiceTier(
                id=ServiceTier.FAST.request_value(),
                name=SPEED_TIER_FAST,
                description="Fastest inference with increased plan usage",
            ),
        ),
        default_service_tier=None,
        availability_nux=None,
        upgrade=None,
        base_instructions=BASE_INSTRUCTIONS,
        model_messages=None,
        supports_reasoning_summaries=True,
        default_reasoning_summary=ReasoningSummary.NONE,
        support_verbosity=True,
        default_verbosity=Verbosity.MEDIUM,
        apply_patch_tool_type=ApplyPatchToolType.FREEFORM,
        web_search_tool_type=WebSearchToolType.TEXT_AND_IMAGE,
        truncation_policy=TruncationPolicyConfig.tokens(10_000),
        supports_parallel_tool_calls=True,
        supports_image_detail_original=True,
        context_window=GPT_5_4_CONTEXT_WINDOW,
        max_context_window=GPT_5_4_MAX_CONTEXT_WINDOW,
        auto_compact_token_limit_value=None,
        effective_context_window_percent=95,
        experimental_supported_tools=(),
        input_modalities=(InputModality.TEXT, InputModality.IMAGE),
        used_fallback_model_metadata=False,
        supports_search_tool=True,
    )


def bedrock_oss_model(slug: str, display_name: str, priority: int) -> ModelInfo:
    return ModelInfo(
        slug=slug,
        display_name=display_name,
        description=display_name,
        default_reasoning_level=ReasoningEffort.MEDIUM,
        supported_reasoning_levels=(
            reasoning_effort_preset(ReasoningEffort.LOW),
            reasoning_effort_preset(ReasoningEffort.MEDIUM),
            reasoning_effort_preset(ReasoningEffort.HIGH),
        ),
        shell_type=ConfigShellToolType.SHELL_COMMAND,
        visibility=ModelVisibility.LIST,
        supported_in_api=True,
        priority=priority,
        additional_speed_tiers=(),
        service_tiers=(),
        default_service_tier=None,
        availability_nux=None,
        upgrade=None,
        base_instructions=BASE_INSTRUCTIONS,
        model_messages=None,
        supports_reasoning_summaries=True,
        default_reasoning_summary=ReasoningSummary.NONE,
        support_verbosity=False,
        default_verbosity=None,
        apply_patch_tool_type=None,
        web_search_tool_type=WebSearchToolType.TEXT,
        truncation_policy=TruncationPolicyConfig.tokens(10_000),
        supports_parallel_tool_calls=True,
        supports_image_detail_original=False,
        context_window=GPT_OSS_CONTEXT_WINDOW,
        max_context_window=GPT_OSS_CONTEXT_WINDOW,
        auto_compact_token_limit_value=None,
        effective_context_window_percent=95,
        experimental_supported_tools=(),
        input_modalities=(InputModality.TEXT,),
        used_fallback_model_metadata=False,
        supports_search_tool=False,
    )


def gpt_5_4_cmb_reasoning_levels() -> list[ReasoningEffortPreset]:
    return [
        reasoning_effort_preset(ReasoningEffort.MINIMAL),
        reasoning_effort_preset(ReasoningEffort.LOW),
        reasoning_effort_preset(ReasoningEffort.MEDIUM),
        reasoning_effort_preset(ReasoningEffort.HIGH),
    ]


def reasoning_effort_preset(effort: ReasoningEffort) -> ReasoningEffortPreset:
    descriptions = {
        ReasoningEffort.NONE: "No reasoning",
        ReasoningEffort.MINIMAL: "Minimal reasoning",
        ReasoningEffort.LOW: "Fast responses with lighter reasoning",
        ReasoningEffort.MEDIUM: "Balances speed and reasoning depth for everyday tasks",
        ReasoningEffort.HIGH: "Greater reasoning depth for complex problems",
        ReasoningEffort.XHIGH: "Extra high reasoning depth for complex problems",
    }
    return ReasoningEffortPreset(effort=effort, description=descriptions[effort])


__all__ = [
    "BASE_INSTRUCTIONS",
    "GPT_5_4_CONTEXT_WINDOW",
    "GPT_5_4_MAX_CONTEXT_WINDOW",
    "GPT_OSS_CONTEXT_WINDOW",
    "bedrock_oss_model",
    "gpt_5_4_cmb_bedrock_model",
    "gpt_5_4_cmb_reasoning_levels",
    "reasoning_effort_preset",
    "static_model_catalog",
]
