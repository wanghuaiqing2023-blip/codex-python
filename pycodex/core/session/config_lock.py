"""Session config-lock helpers aligned with ``core/src/session/config_lock.rs``."""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.config_lock import (
    ConfigLockError,
    ConfigLockReplayOptions,
    ConfigLockfile,
    clear_config_lock_debug_controls,
    config_lock_error,
    config_lockfile,
    toml_round_trip,
    toml_value,
    validate_config_lock_replay,
)
from pycodex.features import FEATURES, Feature


UPSTREAM_SESSION_CONFIG_LOCK = "codex/codex-rs/core/src/session/config_lock.rs"


async def validate_config_lock_if_configured(session_configuration: Any) -> None:
    """Validate replayed session config when the root session supplied a lock."""

    session_source = _field(session_configuration, "session_source")
    is_non_root_agent = getattr(session_source, "is_non_root_agent", None)
    if callable(is_non_root_agent) and is_non_root_agent():
        return

    config = _original_config(session_configuration)
    expected = _field(config, "config_lock_toml")
    if expected is None:
        return

    actual = to_config_lockfile_toml(session_configuration)
    allow_version_mismatch = bool(_field(config, "config_lock_allow_codex_version_mismatch", False))
    try:
        validate_config_lock_replay(
            expected,
            actual,
            ConfigLockReplayOptions(allow_codex_version_mismatch=allow_version_mismatch),
        )
    except ConfigLockError as exc:
        raise config_lock_error(f"config lock replay validation failed: {exc}") from exc


async def export_config_lock_if_configured(
    session_configuration: Any,
    conversation_id: str,
) -> Path | None:
    """Write ``{conversation_id}.config.lock.toml`` when export is configured."""

    if not isinstance(conversation_id, str):
        raise TypeError("conversation_id must be a string")
    config = _original_config(session_configuration)
    export_dir = _field(config, "config_lock_export_dir")
    if export_dir is None:
        return None

    export_path = Path(export_dir)
    lockfile = to_config_lockfile_toml(session_configuration)
    path = export_path / f"{conversation_id}.config.lock.toml"
    try:
        export_path.mkdir(parents=True, exist_ok=True)
        path.write_text(_config_lockfile_to_toml(lockfile), encoding="utf-8")
    except OSError as exc:
        raise config_lock_error(f"failed to write config lock to {path}: {exc}") from exc
    return path


def to_config_lockfile_toml(session_configuration: Any) -> ConfigLockfile:
    """Return a lockfile for the replayable session configuration."""

    return config_lockfile(session_configuration_to_lock_config_toml(session_configuration))


def session_configuration_to_lock_config_toml(session_configuration: Any) -> dict[str, Any]:
    """Build the effective config table used by session lock validation/export."""

    config = _original_config(session_configuration)
    lock_config = _effective_config_mapping(config)
    if bool(_field(config, "config_lock_save_fields_resolved_from_model_catalog", True)):
        _save_session_resolved_fields(session_configuration, lock_config)
    _save_config_resolved_fields(config, lock_config)
    _drop_lockfile_inputs(lock_config)
    return _drop_none(lock_config)


def _save_session_resolved_fields(session_configuration: Any, lock_config: dict[str, Any]) -> None:
    collaboration_mode = _field(session_configuration, "collaboration_mode")
    model = _collaboration_mode_model(collaboration_mode)
    reasoning_effort = _collaboration_mode_reasoning_effort(collaboration_mode)
    if model is not None:
        lock_config["model"] = model
    if reasoning_effort is not None:
        lock_config["model_reasoning_effort"] = _enum_value(reasoning_effort)

    _set_if_present(lock_config, "model_reasoning_summary", session_configuration, "model_reasoning_summary")
    _set_if_present(lock_config, "service_tier", session_configuration, "service_tier")
    _set_if_present(lock_config, "instructions", session_configuration, "base_instructions")
    _set_if_present(lock_config, "developer_instructions", session_configuration, "developer_instructions")
    _set_if_present(lock_config, "compact_prompt", session_configuration, "compact_prompt")
    _set_if_present(lock_config, "personality", session_configuration, "personality")
    _set_if_present(lock_config, "approval_policy", session_configuration, "approval_policy")
    _set_if_present(lock_config, "approvals_reviewer", session_configuration, "approvals_reviewer")


