"""Sandbox and config summary helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable


def summarize_sandbox_policy(sandbox_policy: Any) -> str:
    kind = _policy_kind(sandbox_policy)
    if kind == "danger-full-access":
        return "danger-full-access"
    if kind == "read-only":
        summary = "read-only"
        if bool(_field(sandbox_policy, "network_access", False)):
            summary += " (network access enabled)"
        return summary
    if kind == "external-sandbox":
        summary = "external-sandbox"
        if _network_enabled(_field(sandbox_policy, "network_access", None)):
            summary += " (network access enabled)"
        return summary
    if kind == "workspace-write":
        entries = ["workdir"]
        if not bool(_field(sandbox_policy, "exclude_slash_tmp", False)):
            entries.append("/tmp")
        if not bool(_field(sandbox_policy, "exclude_tmpdir_env_var", False)):
            entries.append("$TMPDIR")
        entries.extend(str(path) for path in _field(sandbox_policy, "writable_roots", []) or [])
        summary = f"workspace-write [{', '.join(entries)}]"
        if bool(_field(sandbox_policy, "network_access", False)):
            summary += " (network access enabled)"
        return summary
    return str(kind or sandbox_policy)


def summarize_permission_profile(permission_profile: Any, cwd: Path | str, workspace_roots: Iterable[Path | str]) -> str:
    try:
        policy = _call_method(permission_profile, "to_legacy_sandbox_policy", Path(cwd))
    except Exception:
        network = _call_method(permission_profile, "network_sandbox_policy", None)
        return "custom permissions (network access enabled)" if _network_enabled(network) else "custom permissions"
    if _policy_kind(policy) == "workspace-write":
        entries = ["workdir"]
        if not bool(_field(policy, "exclude_slash_tmp", False)):
            entries.append("/tmp")
        if not bool(_field(policy, "exclude_tmpdir_env_var", False)):
            entries.append("$TMPDIR")
        cwd_text = str(cwd)
        entries.extend(str(root) for root in workspace_roots if str(root) != cwd_text)
        summary = f"workspace-write [{', '.join(entries)}]"
        if bool(_field(policy, "network_access", False)):
            summary += " (network access enabled)"
        return summary
    return summarize_sandbox_policy(policy)


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


def _policy_kind(value: Any) -> str | None:
    raw = _field(value, "kind", None) or _field(value, "type", None) or _field(value, "name", None)
    if raw is None:
        raw = value.__class__.__name__ if value is not None else None
    text = str(raw).replace("_", "-").lower() if raw is not None else None
    mapping = {
        "dangerfullaccess": "danger-full-access",
        "danger-full-access": "danger-full-access",
        "readonly": "read-only",
        "read-only": "read-only",
        "externalsandbox": "external-sandbox",
        "external-sandbox": "external-sandbox",
        "workspacewrite": "workspace-write",
        "workspace-write": "workspace-write",
    }
    return mapping.get(text or "", text)


def _network_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    checker = getattr(value, "is_enabled", None)
    if callable(checker):
        return bool(checker())
    return str(value).lower().endswith("enabled") or str(value).lower() == "enabled"


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _call_method(value: Any, name: str, default: Any = None, *args: Any) -> Any:
    method = getattr(value, name, None)
    if callable(method):
        return method(*args)
    return default


__all__ = [
    "create_config_summary_entries",
    "summarize_permission_profile",
    "summarize_sandbox_policy",
]
