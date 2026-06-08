"""Agent role helpers aligned with ``codex-rs/core/src/agent/role.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from pycodex.config import toml_compat as _toml
from pycodex.core.config.agent_roles import (
    AGENT_TYPE_UNAVAILABLE_ERROR,
    AWAITER_TOML,
    DEFAULT_ROLE_NAME,
    EXPLORER_TOML,
    AgentRoleConfig,
    AgentRoleError,
    build_spawn_agent_tool_description,
    built_in_agent_role_config_file_contents,
    built_in_agent_role_configs,
    format_role_for_spawn_tool,
    locked_settings_note_for_role,
    parse_agent_role_file_contents,
    resolve_role_config,
)
from pycodex.network_proxy import ConfigLayerEntry, ConfigLayerSource


def build_spawn_agent_role_description(
    user_defined_agent_roles: Mapping[str, AgentRoleConfig],
) -> str:
    """Return Rust's spawn-agent ``agent_type`` description text."""

    return build_spawn_agent_tool_description(user_defined_agent_roles)


def built_in_config_file_contents(path: str | Path) -> str | None:
    """Resolve embedded built-in role config-file contents."""

    return built_in_agent_role_config_file_contents(path)


def apply_role_to_config(config: Any, role_name: str | None = None) -> None:
    """Apply a named role layer to a mutable config object.

    Rust inserts the role config as a high-precedence ``SessionFlags`` layer and
    rebuilds ``Config``.  The Python port mirrors the observable module contract
    for config-like objects: unknown roles produce the Rust-facing unknown-role
    error, role-file failures collapse to the upstream unavailable message, role
    metadata is stripped from user role files, and current provider/service tier
    values remain sticky unless the role explicitly sets those keys.
    """

    selected_role_name = role_name or DEFAULT_ROLE_NAME
    roles = _agent_roles(config)
    role = resolve_role_config(roles, selected_role_name)
    if role is None:
        raise ValueError(f"unknown agent_type '{selected_role_name}'")
    try:
        _apply_role_to_config_inner(config, selected_role_name, role)
    except Exception as exc:
        raise ValueError(AGENT_TYPE_UNAVAILABLE_ERROR) from exc


async def apply_role_to_config_async(config: Any, role_name: str | None = None) -> None:
    """Async wrapper matching Rust's async call site shape."""

    apply_role_to_config(config, role_name)


def _apply_role_to_config_inner(config: Any, role_name: str, role: AgentRoleConfig) -> None:
    role_layer_toml = load_role_layer_toml(config, role.config_file, _is_built_in_role(config, role_name), role_name)
    if not role_layer_toml:
        return

    preserve_current_provider = "model_provider" not in role_layer_toml
    preserve_current_service_tier = "service_tier" not in role_layer_toml
    current_provider = _get_attr_or_mapping(config, "model_provider_id", None)
    current_service_tier = _get_attr_or_mapping(config, "service_tier", None)

    _insert_session_flags_role_layer(config, role_layer_toml)
    _apply_role_layer_fields(config, role_layer_toml)

    if preserve_current_provider and current_provider is not None:
        _set_attr_or_mapping(config, "model_provider_id", current_provider)
    if preserve_current_service_tier and current_service_tier is not None:
        _set_attr_or_mapping(config, "service_tier", current_service_tier)


def load_role_layer_toml(
    config: Any,
    config_file: str | Path | None,
    is_built_in: bool,
    role_name: str,
) -> dict[str, Any]:
    """Load the TOML config layer for a role and strip user role metadata."""

    if config_file is None:
        return {}
    path = Path(config_file)
    if is_built_in:
        contents = built_in_config_file_contents(path)
        if contents is None:
            raise AgentRoleError("No corresponding config content")
        if not contents.strip():
            return {}
        parsed = _toml.loads(contents)
        if not isinstance(parsed, dict):
            raise AgentRoleError("built-in role config must be a TOML table")
        return _resolve_relative_paths_in_config_toml(parsed, _codex_home(config))

    contents = path.read_text(encoding="utf-8")
    parsed_role = parse_agent_role_file_contents(contents, path, path.parent, role_name_hint=role_name)
    return _resolve_relative_paths_in_config_toml(parsed_role.config, path.parent)


def _agent_roles(config: Any) -> Mapping[str, AgentRoleConfig]:
    roles = _get_attr_or_mapping(config, "agent_roles", {})
    if not isinstance(roles, Mapping):
        raise TypeError("config.agent_roles must be a mapping")
    return roles


