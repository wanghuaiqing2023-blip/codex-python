"""Tool approval and sandboxing primitives ported from Codex core.

This module mirrors the policy-independent helpers in
``codex/codex-rs/core/src/tools/sandboxing.rs``.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, fields, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeVar

from pycodex.core.tools.hook_names import HookToolName
from pycodex.protocol import (
    AskForApproval,
    ExecPolicyAmendment,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    ReviewDecision,
    SandboxPermissions,
    ToolName,
    WindowsSandboxLevel,
)
from pycodex.core.tools.network_approval import CancellationToken

_NetworkT = TypeVar("_NetworkT")


@dataclass(frozen=True)
class PermissionRequestPayload:
    tool_name: HookToolName
    tool_input: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, HookToolName):
            raise TypeError("tool_name must be HookToolName")
        if not isinstance(self.tool_input, dict):
            raise TypeError("tool_input must be a dict")

    @classmethod
    def bash(cls, command: str, description: str | None = None) -> "PermissionRequestPayload":
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        if description is not None and not isinstance(description, str):
            raise TypeError("description must be a string or None")
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


@dataclass(frozen=True)
class ApprovalCtx:
    session: Any
    turn: Any
    call_id: str
    guardian_review_id: str | None = None
    retry_reason: str | None = None
    network_approval_context: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if self.guardian_review_id is not None and not isinstance(self.guardian_review_id, str):
            raise TypeError("guardian_review_id must be a string or None")
        if self.retry_reason is not None and not isinstance(self.retry_reason, str):
            raise TypeError("retry_reason must be a string or None")


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


class Approvable(ABC):
    @abstractmethod
    def approval_keys(self, req: Any) -> list[Any]:
        raise NotImplementedError

    def sandbox_permissions(self, req: Any) -> SandboxPermissions:
        return SandboxPermissions.USE_DEFAULT

    def should_bypass_approval(self, policy: AskForApproval | str, already_approved: bool) -> bool:
        return should_bypass_approval(policy, already_approved)

    def exec_approval_requirement(self, req: Any) -> ExecApprovalRequirement | None:
        return None

    def permission_request_payload(self, req: Any) -> PermissionRequestPayload | None:
        return None

    def wants_no_sandbox_approval(self, policy: AskForApproval | GranularApprovalConfig | str) -> bool:
        return wants_no_sandbox_approval(policy)

    @abstractmethod
    async def start_approval_async(self, req: Any, ctx: ApprovalCtx) -> ReviewDecision:
        raise NotImplementedError


class Sandboxable(ABC):
    @abstractmethod
    def sandbox_preference(self) -> Any:
        raise NotImplementedError

    def escalate_on_failure(self) -> bool:
        return True


class ToolRuntime(Approvable, Sandboxable):
    def network_approval_spec(self, req: Any, ctx: "ToolCtx") -> Any:
        return None

    def sandbox_cwd(self, req: Any) -> Path | None:
        return None

    @abstractmethod
    async def run(self, req: Any, attempt: "SandboxAttempt", ctx: "ToolCtx") -> Any:
        raise NotImplementedError


@dataclass(frozen=True)
class ExecApprovalRequirement:
    type: str
    bypass_sandbox: bool = False
    reason: str | None = None
    proposed_execpolicy_amendment: ExecPolicyAmendment | None = None

    def __post_init__(self) -> None:
        if self.type == "skip":
            if not isinstance(self.bypass_sandbox, bool):
                raise TypeError("bypass_sandbox must be a bool")
            if self.reason is not None:
                raise ValueError("skip requirement must not include reason")
        elif self.type == "needs_approval":
            if self.bypass_sandbox:
                raise ValueError("needs_approval requirement must not bypass sandbox")
            if self.reason is not None and not isinstance(self.reason, str):
                raise TypeError("reason must be a string or None")
        elif self.type == "forbidden":
            if self.bypass_sandbox:
                raise ValueError("forbidden requirement must not bypass sandbox")
            if not isinstance(self.reason, str):
                raise TypeError("forbidden requirement requires reason")
        else:
            raise ValueError(f"unknown exec approval requirement type: {self.type}")
        if (
            self.proposed_execpolicy_amendment is not None
            and not isinstance(self.proposed_execpolicy_amendment, ExecPolicyAmendment)
        ):
            raise TypeError("proposed_execpolicy_amendment must be ExecPolicyAmendment or None")

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

    def proposed_execpolicy_amendment_ref(self) -> ExecPolicyAmendment | None:
        return self.proposed_amendment()


class SandboxOverride(str, Enum):
    NO_OVERRIDE = "no_override"
    BYPASS_SANDBOX_FIRST_ATTEMPT = "bypass_sandbox_first_attempt"


@dataclass(frozen=True)
class ToolCtx:
    session: Any
    turn: Any
    call_id: str
    tool_name: ToolName

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.tool_name, ToolName):
            raise TypeError("tool_name must be ToolName")


@dataclass(frozen=True)
class ToolError:
    type: str
    message: str | None = None
    error: Any = None

    @classmethod
    def rejected(cls, message: str) -> "ToolError":
        return cls("rejected", message=message)

    @classmethod
    def codex(cls, error: Any) -> "ToolError":
        return cls("codex", error=error)

    def __post_init__(self) -> None:
        if self.type == "rejected":
            if not isinstance(self.message, str):
                raise TypeError("rejected tool error requires message")
            if self.error is not None:
                raise ValueError("rejected tool error must not include error")
            return
        if self.type == "codex":
            if self.message is not None:
                raise ValueError("codex tool error must not include message")
            return
        raise ValueError(f"unknown tool error type: {self.type}")


@dataclass(frozen=True)
class SandboxAttempt:
    sandbox: Any
    permissions: PermissionProfile
    enforce_managed_network: bool
    manager: Any
    sandbox_cwd: Path
    codex_linux_sandbox_exe: Path | None = None
    use_legacy_landlock: bool = False
    windows_sandbox_level: WindowsSandboxLevel = WindowsSandboxLevel.DISABLED
    windows_sandbox_private_desktop: bool = False
    network_denial_cancellation_token: CancellationToken | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.permissions, PermissionProfile):
            raise TypeError("permissions must be PermissionProfile")
        if not isinstance(self.enforce_managed_network, bool):
            raise TypeError("enforce_managed_network must be a bool")
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if self.codex_linux_sandbox_exe is not None and not isinstance(self.codex_linux_sandbox_exe, Path):
            object.__setattr__(self, "codex_linux_sandbox_exe", Path(self.codex_linux_sandbox_exe))
        if not isinstance(self.use_legacy_landlock, bool):
            raise TypeError("use_legacy_landlock must be a bool")
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(self, "windows_sandbox_level", WindowsSandboxLevel.parse(str(self.windows_sandbox_level)))
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError("windows_sandbox_private_desktop must be a bool")
        if (
            self.network_denial_cancellation_token is not None
            and not isinstance(self.network_denial_cancellation_token, CancellationToken)
        ):
            raise TypeError("network_denial_cancellation_token must be CancellationToken or None")

    def env_for(self, *_args: Any, **_kwargs: Any) -> Any:
        return self.manager.transform(*_args, **_kwargs)


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


def should_bypass_approval(policy: AskForApproval | str, already_approved: bool) -> bool:
    if not isinstance(already_approved, bool):
        raise TypeError("already_approved must be a bool")
    if already_approved:
        return True
    return AskForApproval(policy) is AskForApproval.NEVER


def wants_no_sandbox_approval(policy: AskForApproval | GranularApprovalConfig | str) -> bool:
    if isinstance(policy, GranularApprovalConfig):
        return policy.sandbox_approval
    policy = AskForApproval(policy)
    if policy in {AskForApproval.ON_FAILURE, AskForApproval.UNLESS_TRUSTED}:
        return True
    if policy in {AskForApproval.NEVER, AskForApproval.ON_REQUEST}:
        return False
    return False


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
    "Approvable",
    "ApprovalCtx",
    "ApprovalStore",
    "ExecApprovalRequirement",
    "PermissionRequestPayload",
    "SandboxOverride",
    "SandboxAttempt",
    "Sandboxable",
    "ToolCtx",
    "ToolError",
    "ToolRuntime",
    "default_exec_approval_requirement",
    "managed_network_for_sandbox_permissions",
    "sandbox_override_for_first_attempt",
    "should_bypass_approval",
    "wants_no_sandbox_approval",
    "with_cached_approval",
]
