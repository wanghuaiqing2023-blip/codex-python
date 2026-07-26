"""Role configuration reload owned by ``agent::role::reload``."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from pycodex.app_server_protocol.config import ConfigLayerSource
from pycodex.config.state import ConfigLayerEntry


def build_next_config(
    config: Any,
    role_layer_toml: Mapping[str, Any],
    preserve_current_provider: bool,
    preserve_current_service_tier: bool,
) -> Any:
    """Insert the role layer and rebuild the observable Python config state."""

    current_provider = _get_attr_or_mapping(config, "model_provider_id", None)
    current_service_tier = _get_attr_or_mapping(config, "service_tier", None)
    _insert_session_flags_role_layer(config, role_layer_toml)
    _apply_role_layer_fields(config, role_layer_toml)
    if preserve_current_provider and current_provider is not None:
        _set_attr_or_mapping(config, "model_provider_id", current_provider)
    if preserve_current_service_tier and current_service_tier is not None:
        _set_attr_or_mapping(config, "service_tier", current_service_tier)
    return config


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
    merged = deepcopy(_config_mapping(config))
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
    return "model_provider_id" if toml_key == "model_provider" else toml_key


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


__all__ = ["build_next_config"]
