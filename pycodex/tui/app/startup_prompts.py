"""Startup prompt helpers for Rust ``codex-tui::app::startup_prompts``.

Upstream source: ``codex/codex-rs/tui/src/app/startup_prompts.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::startup_prompts",
    source="codex/codex-rs/tui/src/app/startup_prompts.rs",
)

HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG = "hide_gpt_5_1_codex_max_migration_prompt"
HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG = "hide_gpt5_1_migration_prompt"
MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT = 4


@dataclass(eq=True)
class ModelUpgrade:
    id: str


@dataclass(eq=True)
class ModelAvailabilityNux:
    message: str


@dataclass(eq=True)
class ModelPreset:
    model: str
    show_in_picker: bool = True
    upgrade: ModelUpgrade | None = None
    availability_nux: ModelAvailabilityNux | None = None
    display_name: str | None = None
    description: str = ""
    default_reasoning_effort: Any | None = None


@dataclass(eq=True)
class Notices:
    model_migrations: dict[str, str] = field(default_factory=dict)
    hide_gpt_5_1_codex_max_migration_prompt: bool | None = None
    hide_gpt5_1_migration_prompt: bool | None = None


@dataclass(eq=True)
class ModelAvailabilityNuxConfig:
    shown_count: dict[str, int] = field(default_factory=dict)


@dataclass(eq=True)
class ConfigOverrides:
    additional_writable_roots: list[Path] = field(default_factory=list)


@dataclass(eq=True)
class StartupTooltipOverride:
    model_slug: str
    message: str


@dataclass(eq=True)
class Config:
    model: str | None = None
    model_reasoning_effort: Any | None = None
    notices: Notices = field(default_factory=Notices)
    model_availability_nux: ModelAvailabilityNuxConfig = field(default_factory=ModelAvailabilityNuxConfig)
    show_tooltips: bool = True


class EventSender:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def send(self, event: dict[str, Any]) -> None:
        self.events.append(event)


def _get_attr_or_key(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def should_show_model_migration_prompt(
    current_model: str,
    target_model: str,
    seen_migrations: dict[str, str],
    available_models: list[ModelPreset] | list[Any],
) -> bool:
    if target_model == current_model:
        return False
    if seen_migrations.get(current_model) == target_model:
        return False
    if not any(_get_attr_or_key(preset, "model") == target_model and bool(_get_attr_or_key(preset, "show_in_picker")) for preset in available_models):
        return False
    if any(_get_attr_or_key(preset, "model") == current_model and _get_attr_or_key(preset, "upgrade") is not None for preset in available_models):
        return True
    return any(_get_attr_or_key(_get_attr_or_key(preset, "upgrade"), "id") == target_model for preset in available_models)


def migration_prompt_hidden(config: Config | Any, migration_config_key: str) -> bool:
    notices = _get_attr_or_key(config, "notices", Notices())
    if migration_config_key == HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG:
        return bool(_get_attr_or_key(notices, "hide_gpt_5_1_codex_max_migration_prompt", False))
    if migration_config_key == HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG:
        return bool(_get_attr_or_key(notices, "hide_gpt5_1_migration_prompt", False))
    return False


def target_preset_for_upgrade(available_models: list[Any], target_model: str) -> Any | None:
    for preset in available_models:
        if _get_attr_or_key(preset, "model") == target_model and bool(_get_attr_or_key(preset, "show_in_picker")):
            return preset
    return None


def apply_accepted_model_migration(
    config: Config,
    app_event_tx: EventSender,
    from_model: str,
    target_model: str,
    target_default_effort: Any,
) -> None:
    app_event_tx.send({"type": "PersistModelMigrationPromptAcknowledged", "from_model": from_model, "to_model": target_model})
    config.model = target_model
    config.model_reasoning_effort = target_default_effort
    app_event_tx.send({"type": "UpdateModel", "model": target_model})
    app_event_tx.send({"type": "UpdateReasoningEffort", "effort": target_default_effort})
    app_event_tx.send({"type": "PersistModelSelection", "model": target_model, "effort": target_default_effort})


def select_model_availability_nux(
    available_models: list[Any],
    nux_config: ModelAvailabilityNuxConfig | Any,
) -> StartupTooltipOverride | None:
    shown_count = _get_attr_or_key(nux_config, "shown_count", {}) or {}
    for preset in available_models:
        nux = _get_attr_or_key(preset, "availability_nux")
        if nux is None:
            continue
        model = str(_get_attr_or_key(preset, "model"))
        if int(shown_count.get(model, 0)) < MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT:
            return StartupTooltipOverride(model_slug=model, message=str(_get_attr_or_key(nux, "message")))
    return None


def normalize_harness_overrides_for_cwd(overrides: ConfigOverrides, base_cwd: str | Path) -> ConfigOverrides:
    if not overrides.additional_writable_roots:
        return overrides
    base = Path(base_cwd)
    overrides.additional_writable_roots = [base / root for root in overrides.additional_writable_roots]
    return overrides


async def prepare_startup_tooltip_override(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::startup_prompts.prepare_startup_tooltip_override config persistence is not ported")


async def handle_model_migration_prompt_if_needed(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::startup_prompts.handle_model_migration_prompt_if_needed TUI prompt flow is not ported")


__all__ = [
    "Config",
    "ConfigOverrides",
    "EventSender",
    "HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG",
    "HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG",
    "MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT",
    "ModelAvailabilityNux",
    "ModelAvailabilityNuxConfig",
    "ModelPreset",
    "ModelUpgrade",
    "Notices",
    "RUST_MODULE",
    "StartupTooltipOverride",
    "apply_accepted_model_migration",
    "handle_model_migration_prompt_if_needed",
    "migration_prompt_hidden",
    "normalize_harness_overrides_for_cwd",
    "prepare_startup_tooltip_override",
    "select_model_availability_nux",
    "should_show_model_migration_prompt",
    "target_preset_for_upgrade",
]
