"""Semantic helpers for Rust ``codex-tui::app::config_persistence``.

Upstream source: ``codex/codex-rs/tui/src/app/config_persistence.rs``.

The Rust module mostly owns app-level async config rebuild/write glue.  Python
ports the module-local pure extraction helpers and keeps runtime persistence
paths explicit ``not_ported`` boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="app::config_persistence",
    source="codex/codex-rs/tui/src/app/config_persistence.rs",
)

DEFAULT_OVERRIDDEN_WRITE_MESSAGE = "the effective config is overridden by a higher-priority layer"


@dataclass(frozen=True)
class OverriddenMetadata:
    message: str


@dataclass(frozen=True)
class ConfigWriteResponse:
    overridden_metadata: OverriddenMetadata | dict[str, Any] | None = None


@dataclass(frozen=True)
class FeatureSpec:
    key: str
    default_enabled: bool = False


@dataclass(frozen=True)
class EffectiveConfigBody:
    additional: dict[str, Any] = field(default_factory=dict)
    approvals_reviewer: Any | None = None
    approval_policy: Any | None = None
    sandbox_mode: Any | None = None


@dataclass(frozen=True)
class ConfigReadResponse:
    config: EffectiveConfigBody | dict[str, Any]


@dataclass(frozen=True)
class MemoriesToml:
    use_memories: bool | None = None
    generate_memories: bool | None = None


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


def features_toml_from_json(value: Any) -> dict[str, bool] | None:
    if value is None or not isinstance(value, dict):
        return None
    entries: dict[str, bool] = {}
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


def approvals_reviewer_from_effective_config(effective_config: Any) -> Any | None:
    config = _effective_config_body(effective_config)
    reviewer = _get_attr_or_key(config, "approvals_reviewer")
    if callable(getattr(reviewer, "to_core", None)):
        return reviewer.to_core()
    return reviewer


def approval_policy_from_effective_config(effective_config: Any) -> Any | None:
    return _get_attr_or_key(_effective_config_body(effective_config), "approval_policy")


def sandbox_mode_from_effective_config(effective_config: Any) -> Any | None:
    return _get_attr_or_key(_effective_config_body(effective_config), "sandbox_mode")


def memories_from_effective_config(effective_config: Any) -> MemoriesToml | None:
    config = _effective_config_body(effective_config)
    additional = _get_attr_or_key(config, "additional", {}) or {}
    raw = additional.get("memories") if isinstance(additional, dict) else None
    if raw is None:
        return None
    if isinstance(raw, MemoriesToml):
        return raw
    if not isinstance(raw, dict):
        return None
    return MemoriesToml(
        use_memories=raw.get("use_memories"),
        generate_memories=raw.get("generate_memories"),
    )


def windows_toml_from_json(value: Any) -> dict[str, Any] | None:
    return value if isinstance(value, dict) else None


def windows_sandbox_mode_from_effective_config(effective_config: Any) -> Any | None:
    config = _effective_config_body(effective_config)
    additional = _get_attr_or_key(config, "additional", {}) or {}
    root_windows = additional.get("windows") if isinstance(additional, dict) else None
    windows = windows_toml_from_json(root_windows)
    return None if windows is None else windows.get("sandbox")


async def update_reasoning_effort_updates_collaboration_mode(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence App reasoning-effort runtime path is not ported")


async def refresh_in_memory_config_from_disk_loads_latest_apps_state(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence disk config reload runtime path is not ported")


async def refresh_in_memory_config_from_disk_best_effort_keeps_current_config_on_error(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence best-effort disk config reload runtime path is not ported")


async def refresh_in_memory_config_from_disk_uses_active_chat_widget_cwd(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence chat-widget cwd config reload runtime path is not ported")


async def refresh_in_memory_config_from_disk_updates_resize_reflow_config(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence resize reflow disk reload runtime path is not ported")


async def overridden_disabled_guardian_does_not_apply_auto_review_companions(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence guardian sync runtime path is not ported")


async def rebuild_config_for_resume_or_fallback_uses_current_config_on_same_cwd_error(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence resume config rebuild runtime path is not ported")


async def rebuild_config_for_resume_or_fallback_errors_when_cwd_changes(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence resume config rebuild runtime path is not ported")


async def sync_tui_theme_selection_updates_chat_widget_config_copy(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence App theme sync runtime path is not ported")


async def sync_tui_pet_selection_updates_chat_widget_config_copy(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence App pet sync runtime path is not ported")


async def sync_tui_pet_disabled_updates_chat_widget_config_copy(*_args: Any, **_kwargs: Any) -> Any:
    raise not_ported("app::config_persistence App pet disabled sync runtime path is not ported")


__all__ = [
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
