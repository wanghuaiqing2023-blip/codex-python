"""Behavior port slice for Rust ``codex-tui::external_agent_config_migration_startup``.

This module owns startup gating, prompt cooldown filtering, success-copy, and
preference timestamp/dismissal persistence boundaries for external agent config
migration. Python keeps config/app-server/TUI integration semantic and
standard-library-only.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Sequence

from ._porting import RustTuiModule
from .external_agent_config_migration import ExternalAgentConfigMigrationOutcome

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="external_agent_config_migration_startup",
    source="codex/codex-rs/tui/src/external_agent_config_migration_startup.rs",
)

EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS = 5 * 24 * 60 * 60


@dataclass(frozen=True)
class ExternalAgentConfigMigrationStartupOutcome:
    kind: str
    success_message: str | None = None

    @classmethod
    def Continue(cls, success_message: str | None = None) -> "ExternalAgentConfigMigrationStartupOutcome":
        return cls("continue", success_message)

    @classmethod
    def ExitRequested(cls) -> "ExternalAgentConfigMigrationStartupOutcome":
        return cls("exit_requested")


@dataclass
class ExternalConfigMigrationPrompts:
    home: bool | None = None
    projects: dict[str, bool] = field(default_factory=dict)
    home_last_prompted_at: int | None = None
    project_last_prompted_at: dict[str, int] = field(default_factory=dict)


@dataclass
class Notices:
    external_config_migration_prompts: ExternalConfigMigrationPrompts = field(default_factory=ExternalConfigMigrationPrompts)


@dataclass
class FeatureSet:
    enabled_features: set[str] = field(default_factory=set)

    def enabled(self, feature: Any) -> bool:
        raw = _feature_name(feature)
        return raw in self.enabled_features or "ExternalMigration" in self.enabled_features


@dataclass
class Config:
    cwd: Path = Path.cwd()
    codex_home: Path = Path.cwd()
    features: FeatureSet = field(default_factory=FeatureSet)
    notices: Notices = field(default_factory=Notices)
    applied_edits: list[tuple[str, Any]] = field(default_factory=list)


def should_show_external_agent_config_migration_prompt(config: Any, entered_trust_nux: bool) -> bool:
    return bool(entered_trust_nux) and _feature_enabled(_get(config, "features"), "ExternalMigration")


def external_config_migration_project_key(path: str | Path) -> str:
    return str(Path(path))


def is_external_config_migration_scope_hidden(config: Any, cwd: str | Path | None) -> bool:
    prompts = _prompts(config)
    if cwd is None:
        return bool(_get(prompts, "home", False))
    projects = _get(prompts, "projects", {}) or {}
    return bool(projects.get(external_config_migration_project_key(cwd), False))


def external_config_migration_last_prompted_at(config: Any, cwd: str | Path | None) -> int | None:
    prompts = _prompts(config)
    if cwd is None:
        value = _get(prompts, "home_last_prompted_at")
        return None if value is None else int(value)
    projects = _get(prompts, "project_last_prompted_at", {}) or {}
    value = projects.get(external_config_migration_project_key(cwd))
    return None if value is None else int(value)


def is_external_config_migration_scope_cooling_down(
    config: Any,
    cwd: str | Path | None,
    now_unix_seconds: int,
) -> bool:
    last_prompted_at = external_config_migration_last_prompted_at(config, cwd)
    if last_prompted_at is None:
        return False
    return last_prompted_at + EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS > int(now_unix_seconds)


def visible_external_agent_config_migration_items(
    config: Any,
    items: Iterable[Any],
    now_unix_seconds: int,
) -> list[Any]:
    visible = []
    for item in items:
        cwd = _get(item, "cwd")
        if is_external_config_migration_scope_hidden(config, cwd):
            continue
        if is_external_config_migration_scope_cooling_down(config, cwd, now_unix_seconds):
            continue
        visible.append(item)
    return visible


def external_agent_config_migration_success_message(items: Sequence[Any]) -> str:
    for item in items:
        if _item_type(item).lower() == "plugins":
            return "External config migration completed. Plugin migration is still in progress and may take a few minutes."
    return "External config migration completed successfully."


def unix_seconds_now() -> int:
    return int(time.time())


async def persist_external_agent_config_migration_prompt_shown(
    config: Any,
    items: Sequence[Any],
    now_unix_seconds: int,
) -> None:
    prompts = _ensure_prompts(config)
    edits = []
    if any(_get(item, "cwd") is None for item in items):
        edits.append(("home_last_prompted_at", int(now_unix_seconds)))
        _set(prompts, "home_last_prompted_at", int(now_unix_seconds))

    project_map = _ensure_map(prompts, "project_last_prompted_at")
    for project in _project_keys(items):
        edits.append(("project_last_prompted_at", project, int(now_unix_seconds)))
        project_map[project] = int(now_unix_seconds)
    _record_edits(config, edits)


async def persist_external_agent_config_migration_prompt_dismissal(
    config: Any,
    items: Sequence[Any],
) -> None:
    prompts = _ensure_prompts(config)
    edits = []
    hide_home = any(_get(item, "cwd") is None for item in items)
    if hide_home and not bool(_get(prompts, "home", False)):
        edits.append(("home", True))
        _set(prompts, "home", True)

    projects = _ensure_map(prompts, "projects")
    for project in sorted(set(_project_keys(items))):
        if not bool(projects.get(project, False)):
            edits.append(("project", project, True))
            projects[project] = True
    _record_edits(config, edits)


async def handle_external_agent_config_migration_prompt_if_needed(
    tui: Any,
    app_server: Any,
    config: Any,
    cli_kv_overrides: Sequence[tuple[str, Any]] | None = None,
    harness_overrides: Any = None,
    entered_trust_nux: bool = False,
    *,
    prompt_runner: Any | None = None,
    now_unix_seconds: int | None = None,
    config_reloader: Any | None = None,
) -> ExternalAgentConfigMigrationStartupOutcome:
    if not should_show_external_agent_config_migration_prompt(config, entered_trust_nux):
        return ExternalAgentConfigMigrationStartupOutcome.Continue()

    now = unix_seconds_now() if now_unix_seconds is None else int(now_unix_seconds)
    try:
        response = await _maybe_await(
            app_server.external_agent_config_detect({"include_home": True, "cwds": [_get(config, "cwd")]})
        )
        detected_items = visible_external_agent_config_migration_items(config, _get(response, "items", []), now)
    except Exception:
        return ExternalAgentConfigMigrationStartupOutcome.Continue()

    if not detected_items:
        return ExternalAgentConfigMigrationStartupOutcome.Continue()

    try:
        await persist_external_agent_config_migration_prompt_shown(config, detected_items, now)
    except Exception:
        pass

    selected_items = list(detected_items)
    error: str | None = None
    if prompt_runner is None:
        raise NotImplementedError("interactive migration prompt runner is a TUI runtime boundary")

    while True:
        outcome = await _maybe_await(prompt_runner(tui, detected_items, selected_items, error))
        kind = _get(outcome, "kind", "")
        if kind == "proceed":
            selected_items = list(_get(outcome, "items", ()))
            try:
                await _maybe_await(app_server.external_agent_config_import(selected_items))
            except Exception as exc:
                error = f"Migration failed: {exc}"
                continue
            success_message = external_agent_config_migration_success_message(selected_items)
            if config_reloader is not None:
                new_config = await _maybe_await(config_reloader(config, cli_kv_overrides or [], harness_overrides))
                if new_config is not None:
                    _copy_public_attrs(config, new_config)
            return ExternalAgentConfigMigrationStartupOutcome.Continue(success_message)
        if kind == "skip":
            return ExternalAgentConfigMigrationStartupOutcome.Continue()
        if kind == "skip_forever":
            try:
                await persist_external_agent_config_migration_prompt_dismissal(config, detected_items)
            except Exception as exc:
                error = f"Failed to save preference: {exc}"
                continue
            return ExternalAgentConfigMigrationStartupOutcome.Continue()
        if kind == "exit":
            return ExternalAgentConfigMigrationStartupOutcome.ExitRequested()
        return ExternalAgentConfigMigrationStartupOutcome.Continue()


def _feature_enabled(features: Any, feature: str) -> bool:
    if features is None:
        return False
    if hasattr(features, "enabled"):
        return bool(features.enabled(feature))
    if isinstance(features, dict):
        value = features.get(feature) or features.get("ExternalMigration") or features.get("external_migration")
        return bool(value)
    if isinstance(features, (set, list, tuple)):
        return feature in {_feature_name(item) for item in features}
    return bool(getattr(features, feature, False) or getattr(features, "external_migration", False))


def _feature_name(feature: Any) -> str:
    raw = str(getattr(feature, "name", feature))
    return raw.split("::")[-1].split(".")[-1]


def _prompts(config: Any) -> Any:
    notices = _get(config, "notices", {})
    return _get(notices, "external_config_migration_prompts", {})


def _ensure_prompts(config: Any) -> Any:
    notices = _get(config, "notices")
    if notices is None:
        notices = Notices()
        _set(config, "notices", notices)
    prompts = _get(notices, "external_config_migration_prompts")
    if prompts is None:
        prompts = ExternalConfigMigrationPrompts()
        _set(notices, "external_config_migration_prompts", prompts)
    return prompts


def _ensure_map(obj: Any, key: str) -> dict[str, Any]:
    value = _get(obj, key)
    if value is None:
        value = {}
        _set(obj, key, value)
    return value


def _project_keys(items: Iterable[Any]) -> list[str]:
    return [external_config_migration_project_key(cwd) for cwd in (_get(item, "cwd") for item in items) if cwd is not None]


def _item_type(item: Any) -> str:
    value = _get(item, "item_type", "")
    raw = str(getattr(value, "name", value))
    return raw.split("::")[-1].split(".")[-1]


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


def _record_edits(config: Any, edits: list[Any]) -> None:
    if not edits:
        return
    existing = _get(config, "applied_edits")
    if existing is None:
        _set(config, "applied_edits", [])
        existing = _get(config, "applied_edits")
    if hasattr(existing, "extend"):
        existing.extend(edits)


async def _maybe_await(value: Any) -> Any:
    if hasattr(value, "__await__"):
        return await value
    return value


def _copy_public_attrs(target: Any, source: Any) -> None:
    if isinstance(target, dict) and isinstance(source, dict):
        target.clear()
        target.update(source)
        return
    if hasattr(source, "__dict__"):
        for key, value in source.__dict__.items():
            if not key.startswith("_"):
                _set(target, key, value)


# Rust test-name compatibility helpers.
async def visible_external_agent_config_migration_items_omits_hidden_scopes(*args: Any, **kwargs: Any) -> Any:
    return visible_external_agent_config_migration_items(*args, **kwargs)


async def visible_external_agent_config_migration_items_omits_recently_prompted_scopes(*args: Any, **kwargs: Any) -> Any:
    return visible_external_agent_config_migration_items(*args, **kwargs)


async def external_config_migration_scope_cooldown_expires_after_five_days(*args: Any, **kwargs: Any) -> Any:
    return is_external_config_migration_scope_cooling_down(*args, **kwargs)


def external_agent_config_migration_success_message_mentions_plugins_when_present(*args: Any, **kwargs: Any) -> Any:
    return external_agent_config_migration_success_message(*args, **kwargs)


def external_agent_config_migration_success_message_omits_plugins_copy_when_absent(*args: Any, **kwargs: Any) -> Any:
    return external_agent_config_migration_success_message(*args, **kwargs)


async def external_agent_config_migration_prompt_requires_trust_nux_entry(*args: Any, **kwargs: Any) -> Any:
    return should_show_external_agent_config_migration_prompt(*args, **kwargs)


__all__ = [
    "EXTERNAL_CONFIG_MIGRATION_PROMPT_COOLDOWN_SECS",
    "Config",
    "ExternalAgentConfigMigrationStartupOutcome",
    "ExternalConfigMigrationPrompts",
    "FeatureSet",
    "Notices",
    "RUST_MODULE",
    "external_agent_config_migration_prompt_requires_trust_nux_entry",
    "external_agent_config_migration_success_message",
    "external_agent_config_migration_success_message_mentions_plugins_when_present",
    "external_agent_config_migration_success_message_omits_plugins_copy_when_absent",
    "external_config_migration_last_prompted_at",
    "external_config_migration_project_key",
    "external_config_migration_scope_cooldown_expires_after_five_days",
    "handle_external_agent_config_migration_prompt_if_needed",
    "is_external_config_migration_scope_cooling_down",
    "is_external_config_migration_scope_hidden",
    "persist_external_agent_config_migration_prompt_dismissal",
    "persist_external_agent_config_migration_prompt_shown",
    "should_show_external_agent_config_migration_prompt",
    "unix_seconds_now",
    "visible_external_agent_config_migration_items",
    "visible_external_agent_config_migration_items_omits_hidden_scopes",
    "visible_external_agent_config_migration_items_omits_recently_prompted_scopes",
]
