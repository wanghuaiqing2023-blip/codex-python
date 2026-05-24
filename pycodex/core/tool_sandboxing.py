"""Tool approval and sandboxing primitives ported from Codex core.

This module mirrors the policy-independent helpers in
``codex/codex-rs/core/src/tools/sandboxing.rs``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from pycodex.core.hook_names import HookToolName
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    ReviewDecision,
    SandboxPermissions,
)

_NetworkT = TypeVar("_NetworkT")


@dataclass(frozen=True)
class PermissionRequestPayload:
    tool_name: HookToolName
    tool_input: dict[str, Any]

    @classmethod
    def bash(cls, command: str, description: str | None = None) -> "PermissionRequestPayload":
        tool_input: dict[str, Any] = {"command": command}
        if description is not None:
            tool_input["description"] = description
        return cls(tool_name=HookToolName.bash(), tool_input=tool_input)


class ApprovalStore:
    """Session approval cache keyed by JSON-serialized approval keys."""

    def __init__(self) -> None:
        self._map: dict[str, ReviewDecision] = {}

    def get(self, key: Any) -> ReviewDecision | None:
        cache_key = _serialize_approval_key(key)
        if cache_key is None:
            return None
        return self._map.get(cache_key)

    def put(self, key: Any, value: ReviewDecision) -> None:
        cache_key = _serialize_approval_key(key)
        if cache_key is not None:
            self._map[cache_key] = value


def with_cached_approval(
    store: ApprovalStore,
    keys: Iterable[Any],
    fetch: Callable[[], ReviewDecision],
) -> ReviewDecision:
    approval_keys = tuple(keys)
    if not approval_keys:
        return fetch()

    approved_for_session = ReviewDecision.approved_for_session()
    if all(store.get(key) == approved_for_session for key in approval_keys):
        return approved_for_session

    decision = fetch()
    if decision == approved_for_session:
        for key in approval_keys:
            store.put(key, approved_for_session)
    return decision


@dataclass(frozen=True)
class ExecApprovalRequirement:
    type: str
    bypass_sandbox: bool = False
    reason: str | None = None
    proposed_execpolicy_amendment: ExecPolicyAmendment | None = None

    @classmethod
    def skip(
        cls,
        *,
        bypass_sandbox: bool = False,
        proposed_execpolicy_amendment: ExecPolicyAmendment | None = None,
    ) -> "ExecApprovalRequirement":
        return cls(
            type="skip",
            bypass_sandbox=bypass_sandbox,
            proposed_execpolicy_amendment=proposed_execpolicy_amendment,
        )

    @classmethod
    def needs_approval(
        cls,
        *,
        reason: str | None = None,
        proposed_execpolicy_amendment: ExecPolicyAmendment | None = None,
    ) -> "ExecApprovalRequirement":
        return cls(
            type="needs_approval",
            reason=reason,
            proposed_execpolicy_amendment=proposed_execpolicy_amendment,
        )

    @classmethod
    def forbidden(cls, reason: str) -> "ExecApprovalRequirement":
        return cls(type="forbidden", reason=reason)

    def proposed_amendment(self) -> ExecPolicyAmendment | None:
        if self.type in {"skip", "needs_approval"}:
            return self.proposed_execpolicy_amendment
        return None


class SandboxOverride(str, Enum):
    NO_OVERRIDE = "no_override"
    BYPASS_SANDBOX_FIRST_ATTEMPT = "bypass_sandbox_first_attempt"


def default_exec_approval_requirement(
    policy: AskForApproval | GranularApprovalConfig,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
) -> ExecApprovalRequirement:
    if isinstance(policy, GranularApprovalConfig):
        needs_approval = file_system_sandbox_policy.kind is FileSystemSandboxKind.RESTRICTED
        sandbox_approval_allowed = policy.allows_sandbox_approval()
    else:
        policy = AskForApproval(policy)
        sandbox_approval_allowed = True
        if policy in {AskForApproval.NEVER, AskForApproval.ON_FAILURE}:
            needs_approval = False
        elif policy is AskForApproval.UNLESS_TRUSTED:
            needs_approval = True
        else:
            needs_approval = file_system_sandbox_policy.kind is FileSystemSandboxKind.RESTRICTED

    if needs_approval and not sandbox_approval_allowed:
        return ExecApprovalRequirement.forbidden("approval policy disallowed sandbox approval prompt")
    if needs_approval:
        return ExecApprovalRequirement.needs_approval()
    return ExecApprovalRequirement.skip()


def sandbox_override_for_first_attempt(
    sandbox_permissions: SandboxPermissions,
    exec_approval_requirement: ExecApprovalRequirement,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
) -> SandboxOverride:
    if exec_approval_requirement.type == "skip" and exec_approval_requirement.bypass_sandbox:
        return SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT

    if file_system_sandbox_policy.has_denied_read_restrictions():
        return SandboxOverride.NO_OVERRIDE

    if SandboxPermissions(sandbox_permissions).requires_escalated_permissions():
        return SandboxOverride.BYPASS_SANDBOX_FIRST_ATTEMPT
    return SandboxOverride.NO_OVERRIDE


def managed_network_for_sandbox_permissions(
    network: _NetworkT | None,
    sandbox_permissions: SandboxPermissions,
) -> _NetworkT | None:
    if SandboxPermissions(sandbox_permissions).requires_escalated_permissions():
        return None
    return network


def _serialize_approval_key(key: Any) -> str | None:
    try:
        return json.dumps(_json_approval_key(key), sort_keys=True, separators=(",", ":"))
    except (TypeError, ValueError):
        return None


def _json_approval_key(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _json_approval_key(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): _json_approval_key(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_json_approval_key(item) for item in value]
    if isinstance(value, set | frozenset):
        return sorted((_json_approval_key(item) for item in value), key=repr)
    return value


__all__ = [
    "ApprovalStore",
    "ExecApprovalRequirement",
    "PermissionRequestPayload",
    "SandboxOverride",
    "default_exec_approval_requirement",
    "managed_network_for_sandbox_permissions",
    "sandbox_override_for_first_attempt",
    "with_cached_approval",
]
