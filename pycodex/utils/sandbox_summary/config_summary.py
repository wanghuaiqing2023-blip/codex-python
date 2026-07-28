"""Effective configuration summaries from ``config_summary.rs``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .sandbox_summary import summarize_sandbox_policy


def create_config_summary_entries(config: Any, model: str) -> list[tuple[str, str]]:
    cwd = _field(config, "cwd", "")
    provider_id = _field(config, "model_provider_id", "")
    permissions = _field(config, "permissions", None)
    approval_policy = _field(permissions, "approval_policy", "")
    approval_value = _call_method(approval_policy, "value", approval_policy)
    legacy_policy = _call_method(permissions, "legacy_sandbox_policy", None, Path(cwd))
    entries = [
        ("workdir", str(cwd)),
        ("model", str(model)),
        ("provider", str(provider_id)),
        ("approval", str(approval_value)),
        ("sandbox", summarize_sandbox_policy(legacy_policy)),
    ]
    model_provider = _field(config, "model_provider", None)
    if str(_field(model_provider, "wire_api", "")).lower().endswith("responses"):
        entries.append(("reasoning effort", str(_field(config, "model_reasoning_effort", None) or "none")))
        entries.append(("reasoning summaries", str(_field(config, "model_reasoning_summary", None) or "none")))
    return entries


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _call_method(value: Any, name: str, default: Any = None, *args: Any) -> Any:
    method = getattr(value, name, None)
    if callable(method):
        return method(*args)
    return default


__all__ = ["create_config_summary_entries"]
