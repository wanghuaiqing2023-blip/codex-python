"""Model list helpers for ``codex-app-server/src/models.rs``."""

from __future__ import annotations

from collections.abc import Iterable
from inspect import isawaitable
from typing import Any

from pycodex.app_server_protocol.model import (
    Model,
    ModelAvailabilityNux,
    ModelServiceTier,
    ModelUpgradeInfo,
    ReasoningEffortOption,
)
from pycodex.protocol.openai_models import (
    ModelPreset,
    ReasoningEffortPreset,
)

JsonValue = Any
REFRESH_STRATEGY_ONLINE_IF_UNCACHED = "OnlineIfUncached"


async def supported_models(thread_manager: Any, include_hidden: bool) -> list[Model]:
    """Mirror Rust's async list/filter/map shape for app-server models."""

    raw_models = thread_manager.list_models(REFRESH_STRATEGY_ONLINE_IF_UNCACHED)
    if isawaitable(raw_models):
        raw_models = await raw_models
    return supported_models_from_presets(raw_models, include_hidden=include_hidden)


def supported_models_from_presets(
    presets: Iterable[ModelPreset],
    *,
    include_hidden: bool,
) -> list[Model]:
    return [
        model_from_preset(preset)
        for preset in presets
        if include_hidden or preset.show_in_picker
    ]


def model_from_preset(preset: ModelPreset) -> Model:
    upgrade = preset.upgrade
    return Model(
        id=str(preset.id),
        model=str(preset.model),
        upgrade=None if upgrade is None else upgrade.id,
        upgrade_info=None
        if upgrade is None
        else ModelUpgradeInfo(
            model=upgrade.id,
            upgrade_copy=upgrade.upgrade_copy,
            model_link=upgrade.model_link,
            migration_markdown=upgrade.migration_markdown,
        ),
        availability_nux=None
        if preset.availability_nux is None
        else ModelAvailabilityNux(message=preset.availability_nux.message),
        display_name=str(preset.display_name),
        description=str(preset.description),
        hidden=not preset.show_in_picker,
        supported_reasoning_efforts=reasoning_efforts_from_preset(preset.supported_reasoning_efforts),
        default_reasoning_effort=preset.default_reasoning_effort,
        input_modalities=preset.input_modalities,
        supports_personality=preset.supports_personality,
        additional_speed_tiers=preset.additional_speed_tiers,
        service_tiers=tuple(
            ModelServiceTier(
                id=service_tier.id,
                name=service_tier.name,
                description=service_tier.description,
            )
            for service_tier in preset.service_tiers
        ),
        default_service_tier=preset.default_service_tier,
        is_default=preset.is_default,
    )


def reasoning_efforts_from_preset(
    efforts: Iterable[ReasoningEffortPreset],
) -> tuple[ReasoningEffortOption, ...]:
    return tuple(
        ReasoningEffortOption(
            reasoning_effort=preset.effort,
            description=str(preset.description),
        )
        for preset in efforts
    )


__all__ = [
    "REFRESH_STRATEGY_ONLINE_IF_UNCACHED",
    "model_from_preset",
    "reasoning_efforts_from_preset",
    "supported_models",
    "supported_models_from_presets",
]
