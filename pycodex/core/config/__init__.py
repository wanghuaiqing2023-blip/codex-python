"""Configuration helpers aligned with ``codex-rs/core/src/config``."""

from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping

from pycodex.core.config.permissions import (
    is_builtin_permission_profile_name,
    validate_user_permission_profile_names,
)
from pycodex.core.config.schema import (
    canonicalize,
    config_schema_json,
    write_config_schema,
)

DEFAULT_IGNORE_LARGE_UNTRACKED_DIRS = 200
DEFAULT_IGNORE_LARGE_UNTRACKED_FILES = 10 * 1024 * 1024
DEFAULT_MULTI_AGENT_V2_MAX_CONCURRENT_THREADS_PER_SESSION = 4
DEFAULT_MULTI_AGENT_V2_MIN_WAIT_TIMEOUT_MS = 10_000
DEFAULT_MULTI_AGENT_V2_MAX_WAIT_TIMEOUT_MS = 3_600_000
DEFAULT_MULTI_AGENT_V2_DEFAULT_WAIT_TIMEOUT_MS = 30_000
LOCAL_DEV_BUILD_VERSION = "0.0.0"
CONFIG_TOML_FILE = "config.toml"
SQLITE_HOME_ENV = "CODEX_SQLITE_HOME"


class AuthCredentialsStoreMode(str, Enum):
    FILE = "file"
    KEYRING = "keyring"
    AUTO = "auto"
    EPHEMERAL = "ephemeral"


class OAuthCredentialsStoreMode(str, Enum):
    AUTO = "auto"
    FILE = "file"
    KEYRING = "keyring"


@dataclass(frozen=True)
class GhostSnapshotConfig:
    ignore_large_untracked_files: int | None = DEFAULT_IGNORE_LARGE_UNTRACKED_FILES
    ignore_large_untracked_dirs: int | None = DEFAULT_IGNORE_LARGE_UNTRACKED_DIRS
    disable_warnings: bool = False


@dataclass(frozen=True)
class MultiAgentV2Config:
    max_concurrent_threads_per_session: int = DEFAULT_MULTI_AGENT_V2_MAX_CONCURRENT_THREADS_PER_SESSION
    min_wait_timeout_ms: int = DEFAULT_MULTI_AGENT_V2_MIN_WAIT_TIMEOUT_MS
    max_wait_timeout_ms: int = DEFAULT_MULTI_AGENT_V2_MAX_WAIT_TIMEOUT_MS
    default_wait_timeout_ms: int = DEFAULT_MULTI_AGENT_V2_DEFAULT_WAIT_TIMEOUT_MS
    usage_hint_enabled: bool = True
    usage_hint_text: str | None = None
    root_agent_usage_hint_text: str | None = None
    subagent_usage_hint_text: str | None = None
    tool_namespace: str | None = None
    hide_spawn_agent_metadata: bool = False
    non_code_mode_only: bool = False


@dataclass(frozen=True)
class ThreadStoreConfig:
    kind: str
    id: str | None = None

    @classmethod
    def local(cls) -> "ThreadStoreConfig":
        return cls("local")

    @classmethod
    def in_memory(cls, id: str) -> "ThreadStoreConfig":
        if not isinstance(id, str):
            raise TypeError("thread store id must be a string")
        return cls("in_memory", id=id)


@dataclass(frozen=True)
class EffectivePermissionSelection:
    profiles: Mapping[str, Any] | None
    selected_profile_id: str | None
    requirements_force_profile_selection: bool = False


def resolve_sqlite_home_env(resolved_cwd: str | os.PathLike[str], env: Mapping[str, str] | None = None) -> Path | None:
    """Resolve ``CODEX_SQLITE_HOME`` like Rust ``resolve_sqlite_home_env``."""

    raw = (os.environ if env is None else env).get(SQLITE_HOME_ENV)
    if raw is None:
        return None
    trimmed = raw.strip()
    if not trimmed:
        return None
    path = Path(trimmed)
    if path.is_absolute():
        return path
    return Path(resolved_cwd) / path


def resolve_cli_auth_credentials_store_mode(
    configured: AuthCredentialsStoreMode | str,
    package_version: str,
) -> AuthCredentialsStoreMode:
    mode = AuthCredentialsStoreMode(configured)
    if package_version == LOCAL_DEV_BUILD_VERSION and mode in {
        AuthCredentialsStoreMode.KEYRING,
        AuthCredentialsStoreMode.AUTO,
    }:
        return AuthCredentialsStoreMode.FILE
    return mode