def _save_config_resolved_fields(config: Any, lock_config: dict[str, Any]) -> None:
    _set_if_present(lock_config, "web_search", config, "web_search_mode")
    _set_if_present(lock_config, "model_provider", config, "model_provider_id")
    _set_if_present(lock_config, "plan_mode_reasoning_effort", config, "plan_mode_reasoning_effort")
    _set_if_present(lock_config, "model_verbosity", config, "model_verbosity")
    _set_if_present(lock_config, "include_permissions_instructions", config, "include_permissions_instructions")
    _set_if_present(lock_config, "include_apps_instructions", config, "include_apps_instructions")
    _set_if_present(
        lock_config,
        "include_collaboration_mode_instructions",
        config,
        "include_collaboration_mode_instructions",
    )
    _set_if_present(lock_config, "include_environment_context", config, "include_environment_context")
    _set_if_present(lock_config, "background_terminal_max_timeout", config, "background_terminal_max_timeout")

    features = _field(config, "features")
    feature_entries = _materialized_feature_entries(features)
    if feature_entries:
        lock_config["features"] = feature_entries

    memories = _field(config, "memories")
    if memories is not None:
        lock_config["memories"] = toml_round_trip(_plain_value(memories), "memories")

    agents = dict(lock_config.get("agents") or {})
    if _feature_enabled(features, Feature.MULTI_AGENT_V2):
        agents["max_threads"] = None
    else:
        _set_if_present(agents, "max_threads", config, "agent_max_threads")
    _set_if_present(agents, "max_depth", config, "agent_max_depth")
    _set_if_present(agents, "job_max_runtime_seconds", config, "agent_job_max_runtime_seconds")
    _set_if_present(agents, "interrupt_message", config, "agent_interrupt_message_enabled")
    if agents:
        lock_config["agents"] = agents

    skills = dict(lock_config.get("skills") or {})
    _set_if_present(skills, "include_instructions", config, "include_skill_instructions")
    if skills:
        lock_config["skills"] = skills


def _drop_lockfile_inputs(lock_config: dict[str, Any]) -> None:
    for key in (
        "profile",
        "model_instructions_file",
        "experimental_compact_prompt_file",
        "model_catalog_json",
        "sandbox_mode",
        "sandbox_workspace_write",
        "default_permissions",
        "permissions",
        "experimental_use_unified_exec_tool",
    ):
        lock_config.pop(key, None)
    lock_config["profiles"] = {}
    clear_config_lock_debug_controls(lock_config)


def _original_config(session_configuration: Any) -> Any:
    value = _field(session_configuration, "original_config_do_not_use")
    if value is None:
        value = _field(session_configuration, "original_config")
    if value is None:
        raise config_lock_error("session configuration is missing original config")
    return value


def _effective_config_mapping(config: Any) -> dict[str, Any]:
    stack = _field(config, "config_layer_stack")
    effective = _call_optional(stack, "effective_config")
    if effective is None and isinstance(stack, Mapping):
        effective = _call_optional(stack, "effective_config") or stack.get("effective_config")
    if effective is None and isinstance(stack, Sequence) and not isinstance(stack, (str, bytes)):
        effective = {}
        for layer in stack:
            layer_config = _field(layer, "config", layer if isinstance(layer, Mapping) else None)
            if isinstance(layer_config, Mapping):
                _deep_merge(effective, layer_config)
    if effective is None:
        effective = _field(config, "effective_config", config)
    if callable(effective):
        effective = effective()
    if is_dataclass(effective):
        effective = asdict(effective)
    if not isinstance(effective, Mapping):
        raise config_lock_error("failed to deserialize effective config for config lock")
    return copy.deepcopy(dict(effective))


def _materialized_feature_entries(features: Any) -> dict[str, Any]:
    if features is None:
        return {}
    if hasattr(features, "get") and not isinstance(features, Mapping):
        maybe_features = features.get()
        if maybe_features is not None:
            features = maybe_features

    entries: dict[str, Any] = {}
    for spec in FEATURES:
        enabled = _feature_enabled(features, spec.id)
        if enabled is not None:
            entries[spec.key] = enabled

    multi_agent_v2 = _feature_config_with_enabled(
        _field(features, "multi_agent_v2"),
        entries.get(Feature.MULTI_AGENT_V2.key()),
    )
    if multi_agent_v2 is not None:
        entries[Feature.MULTI_AGENT_V2.key()] = multi_agent_v2

    apps_override = _feature_config_with_enabled(
        _field(features, "apps_mcp_path_override"),
        entries.get(Feature.APPS_MCP_PATH_OVERRIDE.key()),
    )
    if apps_override is not None:
        path = _field(features, "apps_mcp_path_override_path")
        if path is not None:
            apps_override["path"] = str(path)
        entries[Feature.APPS_MCP_PATH_OVERRIDE.key()] = apps_override
    return entries


