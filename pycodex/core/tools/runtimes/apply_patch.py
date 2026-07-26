"""Shared runtime helpers ported from ``core/src/tools/runtimes/mod.rs``."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from enum import Enum
from datetime import timedelta
from pathlib import Path
import io
import inspect
import json
import struct
import array
import os
import socket
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping

if not hasattr(socket, "SCM_RIGHTS"):
    socket.SCM_RIGHTS = 1  # type: ignore[attr-defined]
if not hasattr(socket, "CMSG_SPACE"):
    socket.CMSG_SPACE = lambda length: length  # type: ignore[attr-defined]

from pycodex.core.exec import (
    CancellationToken,
    DEFAULT_EXEC_COMMAND_TIMEOUT_MS,
    ExecCapturePolicy,
    ExecExpiration,
    ExecRequest,
    ExecSandboxDenied,
    ExecSandboxSignal,
    ExecSandboxTimeout,
    cancel_when_either,
    is_likely_sandbox_denied,
)
from pycodex.core.command_canonicalization import (
    canonicalize_command_for_approval as _canonicalize_command_for_approval,
)
from pycodex.core.guardian.approval_request import GuardianNetworkAccessTrigger
from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.tools.network_approval import NetworkApprovalMode, NetworkApprovalSpec
from pycodex.core.tools.sandboxing import (
    ApprovalStore,
    ExecApprovalRequirement,
    PermissionRequestPayload,
    SandboxAttempt,
    ToolError,
)
from pycodex.execpolicy import Decision
from pycodex.shell_command import parse_shell_lc_plain_commands, parse_shell_lc_single_command_prefix
from pycodex.utils.path_utils import paths_match_after_normalization
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    CODEX_THREAD_ID_ENV_VAR,
    ExecToolCallOutput,
    FileChange,
    FileSystemAccessMode,
    FileSystemSandboxEntry,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkSandboxPolicy,
    NetworkPolicyRuleAction,
    PermissionProfile,
    ReviewDecision,
    SandboxPermissions,
    StreamOutput,
    ToolName,
    WindowsSandboxLevel,
)

PROXY_ACTIVE_ENV_KEY = "CODEX_PROXY_ACTIVE"
PROXY_ENV_KEYS = (
    PROXY_ACTIVE_ENV_KEY,
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)
PROXY_GIT_SSH_COMMAND_ENV_KEY = "GIT_SSH_COMMAND"
CODEX_PROXY_GIT_SSH_COMMAND_MARKER = "codex-proxy-git-ssh"
ESCALATE_SOCKET_ENV_VAR = "CODEX_ESCALATE_SOCKET"
EXEC_WRAPPER_ENV_VAR = "EXEC_WRAPPER"
SHELL_ESCALATE_HANDSHAKE_MESSAGE = b"\x00"
SHELL_SOCKET_MAX_FDS_PER_MESSAGE = 16
SHELL_SOCKET_LENGTH_PREFIX_SIZE = 4
SHELL_SOCKET_STREAM_MAX_PAYLOAD = 8192



from . import (
    PROXY_ACTIVE_ENV_KEY,
)

@dataclass(frozen=True)
class ApplyPatchApprovalKey:
    environment_id: str
    path: Path

    def __post_init__(self) -> None:
        if not isinstance(self.environment_id, str) or not self.environment_id:
            raise TypeError("environment_id must be a non-empty string")
        if not isinstance(self.path, Path):
            object.__setattr__(self, "path", Path(self.path))

@dataclass(frozen=True)
class ApplyPatchRequest:
    turn_environment: Any
    action: Any
    file_paths: tuple[Path, ...]
    changes: dict[Path, FileChange]
    exec_approval_requirement: ExecApprovalRequirement
    additional_permissions: AdditionalPermissionProfile | None = None
    permissions_preapproved: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "file_paths", tuple(Path(path) for path in self.file_paths))
        object.__setattr__(self, "changes", _file_changes_dict(self.changes))
        if not isinstance(self.exec_approval_requirement, ExecApprovalRequirement):
            raise TypeError("exec_approval_requirement must be ExecApprovalRequirement")
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
        if not isinstance(self.permissions_preapproved, bool):
            raise TypeError("permissions_preapproved must be a bool")

@dataclass(frozen=True)
class ApplyPatchRuntimeOutput:
    exec_output: ExecToolCallOutput
    delta: Any

    def __post_init__(self) -> None:
        if not isinstance(self.exec_output, ExecToolCallOutput):
            raise TypeError("exec_output must be ExecToolCallOutput")

class ApplyPatchRuntime:
    """Approval and execution owner for a verified apply-patch request.

    Rust owner: ``codex-core::tools::runtimes::apply_patch::ApplyPatchRuntime``.
    """

    def __init__(self) -> None:
        self._committed_delta: Any = None

    def committed_delta(self) -> Any:
        return self._committed_delta

    def approval_keys(self, req: ApplyPatchRequest) -> tuple[ApplyPatchApprovalKey, ...]:
        return apply_patch_approval_keys(req)

    def sandbox_preference(self) -> str:
        return "auto"

    def escalate_on_failure(self) -> bool:
        return True

    def exec_approval_requirement(self, req: ApplyPatchRequest) -> ExecApprovalRequirement:
        return req.exec_approval_requirement

    def permission_request_payload(self, req: ApplyPatchRequest) -> PermissionRequestPayload:
        return apply_patch_permission_request_payload(req)

    def sandbox_cwd(self, req: ApplyPatchRequest) -> Path:
        return apply_patch_sandbox_cwd(req)

    async def start_approval_async(self, req: ApplyPatchRequest, ctx: Any) -> ReviewDecision:
        if req.permissions_preapproved and getattr(ctx, "retry_reason", None) is None:
            return ReviewDecision.approved()

        keys = self.approval_keys(req)
        services = getattr(ctx.session, "services", None)
        store = getattr(services, "approval_store", None)
        if store is None:
            store = ApprovalStore()
            if services is not None:
                setattr(services, "approval_store", store)
        approved_for_session = ReviewDecision.approved_for_session()
        if keys and all(store.get(key) == approved_for_session for key in keys):
            return approved_for_session

        prompt = getattr(ctx.session, "request_patch_approval", None)
        if not callable(prompt):
            return ReviewDecision.abort()
        decision = prompt(
            ctx.turn,
            str(ctx.call_id),
            req.changes,
            getattr(ctx, "retry_reason", None),
            None,
        )
        if inspect.isawaitable(decision):
            decision = await decision
        decision = ReviewDecision.from_mapping(decision)
        if decision == approved_for_session:
            for key in keys:
                store.put(key, approved_for_session)
        return decision

    async def run(self, req: ApplyPatchRequest, _attempt: SandboxAttempt, _ctx: Any) -> ApplyPatchRuntimeOutput:
        from pycodex.apply_patch import apply_patch_action_to_disk

        started_at = time.monotonic()
        output = apply_patch_action_to_disk(req.action)
        self._committed_delta = req.changes
        exec_output = ExecToolCallOutput(
            exit_code=0,
            stdout=StreamOutput.new(output),
            aggregated_output=StreamOutput.new(output),
            duration=timedelta(seconds=time.monotonic() - started_at),
        )
        return ApplyPatchRuntimeOutput(exec_output, self._committed_delta)

@dataclass(frozen=True)
class ApplyPatchFileSystemSandboxContext:
    permissions: PermissionProfile
    cwd: Path | None
    windows_sandbox_level: WindowsSandboxLevel
    windows_sandbox_private_desktop: bool
    use_legacy_landlock: bool

    def __post_init__(self) -> None:
        if not isinstance(self.permissions, PermissionProfile):
            raise TypeError("permissions must be PermissionProfile")
        if self.cwd is not None and not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(self, "windows_sandbox_level", WindowsSandboxLevel.parse(str(self.windows_sandbox_level)))
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError("windows_sandbox_private_desktop must be a bool")
        if not isinstance(self.use_legacy_landlock, bool):
            raise TypeError("use_legacy_landlock must be a bool")

def apply_patch_approval_keys(req: ApplyPatchRequest) -> tuple[ApplyPatchApprovalKey, ...]:
    if not isinstance(req, ApplyPatchRequest):
        raise TypeError("req must be ApplyPatchRequest")
    environment_id = getattr(req.turn_environment, "environment_id", None)
    if not isinstance(environment_id, str) or not environment_id:
        raise TypeError("turn_environment must expose a non-empty environment_id")
    return tuple(ApplyPatchApprovalKey(environment_id, path) for path in req.file_paths)

def apply_patch_permission_request_payload(req: ApplyPatchRequest) -> PermissionRequestPayload:
    if not isinstance(req, ApplyPatchRequest):
        raise TypeError("req must be ApplyPatchRequest")
    patch = getattr(req.action, "patch", None)
    if not isinstance(patch, str):
        raise TypeError("action must expose patch string")
    return PermissionRequestPayload(HookToolName.apply_patch(), {"command": patch})

def apply_patch_wants_no_sandbox_approval(policy: AskForApproval | GranularApprovalConfig | str) -> bool:
    if isinstance(policy, GranularApprovalConfig):
        return policy.allows_sandbox_approval()
    return AskForApproval(policy) is not AskForApproval.NEVER

def apply_patch_sandbox_cwd(req: ApplyPatchRequest) -> Path:
    if not isinstance(req, ApplyPatchRequest):
        raise TypeError("req must be ApplyPatchRequest")
    cwd = getattr(req.action, "cwd", None)
    if not isinstance(cwd, Path):
        raise TypeError("action must expose cwd Path")
    return cwd

def apply_patch_file_system_sandbox_context_for_attempt(
    req: ApplyPatchRequest,
    attempt: SandboxAttempt,
) -> ApplyPatchFileSystemSandboxContext | None:
    if not isinstance(req, ApplyPatchRequest):
        raise TypeError("req must be ApplyPatchRequest")
    if not isinstance(attempt, SandboxAttempt):
        raise TypeError("attempt must be SandboxAttempt")
    if attempt.sandbox == SandboxType.NONE or str(attempt.sandbox) == SandboxType.NONE.value:
        return None
    return ApplyPatchFileSystemSandboxContext(
        permissions=effective_permission_profile(attempt.permissions, req.additional_permissions),
        cwd=attempt.sandbox_cwd,
        windows_sandbox_level=attempt.windows_sandbox_level,
        windows_sandbox_private_desktop=attempt.windows_sandbox_private_desktop,
        use_legacy_landlock=attempt.use_legacy_landlock,
    )

def effective_permission_profile(
    permissions: PermissionProfile,
    additional_permissions: AdditionalPermissionProfile | None,
) -> PermissionProfile:
    if not isinstance(permissions, PermissionProfile):
        raise TypeError("permissions must be PermissionProfile")
    if additional_permissions is None:
        return permissions
    if not isinstance(additional_permissions, AdditionalPermissionProfile):
        raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
    file_system_policy = effective_file_system_sandbox_policy(
        permissions.file_system_sandbox_policy(),
        additional_permissions,
    )
    network_policy = effective_network_sandbox_policy(
        permissions.network_sandbox_policy(),
        additional_permissions,
    )
    return PermissionProfile.from_runtime_permissions(file_system_policy, network_policy)

def effective_file_system_sandbox_policy(
    file_system_policy: FileSystemSandboxPolicy,
    additional_permissions: AdditionalPermissionProfile | None,
) -> FileSystemSandboxPolicy:
    if not isinstance(file_system_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_policy must be FileSystemSandboxPolicy")
    if additional_permissions is None or additional_permissions.file_system is None:
        return file_system_policy
    if file_system_policy.kind is not FileSystemSandboxKind.RESTRICTED:
        return file_system_policy
    entries = list(file_system_policy.entries)
    for entry in additional_permissions.file_system.entries:
        if entry not in entries:
            entries.append(entry)
    max_depth = _merge_glob_scan_max_depth(
        file_system_policy.entries,
        file_system_policy.glob_scan_max_depth,
        additional_permissions.file_system.entries,
        additional_permissions.file_system.glob_scan_max_depth,
    )
    return FileSystemSandboxPolicy(file_system_policy.kind, tuple(entries), max_depth)

def _merge_glob_scan_max_depth(
    left_entries: tuple[FileSystemSandboxEntry, ...],
    left_depth: int | None,
    right_entries: tuple[FileSystemSandboxEntry, ...],
    right_depth: int | None,
) -> int | None:
    left_effective = _effective_glob_scan_depth(left_entries, left_depth)
    right_effective = _effective_glob_scan_depth(right_entries, right_depth)
    if left_effective == "unbounded" or right_effective == "unbounded":
        return None
    depths = [depth for depth in (left_effective, right_effective) if isinstance(depth, int)]
    if depths:
        return max(depths)
    return None

def _effective_glob_scan_depth(
    entries: tuple[FileSystemSandboxEntry, ...],
    depth: int | None,
) -> int | str | None:
    has_deny_glob = any(
        entry.access is FileSystemAccessMode.DENY and entry.path.type == "glob_pattern"
        for entry in entries
    )
    if not has_deny_glob:
        return None
    return depth if depth is not None else "unbounded"

def effective_network_sandbox_policy(
    network_policy: NetworkSandboxPolicy,
    additional_permissions: AdditionalPermissionProfile | None,
) -> NetworkSandboxPolicy:
    if not isinstance(network_policy, NetworkSandboxPolicy):
        network_policy = NetworkSandboxPolicy(network_policy)
    if additional_permissions is None or additional_permissions.network is None:
        return network_policy
    enabled = additional_permissions.network.enabled
    if enabled is True:
        return NetworkSandboxPolicy.ENABLED
    if enabled is False:
        return NetworkSandboxPolicy.RESTRICTED
    return network_policy

def approval_sandbox_permissions(
    sandbox_permissions: SandboxPermissions,
    additional_permissions_preapproved: bool,
) -> SandboxPermissions:
    if not isinstance(additional_permissions_preapproved, bool):
        raise TypeError("additional_permissions_preapproved must be a bool")
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if additional_permissions_preapproved and sandbox_permissions is SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS:
        return SandboxPermissions.USE_DEFAULT
    return sandbox_permissions

def _file_changes_dict(changes: Mapping[str | Path, FileChange]) -> dict[Path, FileChange]:
    if not isinstance(changes, Mapping):
        raise TypeError("changes must be a mapping")
    result: dict[Path, FileChange] = {}
    for path, change in changes.items():
        if not isinstance(path, (str, Path)):
            raise TypeError("changes keys must be strings or Path")
        if not isinstance(change, FileChange):
            raise TypeError("changes values must be FileChange")
        result[Path(path)] = change
    return result