def resolve_mcp_oauth_credentials_store_mode(
    configured: OAuthCredentialsStoreMode | str,
    package_version: str,
) -> OAuthCredentialsStoreMode:
    mode = OAuthCredentialsStoreMode(configured)
    if package_version == LOCAL_DEV_BUILD_VERSION and mode in {
        OAuthCredentialsStoreMode.KEYRING,
        OAuthCredentialsStoreMode.AUTO,
    }:
        return OAuthCredentialsStoreMode.FILE
    return mode


def thread_store_config(thread_store: Mapping[str, Any] | ThreadStoreConfig | None) -> ThreadStoreConfig:
    if thread_store is None:
        return ThreadStoreConfig.local()
    if isinstance(thread_store, ThreadStoreConfig):
        return thread_store
    if not isinstance(thread_store, Mapping):
        raise TypeError("thread_store must be a mapping, ThreadStoreConfig, or None")
    kind = thread_store.get("type", "local")
    if kind == "local":
        return ThreadStoreConfig.local()
    if kind == "in_memory":
        item = thread_store.get("id")
        if not isinstance(item, str):
            raise TypeError("in_memory thread store requires string id")
        return ThreadStoreConfig.in_memory(item)
    raise ValueError(f"unknown thread store type: {kind}")


def ghost_snapshot_config(ghost_snapshot: Mapping[str, Any] | None) -> GhostSnapshotConfig:
    config = GhostSnapshotConfig()
    if ghost_snapshot is None:
        return config
    if not isinstance(ghost_snapshot, Mapping):
        raise TypeError("ghost_snapshot must be a mapping or None")

    files = _optional_int(ghost_snapshot, "ignore_large_untracked_files", config.ignore_large_untracked_files)
    dirs = _optional_int(ghost_snapshot, "ignore_large_untracked_dirs", config.ignore_large_untracked_dirs)
    disable_warnings = ghost_snapshot.get("disable_warnings", config.disable_warnings)
    if not isinstance(disable_warnings, bool):
        raise TypeError("disable_warnings must be a bool")
    return GhostSnapshotConfig(
        ignore_large_untracked_files=files if files is not None and files > 0 else None,
        ignore_large_untracked_dirs=dirs if dirs is not None and dirs > 0 else None,
        disable_warnings=disable_warnings,
    )


def resolve_multi_agent_v2_config(config_toml: Mapping[str, Any] | None) -> MultiAgentV2Config:
    """Resolve Rust ``Config::multi_agent_v2`` defaults from ``[features]``."""

    config = config_toml or {}
    features = config.get("features")
    raw = features.get("multi_agent_v2") if isinstance(features, Mapping) else None
    values = raw if isinstance(raw, Mapping) else {}
    defaults = MultiAgentV2Config()
    return MultiAgentV2Config(
        max_concurrent_threads_per_session=_config_int(
            values,
            "max_concurrent_threads_per_session",
            defaults.max_concurrent_threads_per_session,
        ),
        min_wait_timeout_ms=_config_int(values, "min_wait_timeout_ms", defaults.min_wait_timeout_ms),
        max_wait_timeout_ms=_config_int(values, "max_wait_timeout_ms", defaults.max_wait_timeout_ms),
        default_wait_timeout_ms=_config_int(
            values,
            "default_wait_timeout_ms",
            defaults.default_wait_timeout_ms,
        ),
        usage_hint_enabled=_config_bool(values, "usage_hint_enabled", defaults.usage_hint_enabled),
        usage_hint_text=_config_optional_str(values, "usage_hint_text"),
        root_agent_usage_hint_text=_config_optional_str(values, "root_agent_usage_hint_text"),
        subagent_usage_hint_text=_config_optional_str(values, "subagent_usage_hint_text"),
        tool_namespace=_config_optional_str(values, "tool_namespace"),
        hide_spawn_agent_metadata=_config_bool(
            values,
            "hide_spawn_agent_metadata",
            defaults.hide_spawn_agent_metadata,
        ),
        non_code_mode_only=_config_bool(values, "non_code_mode_only", defaults.non_code_mode_only),
    )


def guardian_policy_config_from_requirements(requirements_toml: Mapping[str, Any] | None) -> str | None:
    if requirements_toml is None:
        return None
    return normalize_guardian_policy_config(requirements_toml.get("guardian_policy_config"))


