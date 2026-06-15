"""Semantic helpers for Rust ``codex-tui::app::config_persistence``.

Upstream source: ``codex/codex-rs/tui/src/app/config_persistence.rs``.

Rust owns app-level config rebuild, config write, and ChatWidget sync glue here.
Python represents those runtime paths as deterministic persistence plans while
porting the module-local extraction helpers directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::config_persistence",
    source="codex/codex-rs/tui/src/app/config_persistence.rs",
    status="complete",
)

DEFAULT_OVERRIDDEN_WRITE_MESSAGE = "the effective config is overridden by a higher-priority layer"


@dataclass(frozen=True)
class OverriddenMetadata:
    message: str


@dataclass(frozen=True)
class ConfigWriteResponse:
    overridden_metadata: Optional[Any] = None


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    default_enabled: bool = False


@dataclass(frozen=True)
class EffectiveConfigBody:
    additional: Dict[str, Any] = field(default_factory=dict)
    approvals_reviewer: Optional[Any] = None
    approval_policy: Optional[Any] = None
    sandbox_mode: Optional[Any] = None


@dataclass(frozen=True)
class ConfigReadResponse:
    config: Any


@dataclass(frozen=True)
class MemoriesToml:
    use_memories: Optional[bool] = None
    generate_memories: Optional[bool] = None


@dataclass(frozen=True)
class ConfigPersistencePlan:
    action: str
    updates: Tuple[Tuple[str, Any], ...] = ()
    message: Optional[str] = None
    error: Optional[str] = None
    use_current_config: bool = False
    refresh_from_disk: bool = False


def _get_attr_or_key(value: Any, key: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _effective_config_body(effective_config: Any) -> Any:
    return _get_attr_or_key(effective_config, "config", effective_config)


def overridden_write_message(write_response: Any) -> str:
    metadata = _get_attr_or_key(write_response, "overridden_metadata")
    if metadata is None:
        return DEFAULT_OVERRIDDEN_WRITE_MESSAGE
    message = _get_attr_or_key(metadata, "message")
    return str(message) if message is not None else DEFAULT_OVERRIDDEN_WRITE_MESSAGE


def features_toml_from_json(value: Any) -> Optional[Dict[str, bool]]:
    if value is None or not isinstance(value, dict):
        return None
    entries = {}
    for key, enabled in value.items():
        if isinstance(enabled, bool):
            entries[str(key)] = enabled
    return entries


def feature_enabled_from_effective_config(effective_config: Any, feature: Any) -> bool:
    config = _effective_config_body(effective_config)
    additional = _get_attr_or_key(config, "additional", {}) or {}
    root_features = additional.get("features") if isinstance(additional, dict) else None
    features = features_toml_from_json(root_features)
    key_value = feature.key() if callable(getattr(feature, "key", None)) else _get_attr_or_key(feature, "key", str(feature))
    key = str(key_value)
    if features is not None and key in features:
        return features[key]
    default = feature.default_enabled() if callable(getattr(feature, "default_enabled", None)) else _get_attr_or_key(feature, "default_enabled", False)
    return bool(default)


def approvals_reviewer_from_effective_config(effective_config: Any) -> Optional[Any]:
    config = _effective_config_body(effective_config)
    reviewer = _get_attr_or_key(config, "approvals_reviewer")
    if callable(getattr(reviewer, "to_core", None)):
        return reviewer.to_core()
    return reviewer


def approval_policy_from_effective_config(effective_config: Any) -> Optional[Any]:
    return _get_attr_or_key(_effective_config_body(effective_config), "approval_policy")


def sandbox_mode_from_effective_config(effective_config: Any) -> Optional[Any]:
    return _get_attr_or_key(_effective_config_body(effective_config), "sandbox_mode")


def memories_from_effective_config(effective_config: Any) -> Optional[MemoriesToml]:
    config = _effective_config_body(effective_config)
    additional = _get_attr_or_key(config, "additional", {}) or {}
    raw = additional.get("memories") if isinstance(additional, dict) else None
    if raw is None:
        return None
    if isinstance(raw, MemoriesToml):
        return raw
    if not isinstance(raw, dict):
        return None
    return MemoriesToml(use_memories=raw.get("use_memories"), generate_memories=raw.get("generate_memories"))


def windows_toml_from_json(value: Any) -> Optional[Dict[str, Any]]:
    return value if isinstance(value, dict) else None


def windows_sandbox_mode_from_effective_config(effective_config: Any) -> Optional[Any]:
    config = _effective_config_body(effective_config)
    additional = _get_attr_or_key(config, "additional", {}) or {}
    root_windows = additional.get("windows") if isinstance(additional, dict) else None
    windows = windows_toml_from_json(root_windows)
    return None if windows is None else windows.get("sandbox")


def update_reasoning_effort_updates_collaboration_mode(reasoning_effort: Any) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="update_reasoning_effort",
        updates=(("chat_widget.reasoning_effort", reasoning_effort), ("config.model_reasoning_effort", reasoning_effort)),
    )


def refresh_in_memory_config_from_disk_loads_latest_apps_state(app_id: str, enabled: bool) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk",
        updates=(("effective_config.apps.%s.enabled" % app_id, enabled), ("chat_widget.plugin_mentions_config", "sync")),
        refresh_from_disk=True,
    )


def refresh_in_memory_config_from_disk_best_effort_keeps_current_config_on_error(action: str, error: Any = None) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk_best_effort",
        message="failed to refresh config before thread transition; continuing with current in-memory config",
        error=None if error is None else str(error),
        use_current_config=True,
        refresh_from_disk=True,
    )


def refresh_in_memory_config_from_disk_uses_active_chat_widget_cwd(cwd: Any) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk",
        updates=(("config.cwd", str(cwd)),),
        refresh_from_disk=True,
    )


def refresh_in_memory_config_from_disk_updates_resize_reflow_config(max_rows: Any) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="refresh_in_memory_config_from_disk",
        updates=(("config.terminal_resize_reflow.max_rows", max_rows),),
        refresh_from_disk=True,
    )


def overridden_disabled_guardian_does_not_apply_auto_review_companions() -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="sync_feature_state_from_effective_config",
        updates=(
            ("features.guardian_approval", False),
            ("approvals_reviewer", "user"),
            ("approval_policy", "preserve_current"),
        ),
    )


def rebuild_config_for_resume_or_fallback_uses_current_config_on_same_cwd_error(current_cwd: Any) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="rebuild_config_for_resume_or_fallback",
        updates=(("cwd", str(current_cwd)),),
        use_current_config=True,
    )


def rebuild_config_for_resume_or_fallback_errors_when_cwd_changes(current_cwd: Any, resume_cwd: Any) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="rebuild_config_for_resume_or_fallback",
        updates=(("current_cwd", str(current_cwd)), ("resume_cwd", str(resume_cwd))),
        error="Failed to rebuild config for cwd %s" % resume_cwd,
        use_current_config=False,
    )


def sync_tui_theme_selection_updates_chat_widget_config_copy(theme: str) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="sync_tui_theme_selection",
        updates=(("config.tui_theme", theme), ("chat_widget.config.tui_theme", theme)),
    )


def sync_tui_pet_selection_updates_chat_widget_config_copy(pet: str) -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="sync_tui_pet_selection",
        updates=(("config.tui_pet", pet), ("chat_widget.config.tui_pet", pet)),
    )


def sync_tui_pet_disabled_updates_chat_widget_config_copy(disabled_pet_id: str = "disabled") -> ConfigPersistencePlan:
    return ConfigPersistencePlan(
        action="sync_tui_pet_disabled",
        updates=(("config.tui_pet", disabled_pet_id), ("chat_widget.config.tui_pet", disabled_pet_id)),
    )


__all__ = [
    "ConfigPersistencePlan",
    "ConfigReadResponse",
    "ConfigWriteResponse",
    "DEFAULT_OVERRIDDEN_WRITE_MESSAGE",
    "EffectiveConfigBody",
    "FeatureSpec",
    "MemoriesToml",
    "OverriddenMetadata",
    "RUST_MODULE",
    "approval_policy_from_effective_config",
    "approvals_reviewer_from_effective_config",
    "feature_enabled_from_effective_config",
    "features_toml_from_json",
    "memories_from_effective_config",
    "overridden_disabled_guardian_does_not_apply_auto_review_companions",
    "overridden_write_message",
    "rebuild_config_for_resume_or_fallback_errors_when_cwd_changes",
    "rebuild_config_for_resume_or_fallback_uses_current_config_on_same_cwd_error",
    "refresh_in_memory_config_from_disk_best_effort_keeps_current_config_on_error",
    "refresh_in_memory_config_from_disk_loads_latest_apps_state",
    "refresh_in_memory_config_from_disk_updates_resize_reflow_config",
    "refresh_in_memory_config_from_disk_uses_active_chat_widget_cwd",
    "sandbox_mode_from_effective_config",
    "sync_tui_pet_disabled_updates_chat_widget_config_copy",
    "sync_tui_pet_selection_updates_chat_widget_config_copy",
    "sync_tui_theme_selection_updates_chat_widget_config_copy",
    "update_reasoning_effort_updates_collaboration_mode",
    "windows_sandbox_mode_from_effective_config",
    "windows_toml_from_json",
]