def _is_built_in_role(config: Any, role_name: str) -> bool:
    return role_name not in _agent_roles(config)


def _codex_home(config: Any) -> Path:
    return Path(_get_attr_or_mapping(config, "codex_home", Path.cwd()))


def _insert_session_flags_role_layer(config: Any, role_layer_toml: Mapping[str, Any]) -> None:
    layer = ConfigLayerEntry(ConfigLayerSource.session_flags(), deepcopy(dict(role_layer_toml)))
    stack = _get_attr_or_mapping(config, "config_layer_stack", None)
    if stack is None:
        _set_attr_or_mapping(config, "config_layer_stack", [layer])
        return
    if hasattr(stack, "get_layers"):
        try:
            layers = list(stack.get_layers("lowest_precedence_first", True))
        except TypeError:
            layers = list(stack.get_layers())
        layers.append(layer)
        if hasattr(stack, "layers"):
            setattr(stack, "layers", layers)
        else:
            _set_attr_or_mapping(config, "config_layer_stack", layers)
        return
    if isinstance(stack, list):
        stack.append(layer)
        return
    if isinstance(stack, tuple):
        _set_attr_or_mapping(config, "config_layer_stack", [*stack, layer])
        return
    raise TypeError("config_layer_stack must be list-like or expose get_layers")


def _apply_role_layer_fields(config: Any, role_layer_toml: Mapping[str, Any]) -> None:
    existing_effective = _config_mapping(config)
    merged = deepcopy(existing_effective)
    _deep_merge_mapping(merged, role_layer_toml)
    for key, value in merged.items():
        _set_attr_or_mapping(config, _python_config_field_name(key), value)


def _config_mapping(config: Any) -> dict[str, Any]:
    if isinstance(config, Mapping):
        return dict(config)
    result: dict[str, Any] = {}
    for name in (
        "model",
        "model_provider",
        "model_provider_id",
        "model_reasoning_effort",
        "service_tier",
        "developer_instructions",
        "codex_linux_sandbox_exe",
        "main_execve_wrapper_exe",
    ):
        if hasattr(config, name):
            result[name] = getattr(config, name)
    return result


def _python_config_field_name(toml_key: str) -> str:
    if toml_key == "model_provider":
        return "model_provider_id"
    return toml_key


def _resolve_relative_paths_in_config_toml(config_toml: Mapping[str, Any], base: Path) -> dict[str, Any]:
    resolved = deepcopy(dict(config_toml))
    _resolve_relative_paths_in_place(resolved, base)
    return resolved


def _resolve_relative_paths_in_place(value: Any, base: Path) -> None:
    if isinstance(value, dict):
        for key, child in list(value.items()):
            if isinstance(child, str) and _looks_like_path_key(key):
                path = Path(child)
                value[key] = str(path if path.is_absolute() else base / path)
            else:
                _resolve_relative_paths_in_place(child, base)
    elif isinstance(value, list):
        for child in value:
            _resolve_relative_paths_in_place(child, base)


def _looks_like_path_key(key: Any) -> bool:
    return isinstance(key, str) and (key == "path" or key.endswith("_path") or key.endswith("_file"))


def _deep_merge_mapping(target: dict[str, Any], source: Mapping[str, Any]) -> None:
    for key, value in source.items():
        if isinstance(value, Mapping) and isinstance(target.get(key), Mapping):
            child = dict(target[key])
            _deep_merge_mapping(child, value)
            target[key] = child
        else:
            target[key] = deepcopy(value)


def _get_attr_or_mapping(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _set_attr_or_mapping(obj: Any, key: str, value: Any) -> None:
    if isinstance(obj, dict):
        obj[key] = value
    else:
        setattr(obj, key, value)


__all__ = [
    "AGENT_TYPE_UNAVAILABLE_ERROR",
    "AWAITER_TOML",
    "DEFAULT_ROLE_NAME",
    "EXPLORER_TOML",
    "AgentRoleConfig",
    "apply_role_to_config",
    "apply_role_to_config_async",
    "build_spawn_agent_role_description",
    "build_spawn_agent_tool_description",
    "built_in_agent_role_config_file_contents",
    "built_in_agent_role_configs",
    "built_in_config_file_contents",
    "format_role_for_spawn_tool",
    "load_role_layer_toml",
    "locked_settings_note_for_role",
    "resolve_role_config",
]