def normalize_guardian_policy_config(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError("guardian_policy_config must be a string or None")
    trimmed = value.strip()
    return trimmed or None


def merge_managed_permission_profiles(
    configured_permissions: Mapping[str, Any] | None,
    requirements_toml: Mapping[str, Any] | None,
) -> dict[str, Any] | None:
    requirements = requirements_toml or {}
    managed_profiles = _managed_permission_profiles(requirements)
    if not managed_profiles:
        return dict(_permission_entries(configured_permissions)) if configured_permissions is not None else None

    merged = dict(_permission_entries(configured_permissions))
    for profile_id, managed_profile in managed_profiles.items():
        if profile_id in merged:
            raise ValueError(
                "requirements.toml permissions profile "
                f"`{profile_id}` conflicts with a config-defined profile of the same name"
            )
        merged[profile_id] = managed_profile
    return merged


def resolve_effective_permission_selection(
    configured_permissions: Mapping[str, Any] | None,
    default_permissions_override: str | None,
    configured_default_permissions: str | None,
    requirements_toml: Mapping[str, Any] | None,
    startup_warnings: list[str],
) -> EffectivePermissionSelection:
    profiles = merge_managed_permission_profiles(configured_permissions, requirements_toml)
    validate_user_permission_profile_names(profiles)
    validate_required_permission_profile_catalog(requirements_toml, profiles)
    selected_profile_id = resolve_default_permissions(
        default_permissions_override,
        configured_default_permissions,
        requirements_toml,
        startup_warnings,
    )
    return EffectivePermissionSelection(
        profiles=profiles,
        selected_profile_id=selected_profile_id,
        requirements_force_profile_selection=(requirements_toml or {}).get("allowed_permissions") is not None,
    )


def resolve_default_permissions(
    default_permissions_override: str | None,
    configured_default_permissions: str | None,
    requirements_toml: Mapping[str, Any] | None,
    startup_warnings: list[str],
) -> str | None:
    requirements = requirements_toml or {}
    allowed_permissions = requirements.get("allowed_permissions")
    default_permissions = (
        default_permissions_override
        if default_permissions_override is not None
        else configured_default_permissions
    )
    if (
        default_permissions is not None
        and allowed_permissions is not None
        and not is_builtin_permission_profile_name(default_permissions)
        and default_permissions not in _string_list(allowed_permissions, "allowed_permissions")
    ):
        allowed = _string_list(allowed_permissions, "allowed_permissions")
        if not allowed:
            raise ValueError("requirements.toml allowed_permissions must include at least one profile")
        fallback = allowed[0]
        startup_warnings.append(
            "Configured value for `permission_profile` is disallowed by requirements; "
            f"falling back from `{default_permissions}` to required value `{fallback}`."
        )
        default_permissions = fallback
    return default_permissions


def validate_required_permission_profile_catalog(
    requirements_toml: Mapping[str, Any] | None,
    available_permissions: Mapping[str, Any] | None,
) -> None:
    requirements = requirements_toml or {}
    allowed_permissions = requirements.get("allowed_permissions")
    if allowed_permissions is None:
        return
    allowed = _string_list(allowed_permissions, "allowed_permissions")
    if not allowed:
        raise ValueError("requirements.toml allowed_permissions must include at least one profile")
    entries = set((available_permissions or {}).keys())
    for profile_id in allowed:
        if not is_builtin_permission_profile_name(profile_id) and profile_id not in entries:
            raise ValueError(f"requirements.toml allowed_permissions refers to undefined profile `{profile_id}`")


def profile_allows_configured_network_proxy(permission_profile: Any) -> bool:
    profile_type = getattr(permission_profile, "type", None)
    if profile_type is None and isinstance(permission_profile, Mapping):
        profile_type = permission_profile.get("type")
    if profile_type not in {"managed", "external"}:
        return False
    network = getattr(permission_profile, "network", None)
    if network is None and isinstance(permission_profile, Mapping):
        network = permission_profile.get("network")
    return _network_permission_is_enabled(network)


def build_network_proxy_spec(
    configured_network_proxy_config: Any,
    network_requirements: Any | None,
    permission_profile: Any,
) -> Any | None:
    from pycodex.network_proxy import NetworkProxySpec

    requirements, source = _sourced_value_and_source(network_requirements)
    has_network_requirements = requirements is not None
    try:
        network = NetworkProxySpec.from_config_and_constraints(
            configured_network_proxy_config,
            requirements,
            permission_profile,
        )
    except Exception as exc:
        if source is not None:
            raise type(exc)(f"failed to build managed network proxy from {source}: {exc}") from exc
        raise
    if has_network_requirements:
        return network
    return network if network.enabled() else None


def _optional_int(value: Mapping[str, Any], key: str, default: int | None) -> int | None:
    item = value.get(key, default)
    if item is None:
        return None
    if not isinstance(item, int):
        raise TypeError(f"{key} must be an integer or None")
    return item


def _config_int(value: Mapping[str, Any], key: str, default: int) -> int:
    item = value.get(key, default)
    if isinstance(item, bool) or not isinstance(item, int):
        raise TypeError(f"{key} must be an integer")
    return item


def _config_bool(value: Mapping[str, Any], key: str, default: bool) -> bool:
    item = value.get(key, default)
    if not isinstance(item, bool):
        raise TypeError(f"{key} must be a bool")
    return item


def _config_optional_str(value: Mapping[str, Any], key: str) -> str | None:
    item = value.get(key)
    if item is not None and not isinstance(item, str):
        raise TypeError(f"{key} must be a string or None")
    return item


def _network_permission_is_enabled(network: Any) -> bool:
    checker = getattr(network, "is_enabled", None)
    if callable(checker):
        return bool(checker())
    if isinstance(network, Mapping):
        if "enabled" in network:
            return bool(network["enabled"])
        if "policy" in network:
            return str(network["policy"]).lower() in {"enabled", "restricted", "limited", "proxy"}
    if isinstance(network, str):
        return network.lower() in {"enabled", "restricted", "limited", "proxy"}
    return bool(network)


def _sourced_value_and_source(value: Any | None) -> tuple[Any | None, Any | None]:
    if value is None:
        return None, None
    if isinstance(value, Mapping) and "value" in value:
        return value.get("value"), value.get("source")
    if hasattr(value, "value"):
        return getattr(value, "value"), getattr(value, "source", None)
    return value, None


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise TypeError(f"{label} must be a list of strings")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"{label} must be a list of strings")
    return list(value)


