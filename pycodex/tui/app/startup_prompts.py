"""Startup prompt helpers for Rust ``codex-tui::app::startup_prompts``.

Upstream source: ``codex/codex-rs/tui/src/app/startup_prompts.rs``.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::startup_prompts",
    source="codex/codex-rs/tui/src/app/startup_prompts.rs",
    status="complete",
)

HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG = "hide_gpt_5_1_codex_max_migration_prompt"
HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG = "hide_gpt5_1_migration_prompt"
MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT = 4


@dataclass(eq=True)
class ModelUpgrade:
    id: str
    migration_config_key: str = ""
    model_link: Optional[str] = None
    upgrade_copy: Optional[str] = None
    migration_markdown: Optional[str] = None


@dataclass(eq=True)
class ModelAvailabilityNux:
    message: str


@dataclass(eq=True)
class ModelPreset:
    model: str
    show_in_picker: bool = True
    upgrade: Optional[ModelUpgrade] = None
    availability_nux: Optional[ModelAvailabilityNux] = None
    display_name: Optional[str] = None
    description: str = ""
    default_reasoning_effort: Any = None


@dataclass(eq=True)
class Notices:
    model_migrations: Dict[str, str] = field(default_factory=dict)
    hide_gpt_5_1_codex_max_migration_prompt: Optional[bool] = None
    hide_gpt5_1_migration_prompt: Optional[bool] = None


@dataclass(eq=True)
class ModelAvailabilityNuxConfig:
    shown_count: Dict[str, int] = field(default_factory=dict)


@dataclass(eq=True)
class ConfigOverrides:
    additional_writable_roots: List[Path] = field(default_factory=list)


@dataclass(eq=True)
class StartupTooltipOverride:
    model_slug: str
    message: str


@dataclass(eq=True)
class Config:
    model: Optional[str] = None
    model_reasoning_effort: Any = None
    notices: Notices = field(default_factory=Notices)
    model_availability_nux: ModelAvailabilityNuxConfig = field(default_factory=ModelAvailabilityNuxConfig)
    show_tooltips: bool = True


@dataclass(eq=True)
class AppExitInfo:
    exit_reason: str = "UserRequested"
    token_usage: Dict[str, Any] = field(default_factory=dict)
    thread_id: Optional[str] = None
    thread_name: Optional[str] = None
    update_action: Any = None


class ModelMigrationOutcome:
    ACCEPTED = "Accepted"
    REJECTED = "Rejected"
    EXIT = "Exit"


class EventSender:
    def __init__(self) -> None:
        self.events: List[Dict[str, Any]] = []

    def send(self, event: Dict[str, Any]) -> None:
        self.events.append(event)


def _get_attr_or_key(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _warning_event(message: str) -> Dict[str, Any]:
    return {"type": "InsertHistoryCell", "cell": {"kind": "warning", "message": message}}


def emit_skill_load_warnings(app_event_tx: EventSender, errors: Iterable[Any]) -> None:
    error_list = list(errors)
    if not error_list:
        return
    app_event_tx.send(_warning_event("Skipped loading %d skill(s) due to invalid SKILL.md files." % len(error_list)))
    for error in error_list:
        path = _get_attr_or_key(error, "path", "")
        message = _get_attr_or_key(error, "message", "")
        app_event_tx.send(_warning_event("%s: %s" % (path, message)))


def emit_project_config_warnings(app_event_tx: EventSender, config: Any) -> None:
    disabled_folders = []
    layer_stack = _get_attr_or_key(config, "config_layer_stack")
    layers = []
    if layer_stack is not None and hasattr(layer_stack, "get_layers"):
        layers = list(layer_stack.get_layers("LowestPrecedenceFirst", True))
    else:
        layers = list(_get_attr_or_key(config, "config_layers", []) or [])
    for layer in layers:
        disabled_reason = _get_attr_or_key(layer, "disabled_reason")
        if disabled_reason is None:
            continue
        name = _get_attr_or_key(layer, "name", {})
        dot_codex_folder = _get_attr_or_key(name, "dot_codex_folder")
        source_kind = _get_attr_or_key(name, "kind", "Project")
        if dot_codex_folder is None or source_kind != "Project":
            continue
        disabled_folders.append((str(dot_codex_folder), str(disabled_reason)))
    if not disabled_folders:
        return
    message = (
        "Project-local config, hooks, and exec policies are disabled in the following folders "
        "until the project is trusted, but skills still load.\n"
    )
    for index, pair in enumerate(disabled_folders, 1):
        folder, reason = pair
        message += "    %d. %s\n       %s\n" % (index, folder, reason)
    app_event_tx.send(_warning_event(message))


def emit_system_bwrap_warning(app_event_tx: EventSender, config: Any, warning_provider: Optional[Callable[[Any], Optional[str]]] = None) -> None:
    if warning_provider is None:
        warning_provider = _get_attr_or_key(config, "system_bwrap_warning")
    if warning_provider is None:
        return
    permissions = _get_attr_or_key(config, "permissions")
    profile = permissions.permission_profile() if hasattr(permissions, "permission_profile") else _get_attr_or_key(config, "permission_profile")
    message = warning_provider(profile)
    if message:
        app_event_tx.send(_warning_event(str(message)))


def should_show_model_migration_prompt(
    current_model: str,
    target_model: str,
    seen_migrations: Dict[str, str],
    available_models: List[Any],
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


def migration_prompt_hidden(config: Any, migration_config_key: str) -> bool:
    notices = _get_attr_or_key(config, "notices", Notices())
    if migration_config_key == HIDE_GPT_5_1_CODEX_MAX_MIGRATION_PROMPT_CONFIG:
        return bool(_get_attr_or_key(notices, "hide_gpt_5_1_codex_max_migration_prompt", False))
    if migration_config_key == HIDE_GPT5_1_MIGRATION_PROMPT_CONFIG:
        return bool(_get_attr_or_key(notices, "hide_gpt5_1_migration_prompt", False))
    return False


def target_preset_for_upgrade(available_models: List[Any], target_model: str) -> Optional[Any]:
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
    available_models: List[Any],
    nux_config: Any,
) -> Optional[StartupTooltipOverride]:
    shown_count = _get_attr_or_key(nux_config, "shown_count", {}) or {}
    for preset in available_models:
        nux = _get_attr_or_key(preset, "availability_nux")
        if nux is None:
            continue
        model = str(_get_attr_or_key(preset, "model"))
        if int(shown_count.get(model, 0)) < MODEL_AVAILABILITY_NUX_MAX_SHOW_COUNT:
            return StartupTooltipOverride(model_slug=model, message=str(_get_attr_or_key(nux, "message")))
    return None


def normalize_harness_overrides_for_cwd(overrides: ConfigOverrides, base_cwd: Any) -> ConfigOverrides:
    if not overrides.additional_writable_roots:
        return overrides
    base = Path(base_cwd)
    overrides.additional_writable_roots = [base / root for root in overrides.additional_writable_roots]
    return overrides


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def prepare_startup_tooltip_override(config: Config, available_models: List[Any], is_first_run: bool) -> Optional[str]:
    if is_first_run or not config.show_tooltips:
        return None
    tooltip_override = select_model_availability_nux(available_models, config.model_availability_nux)
    if tooltip_override is None:
        return None
    shown_count = config.model_availability_nux.shown_count
    next_count = int(shown_count.get(tooltip_override.model_slug, 0)) + 1
    updated_shown_count = dict(shown_count)
    updated_shown_count[tooltip_override.model_slug] = next_count
    persist = _get_attr_or_key(config, "set_model_availability_nux_count")
    if persist is not None:
        try:
            await _maybe_await(persist(updated_shown_count))
        except Exception:
            return tooltip_override.message
    config.model_availability_nux.shown_count = updated_shown_count
    return tooltip_override.message


def migration_copy_for_models(
    current_model: str,
    target_model: str,
    model_link: Optional[str],
    upgrade_copy: Optional[str],
    migration_markdown: Optional[str],
    heading_label: str,
    target_description: Optional[str],
    can_opt_out: bool,
) -> Dict[str, Any]:
    return {
        "current_model": current_model,
        "target_model": target_model,
        "model_link": model_link,
        "upgrade_copy": upgrade_copy,
        "migration_markdown": migration_markdown,
        "heading_label": heading_label,
        "target_description": target_description,
        "can_opt_out": can_opt_out,
    }


async def handle_model_migration_prompt_if_needed(
    tui: Any,
    config: Config,
    model: str,
    app_event_tx: EventSender,
    available_models: List[Any],
) -> Optional[AppExitInfo]:
    current_preset = next((preset for preset in available_models if _get_attr_or_key(preset, "model") == model), None)
    upgrade = _get_attr_or_key(current_preset, "upgrade") if current_preset is not None else None
    if upgrade is None:
        return None
    target_model = str(_get_attr_or_key(upgrade, "id"))
    migration_config_key = str(_get_attr_or_key(upgrade, "migration_config_key", ""))
    if migration_prompt_hidden(config, migration_config_key):
        return None
    if not should_show_model_migration_prompt(model, target_model, config.notices.model_migrations, available_models):
        return None
    target_preset = target_preset_for_upgrade(available_models, target_model)
    if target_preset is None:
        return None
    target_display_name = _get_attr_or_key(target_preset, "display_name") or target_model
    heading_label = target_model if target_display_name == model else target_display_name
    description = str(_get_attr_or_key(target_preset, "description", ""))
    target_description = description if description else None
    prompt_copy = migration_copy_for_models(
        model,
        target_model,
        _get_attr_or_key(upgrade, "model_link"),
        _get_attr_or_key(upgrade, "upgrade_copy"),
        _get_attr_or_key(upgrade, "migration_markdown"),
        str(heading_label),
        target_description,
        current_preset is not None,
    )
    runner = _get_attr_or_key(tui, "run_model_migration_prompt")
    if runner is None and callable(tui):
        runner = tui
    if runner is None:
        raise RuntimeError("model migration prompt runner is required")
    outcome = await _maybe_await(runner(prompt_copy))
    if outcome == ModelMigrationOutcome.ACCEPTED or outcome == "accepted":
        apply_accepted_model_migration(config, app_event_tx, model, target_model, _get_attr_or_key(target_preset, "default_reasoning_effort"))
    elif outcome == ModelMigrationOutcome.REJECTED or outcome == "rejected":
        app_event_tx.send({"type": "PersistModelMigrationPromptAcknowledged", "from_model": model, "to_model": target_model})
    elif outcome == ModelMigrationOutcome.EXIT or outcome == "exit":
        return AppExitInfo()
    return None


__all__ = [name for name in globals() if not name.startswith("_")]
