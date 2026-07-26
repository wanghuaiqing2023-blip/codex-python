"""Agent role application aligned with ``core/src/agent/role.rs``."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

from pycodex.config import toml_compat as _toml
from pycodex.core.config.agent_roles import AgentRoleConfig, AgentRoleError, parse_agent_role_file_contents

from . import built_in, reload, spawn_tool_spec


DEFAULT_ROLE_NAME = "default"
AGENT_TYPE_UNAVAILABLE_ERROR = "agent type is currently not available"


def apply_role_to_config(config: Any, role_name: str | None = None) -> None:
    """Apply a named role layer to a mutable config object."""

    selected_role_name = role_name or DEFAULT_ROLE_NAME
    role = resolve_role_config(config, selected_role_name)
    if role is None:
        raise ValueError(f"unknown agent_type '{selected_role_name}'")
    try:
        _apply_role_to_config_inner(config, selected_role_name, role)
    except Exception as exc:
        raise ValueError(AGENT_TYPE_UNAVAILABLE_ERROR) from exc


async def apply_role_to_config_async(config: Any, role_name: str | None = None) -> None:
    """Async call shape used by the Rust-owned spawn path."""

    apply_role_to_config(config, role_name)


def _apply_role_to_config_inner(config: Any, role_name: str, role: AgentRoleConfig) -> None:
    role_layer_toml = load_role_layer_toml(
        config,
        role.config_file,
        role_name not in _agent_roles(config),
        role_name,
    )
    if not role_layer_toml:
        return
    reload.build_next_config(
        config,
        role_layer_toml,
        preserve_current_provider="model_provider" not in role_layer_toml,
        preserve_current_service_tier="service_tier" not in role_layer_toml,
    )


def load_role_layer_toml(
    config: Any,
    config_file: str | Path | None,
    is_built_in: bool,
    role_name: str,
) -> dict[str, Any]:
    """Load and resolve a role configuration layer."""

    if config_file is None:
        return {}
    path = Path(config_file)
    if is_built_in:
        contents = built_in.config_file_contents(path)
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


def resolve_role_config(config: Any, role_name: str) -> AgentRoleConfig | None:
    """Resolve a configured role before falling back to built-ins."""

    if not isinstance(role_name, str):
        raise TypeError("role_name must be a string")
    return _agent_roles(config).get(role_name) or built_in.configs().get(role_name)


def _agent_roles(config: Any) -> Mapping[str, AgentRoleConfig]:
    missing = object()
    roles = config.get("agent_roles", missing) if isinstance(config, Mapping) else getattr(config, "agent_roles", missing)
    if roles is missing:
        raise TypeError("config must expose agent_roles")
    if not isinstance(roles, Mapping):
        raise TypeError("config.agent_roles must be a mapping")
    return roles


def _codex_home(config: Any) -> Path:
    value = config.get("codex_home", Path.cwd()) if isinstance(config, Mapping) else getattr(config, "codex_home", Path.cwd())
    return Path(value)


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


__all__ = [
    "DEFAULT_ROLE_NAME",
    "apply_role_to_config",
    "apply_role_to_config_async",
    "load_role_layer_toml",
    "resolve_role_config",
    "spawn_tool_spec",
]