def _permission_entries(permissions: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if permissions is None:
        return {}
    if not isinstance(permissions, Mapping):
        raise TypeError("permissions must be a mapping or None")
    entries = permissions.get("entries")
    if isinstance(entries, Mapping):
        return entries
    profiles = permissions.get("profiles")
    if isinstance(profiles, Mapping):
        return profiles
    return permissions


def _managed_permission_profiles(requirements_toml: Mapping[str, Any]) -> Mapping[str, Any]:
    permissions = requirements_toml.get("permissions")
    if not isinstance(permissions, Mapping):
        return {}
    profiles = permissions.get("profiles")
    if profiles is None:
        return {}
    if not isinstance(profiles, Mapping):
        raise TypeError("requirements.toml permissions.profiles must be a mapping")
    return profiles


__all__ = [
    "AuthCredentialsStoreMode",
    "CONFIG_TOML_FILE",
    "DEFAULT_MULTI_AGENT_V2_DEFAULT_WAIT_TIMEOUT_MS",
    "DEFAULT_MULTI_AGENT_V2_MAX_CONCURRENT_THREADS_PER_SESSION",
    "DEFAULT_MULTI_AGENT_V2_MAX_WAIT_TIMEOUT_MS",
    "DEFAULT_MULTI_AGENT_V2_MIN_WAIT_TIMEOUT_MS",
    "DEFAULT_IGNORE_LARGE_UNTRACKED_DIRS",
    "DEFAULT_IGNORE_LARGE_UNTRACKED_FILES",
    "EffectivePermissionSelection",
    "GhostSnapshotConfig",
    "LOCAL_DEV_BUILD_VERSION",
    "MultiAgentV2Config",
    "OAuthCredentialsStoreMode",
    "SQLITE_HOME_ENV",
    "ThreadStoreConfig",
    "canonicalize",
    "build_network_proxy_spec",
    "config_schema_json",
    "ghost_snapshot_config",
    "guardian_policy_config_from_requirements",
    "merge_managed_permission_profiles",
    "normalize_guardian_policy_config",
    "profile_allows_configured_network_proxy",
    "resolve_effective_permission_selection",
    "resolve_cli_auth_credentials_store_mode",
    "resolve_default_permissions",
    "resolve_mcp_oauth_credentials_store_mode",
    "resolve_multi_agent_v2_config",
    "resolve_sqlite_home_env",
    "thread_store_config",
    "validate_required_permission_profile_catalog",
    "write_config_schema",
]
