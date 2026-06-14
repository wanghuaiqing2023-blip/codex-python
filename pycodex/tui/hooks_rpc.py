"""Hook app-server request helpers for the TUI port.

Rust counterpart: ``codex-rs/tui/src/hooks_rpc.rs``.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class HookTrustUpdate:
    key: str
    current_hash: str


@dataclass(frozen=True)
class HookMetadata:
    trust_status: str


@dataclass(frozen=True)
class HooksListEntry:
    cwd: Path
    hooks: list[Any] = field(default_factory=list)
    warnings: list[Any] = field(default_factory=list)
    errors: list[Any] = field(default_factory=list)


@dataclass(frozen=True)
class HooksListResponse:
    data: list[HooksListEntry]


def _request_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _entry_from_value(value: Any) -> HooksListEntry:
    if isinstance(value, HooksListEntry):
        return value
    return HooksListEntry(
        cwd=Path(_field(value, "cwd")),
        hooks=list(_field(value, "hooks", [])),
        warnings=list(_field(value, "warnings", [])),
        errors=list(_field(value, "errors", [])),
    )


def _coerce_response(response: Any) -> HooksListResponse:
    if isinstance(response, HooksListResponse):
        return response
    data = _field(response, "data", [])
    return HooksListResponse([_entry_from_value(entry) for entry in data])


async def _request_typed(request_handle: Any, request: Mapping[str, Any], context: str) -> Any:
    try:
        result = request_handle.request_typed(dict(request))
        if hasattr(result, "__await__"):
            return await result
        return result
    except Exception as exc:
        raise RuntimeError(context) from exc


async def fetch_hooks_list(request_handle: Any, cwd: str | Path) -> HooksListResponse:
    request = {
        "type": "HooksList",
        "request_id": _request_id("hooks-list"),
        "params": {"cwds": [str(Path(cwd))]},
    }
    response = await _request_typed(request_handle, request, "hooks/list failed in TUI")
    return _coerce_response(response)


def hooks_list_entry_for_cwd(response: HooksListResponse | Mapping[str, Any] | Any, cwd: str | Path) -> HooksListEntry:
    target = Path(cwd)
    coerced = _coerce_response(response)
    for entry in coerced.data:
        if Path(entry.cwd) == target:
            return entry
    return HooksListEntry(cwd=target, hooks=[], warnings=[], errors=[])


def hook_needs_review(hook: HookMetadata | Mapping[str, Any] | Any) -> bool:
    return str(_field(hook, "trust_status", "")) in {"Untrusted", "Modified", "untrusted", "modified"}


async def write_hook_trusts(request_handle: Any, trust_updates: list[HookTrustUpdate]) -> Any:
    value = {
        update.key: {"trusted_hash": update.current_hash}
        for update in trust_updates
    }
    request = {
        "type": "ConfigBatchWrite",
        "request_id": _request_id("hooks-config-write"),
        "params": {
            "edits": [
                {
                    "key_path": "hooks.state",
                    "value": value,
                    "merge_strategy": "Upsert",
                }
            ],
            "file_path": None,
            "expected_version": None,
            "reload_user_config": True,
        },
    }
    return await _request_typed(
        request_handle,
        request,
        "config/batchWrite failed while updating hook trust in TUI",
    )


async def write_hook_trust(request_handle: Any, key: str, current_hash: str) -> Any:
    return await write_hook_trusts(request_handle, [HookTrustUpdate(key=key, current_hash=current_hash)])


__all__ = [
    "HookMetadata",
    "HookTrustUpdate",
    "HooksListEntry",
    "HooksListResponse",
    "fetch_hooks_list",
    "hook_needs_review",
    "hooks_list_entry_for_cwd",
    "write_hook_trust",
    "write_hook_trusts",
]
