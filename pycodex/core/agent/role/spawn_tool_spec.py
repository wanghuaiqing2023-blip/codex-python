"""Spawn-agent tool description from ``agent::role::spawn_tool_spec``."""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pycodex.config import toml_compat as _toml
from pycodex.core.config.agent_roles import AgentRoleConfig

from . import built_in


DEFAULT_ROLE_NAME = "default"


def build(user_defined_agent_roles: Mapping[str, AgentRoleConfig]) -> str:
    """Build the spawn-agent ``agent_type`` description."""

    return build_from_configs(built_in.configs(), user_defined_agent_roles)


def build_from_configs(
    built_in_roles: Mapping[str, AgentRoleConfig],
    user_defined_roles: Mapping[str, AgentRoleConfig],
) -> str:
    """Build a description from explicit role maps, matching the Rust test seam."""

    if not isinstance(built_in_roles, Mapping) or not isinstance(user_defined_roles, Mapping):
        raise TypeError("agent roles must be mappings")
    seen: set[str] = set()
    formatted_roles: list[str] = []
    for roles in (user_defined_roles, built_in_roles):
        for name, declaration in sorted(roles.items()):
            if not isinstance(name, str):
                raise TypeError("agent role names must be strings")
            if not isinstance(declaration, AgentRoleConfig):
                raise TypeError("agent role declarations must be AgentRoleConfig values")
            if name not in seen:
                seen.add(name)
                formatted_roles.append(format_role(name, declaration))
    return (
        f"Optional type name for the new agent. If omitted, `{DEFAULT_ROLE_NAME}` is used.\n"
        "Available roles:\n"
        + "\n".join(formatted_roles)
    )


def format_role(name: str, declaration: AgentRoleConfig) -> str:
    """Format one role declaration for the spawn tool specification."""

    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not isinstance(declaration, AgentRoleConfig):
        raise TypeError("declaration must be an AgentRoleConfig")
    if declaration.description is None:
        return f"{name}: no description"
    return f"{name}: {{\n{declaration.description}{_locked_settings_note(declaration)}\n}}"


def _locked_settings_note(declaration: AgentRoleConfig) -> str:
    if declaration.config_file is None:
        return ""
    contents = built_in.config_file_contents(declaration.config_file)
    if contents is None:
        try:
            contents = Path(declaration.config_file).read_text(encoding="utf-8")
        except OSError:
            return ""
    if not contents.strip():
        return ""
    try:
        role_toml = _toml.loads(contents)
    except _toml.TOMLDecodeError:
        return ""

    model = _optional_str(role_toml.get("model"))
    reasoning_effort = _optional_str(role_toml.get("model_reasoning_effort"))
    service_tier = _optional_str(role_toml.get("service_tier"))
    if model is not None and reasoning_effort is not None:
        model_note = (
            f"\n- This role's model is set to `{model}` and its reasoning effort is set to "
            f"`{reasoning_effort}`. These settings cannot be changed."
        )
    elif model is not None:
        model_note = f"\n- This role's model is set to `{model}` and cannot be changed."
    elif reasoning_effort is not None:
        model_note = (
            f"\n- This role's reasoning effort is set to `{reasoning_effort}` and cannot be changed."
        )
    else:
        model_note = ""
    tier_note = (
        f"\n- This role's service tier is set to `{service_tier}`. If it is supported by the resolved model, "
        "it takes precedence over a valid spawn request service tier."
        if service_tier is not None
        else ""
    )
    return model_note + tier_note


def _optional_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


__all__ = ["build", "build_from_configs", "format_role"]
