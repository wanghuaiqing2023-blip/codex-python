"""Hook trust helpers derived from ``core/tests/common/hooks.rs``."""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any


def trusted_config_layer_stack(
    config_layer_stack: Mapping[str, Any],
    _codex_home: object,
    hooks: Iterable[Any],
) -> dict[str, Any]:
    updated = copy.deepcopy(dict(config_layer_stack))
    user = updated.setdefault("user", {})
    config = user.setdefault("config", {}) if isinstance(user, dict) else {}
    state = config.setdefault("hooks", {}).setdefault("state", {})
    for hook in hooks:
        key = hook.key if hasattr(hook, "key") else hook["key"]
        current_hash = (
            hook.current_hash if hasattr(hook, "current_hash") else hook["current_hash"]
        )
        state[str(key)] = {"trusted_hash": str(current_hash)}
    return updated


def trust_hooks(config: Any, hooks: Iterable[Any]) -> None:
    stack = getattr(config, "config_layer_stack", None)
    if stack is None and isinstance(config, dict):
        stack = config.setdefault("config_layer_stack", {})
    updated = trusted_config_layer_stack(stack or {}, getattr(config, "codex_home", None), hooks)
    if isinstance(config, dict):
        config["config_layer_stack"] = updated
    else:
        config.config_layer_stack = updated


def trust_discovered_hooks(config: Any) -> None:
    hooks = getattr(config, "discovered_hooks", None)
    if hooks is None and isinstance(config, dict):
        hooks = config.get("discovered_hooks")
    if not hooks:
        raise AssertionError("trusted hook fixture should discover at least one hook")
    trust_hooks(config, hooks)


__all__ = ["trust_discovered_hooks", "trust_hooks", "trusted_config_layer_stack"]