def _feature_config_with_enabled(value: Any, enabled: Any) -> dict[str, Any] | None:
    data = _plain_value(value) if value is not None else {}
    if data is None:
        data = {}
    if not isinstance(data, Mapping):
        return {"enabled": bool(enabled)} if enabled is not None else None
    result = dict(data)
    if enabled is not None:
        result["enabled"] = bool(enabled)
    return result if result else None


def _feature_enabled(features: Any, feature: Feature) -> bool | None:
    if features is None:
        return None
    enabled = getattr(features, "enabled", None)
    if callable(enabled):
        try:
            return bool(enabled(feature))
        except Exception:
            return None
    if isinstance(features, Mapping):
        raw = features.get(feature.key(), features.get(feature.value))
        return bool(raw) if raw is not None else None
    raw = getattr(features, feature.key(), None)
    if raw is None:
        raw = getattr(features, feature.value, None)
    return bool(raw) if raw is not None else None


def _set_if_present(target: dict[str, Any], key: str, source: Any, source_key: str) -> None:
    value = _field(source, source_key)
    if value is not None:
        target[key] = _plain_value(value)


def _field(source: Any, name: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(name, default)
    return getattr(source, name, default)


def _call_optional(source: Any, name: str) -> Any:
    value = _field(source, name)
    return value() if callable(value) else None


def _collaboration_mode_model(collaboration_mode: Any) -> str | None:
    method = getattr(collaboration_mode, "model", None)
    if callable(method):
        value = method()
    else:
        settings = _field(collaboration_mode, "settings")
        value = _field(settings, "model")
    return str(value) if value is not None else None


def _collaboration_mode_reasoning_effort(collaboration_mode: Any) -> Any:
    method = getattr(collaboration_mode, "reasoning_effort", None)
    if callable(method):
        return method()
    settings = _field(collaboration_mode, "settings")
    return _field(settings, "reasoning_effort")


def _plain_value(value: Any) -> Any:
    if is_dataclass(value):
        return _drop_none(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain_value(item) for item in value]
    text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return value


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _drop_none(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _drop_none(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none(item) for item in value if item is not None]
    return value


def _deep_merge(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), dict):
            _deep_merge(target[key], value)
        else:
            target[str(key)] = copy.deepcopy(value)


def _config_lockfile_to_toml(lockfile: ConfigLockfile) -> str:
    data = toml_value(lockfile, "config lock export")
    lines: list[str] = [
        f"version = {_toml_scalar(data['version'])}",
        f"codex_version = {_toml_scalar(data['codex_version'])}",
        "",
    ]
    _write_toml_table(lines, ("config",), data["config"])
    return "\n".join(lines).rstrip() + "\n"


def _write_toml_table(lines: list[str], path: tuple[str, ...], table: Mapping[str, Any]) -> None:
    scalars: dict[str, Any] = {}
    nested: dict[str, Mapping[str, Any]] = {}
    for key, value in table.items():
        if isinstance(value, Mapping):
            nested[str(key)] = value
        else:
            scalars[str(key)] = value
    if scalars:
        lines.append(f"[{'.'.join(path)}]")
        for key in sorted(scalars):
            lines.append(f"{_toml_key(key)} = {_toml_scalar(scalars[key])}")
        lines.append("")
    for key in sorted(nested):
        _write_toml_table(lines, (*path, key), nested[key])


def _toml_key(key: str) -> str:
    if key.replace("_", "").replace("-", "").isalnum() and key[0].isalpha():
        return key
    return _toml_string(key)


def _toml_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    if isinstance(value, str):
        return _toml_string(value)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return "[" + ", ".join(_toml_scalar(item) for item in value) + "]"
    return _toml_string(str(value))


def _toml_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n").replace("\r", "\\r")
    return f'"{escaped}"'


__all__ = [
    "UPSTREAM_SESSION_CONFIG_LOCK",
    "export_config_lock_if_configured",
    "session_configuration_to_lock_config_toml",
    "to_config_lockfile_toml",
    "validate_config_lock_if_configured",
]
