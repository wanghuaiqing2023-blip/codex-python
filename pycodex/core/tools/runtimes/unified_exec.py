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
    SandboxCommand,
    ToolRuntimeError,
    _env_dict,
    _string_tuple,
    build_sandbox_command,
    canonicalize_command_for_approval,
    exec_env_for_sandbox_permissions,
    flat_tool_name,
)

from .apply_patch import (
    approval_sandbox_permissions,
    effective_permission_profile,
)

from . import (
    PROXY_ACTIVE_ENV_KEY,
)

@dataclass(frozen=True)
class UnifiedExecRequest:
    command: tuple[str, ...]
    shell_type: ShellType
    hook_command: str
    process_id: int
    cwd: Path
    sandbox_cwd: Path
    environment: Any
    env: dict[str, str]
    exec_server_env_config: Any | None
    explicit_env_overrides: dict[str, str]
    network: Any | None
    tty: bool
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None
    justification: str | None
    exec_approval_requirement: ExecApprovalRequirement
    additional_permissions_preapproved: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if not isinstance(self.shell_type, ShellType):
            object.__setattr__(self, "shell_type", ShellType(str(self.shell_type)))
        if not isinstance(self.hook_command, str):
            raise TypeError("hook_command must be a string")
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an int")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        object.__setattr__(self, "env", _env_dict(self.env))
        object.__setattr__(self, "explicit_env_overrides", _env_dict(self.explicit_env_overrides))
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")
        if not isinstance(self.exec_approval_requirement, ExecApprovalRequirement):
            raise TypeError("exec_approval_requirement must be ExecApprovalRequirement")
        if not isinstance(self.additional_permissions_preapproved, bool):
            raise TypeError("additional_permissions_preapproved must be a bool")

    def approval_sandbox_permissions(self) -> SandboxPermissions:
        return approval_sandbox_permissions(
            self.sandbox_permissions,
            self.additional_permissions_preapproved,
        )

@dataclass(frozen=True)
class UnifiedExecApprovalKey:
    command: tuple[str, ...]
    cwd: Path
    tty: bool
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")

@dataclass(frozen=True)
class UnifiedExecOptions:
    expiration: ExecExpiration
    capture_policy: ExecCapturePolicy = ExecCapturePolicy.SHELL_TOOL

    def __post_init__(self) -> None:
        if not isinstance(self.expiration, ExecExpiration):
            raise TypeError("expiration must be ExecExpiration")
        if not isinstance(self.capture_policy, ExecCapturePolicy):
            object.__setattr__(self, "capture_policy", ExecCapturePolicy(self.capture_policy))

class UnifiedExecRuntime:
    """Approval and sandbox owner for a unified-exec launch.

    Rust owner: ``codex-core::tools::runtimes::unified_exec::UnifiedExecRuntime``.
    The Python process manager combines Rust's open-process and first snapshot
    operations, so ``manager_request`` is retained as backend-only state while
    all approval semantics are derived from the Rust-shaped ``UnifiedExecRequest``.
    """

    def __init__(self, manager: Any, manager_request: Any) -> None:
        self.manager = manager
        self.manager_request = manager_request

    def approval_keys(self, req: UnifiedExecRequest) -> tuple[UnifiedExecApprovalKey, ...]:
        return unified_exec_approval_keys(req)

    def sandbox_preference(self) -> str:
        return "auto"

    def escalate_on_failure(self) -> bool:
        return True

    def exec_approval_requirement(self, req: UnifiedExecRequest) -> ExecApprovalRequirement:
        return req.exec_approval_requirement

    def permission_request_payload(self, req: UnifiedExecRequest) -> PermissionRequestPayload:
        return unified_exec_permission_request_payload(req)

    def sandbox_permissions(self, req: UnifiedExecRequest) -> SandboxPermissions:
        return req.sandbox_permissions

    def sandbox_cwd(self, req: UnifiedExecRequest) -> Path:
        return req.sandbox_cwd

    def network_approval_spec(self, req: UnifiedExecRequest, ctx: Any) -> NetworkApprovalSpec | None:
        return unified_exec_network_approval_spec(
            req,
            call_id=str(getattr(ctx, "call_id")),
            tool_name=getattr(ctx, "tool_name"),
        )

    async def start_approval_async(self, req: UnifiedExecRequest, ctx: Any) -> ReviewDecision:
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

        retry_reason = getattr(ctx, "retry_reason", None)
        reason = retry_reason or req.justification
        guardian_review_id = getattr(ctx, "guardian_review_id", None)
        if guardian_review_id is not None:
            reviewer = getattr(ctx.session, "review_approval_request", None)
            if callable(reviewer):
                decision = reviewer(
                    ctx.turn,
                    guardian_review_id,
                    {
                        "type": "exec_command",
                        "id": str(ctx.call_id),
                        "command": req.command,
                        "cwd": req.cwd,
                        "sandbox_permissions": req.sandbox_permissions,
                        "additional_permissions": req.additional_permissions,
                        "justification": req.justification,
                        "tty": req.tty,
                    },
                    retry_reason,
                )
                if inspect.isawaitable(decision):
                    decision = await decision
                return ReviewDecision.from_mapping(decision)

        prompt = getattr(ctx.session, "request_command_approval", None)
        if not callable(prompt):
            return ReviewDecision.abort()
        decision = prompt(
            ctx.turn,
            str(ctx.call_id),
            None,
            req.command,
            req.cwd,
            reason,
            getattr(ctx, "network_approval_context", None),
            req.exec_approval_requirement.proposed_execpolicy_amendment,
            req.additional_permissions,
            None,
        )
        if inspect.isawaitable(decision):
            decision = await decision
        decision = ReviewDecision.from_mapping(decision)
        if decision == approved_for_session:
            for key in keys:
                store.put(key, approved_for_session)
        return decision

    async def run(self, req: UnifiedExecRequest, attempt: SandboxAttempt, _ctx: Any) -> Any:
        # Rust owner: unified_exec opens the process with the selected sandbox
        # attempt.  Preserve that dynamic anchor for the stdlib manager rather
        # than letting it default to an unrestricted subprocess.
        effective_attempt = replace(
            attempt,
            permissions=effective_permission_profile(attempt.permissions, req.additional_permissions),
        )
        object.__setattr__(self.manager_request, "_sandbox_attempt", effective_attempt)
        result = self.manager.exec_command(self.manager_request)
        if inspect.isawaitable(result):
            result = await result
        return result

@dataclass(frozen=True)
class UnifiedExecDirectRunPlan:
    process_id: int
    sandbox_command: SandboxCommand
    options: UnifiedExecOptions
    tty: bool
    environment: Any
    exec_server_env_config: Any | None
    managed_network: Any | None
    spawn_lifecycle: str = "noop"

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an int")
        if not isinstance(self.sandbox_command, SandboxCommand):
            raise TypeError("sandbox_command must be SandboxCommand")
        if not isinstance(self.options, UnifiedExecOptions):
            raise TypeError("options must be UnifiedExecOptions")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if self.spawn_lifecycle != "noop":
            raise ValueError("spawn_lifecycle must be noop")

def unified_exec_approval_keys(req: UnifiedExecRequest) -> tuple[UnifiedExecApprovalKey, ...]:
    if not isinstance(req, UnifiedExecRequest):
        raise TypeError("req must be UnifiedExecRequest")
    return (UnifiedExecApprovalKey(canonicalize_command_for_approval(req.command), req.cwd, req.tty, req.sandbox_permissions, req.additional_permissions),)

def unified_exec_permission_request_payload(req: UnifiedExecRequest) -> PermissionRequestPayload:
    if not isinstance(req, UnifiedExecRequest):
        raise TypeError("req must be UnifiedExecRequest")
    return PermissionRequestPayload.bash(req.hook_command, req.justification)

def unified_exec_sandbox_cwd(req: UnifiedExecRequest) -> Path:
    if not isinstance(req, UnifiedExecRequest):
        raise TypeError("req must be UnifiedExecRequest")
    return req.sandbox_cwd

def unified_exec_options(
    network_denial_cancellation_token: CancellationToken | None = None,
) -> UnifiedExecOptions:
    if network_denial_cancellation_token is not None and not isinstance(network_denial_cancellation_token, CancellationToken):
        raise TypeError("network_denial_cancellation_token must be CancellationToken or None")
    expiration = ExecExpiration.default_timeout()
    if network_denial_cancellation_token is not None:
        expiration = expiration.with_cancellation(network_denial_cancellation_token)
        if expiration.timeout_ms() != DEFAULT_EXEC_COMMAND_TIMEOUT_MS:
            raise AssertionError("default timeout changed while attaching cancellation")
    return UnifiedExecOptions(expiration, ExecCapturePolicy.SHELL_TOOL)

def build_unified_exec_sandbox_command(
    command: tuple[str, ...] | list[str],
    cwd: str | Path,
    env: Mapping[str, str],
    additional_permissions: AdditionalPermissionProfile | None = None,
) -> SandboxCommand:
    try:
        return build_sandbox_command(command, cwd, env, additional_permissions)
    except ToolRuntimeError as exc:
        if exc.error.type == "rejected":
            raise ToolRuntimeError(ToolError.rejected("missing command line for PTY")) from exc
        raise

def unified_exec_direct_run_plan(
    req: UnifiedExecRequest,
    *,
    network_denial_cancellation_token: CancellationToken | None = None,
) -> UnifiedExecDirectRunPlan:
    # Rust source: codex-rs/core/src/tools/runtimes/unified_exec.rs
    # Behavior anchor: UnifiedExecRuntime::run direct fallback builds the
    # sandbox command, attaches unified_exec_options, copies
    # exec_server_env_config, and opens the process with NoopSpawnLifecycle.
    if not isinstance(req, UnifiedExecRequest):
        raise TypeError("req must be UnifiedExecRequest")
    env = exec_env_for_sandbox_permissions(req.env, req.sandbox_permissions)
    managed_network = managed_network_for_runtime(req.network, req.sandbox_permissions)
    apply_to_env = getattr(managed_network, "apply_to_env", None)
    if callable(apply_to_env):
        apply_to_env(env)
    sandbox_command = build_unified_exec_sandbox_command(
        req.command,
        req.cwd,
        env,
        req.additional_permissions,
    )
    return UnifiedExecDirectRunPlan(
        process_id=req.process_id,
        sandbox_command=sandbox_command,
        options=unified_exec_options(network_denial_cancellation_token),
        tty=req.tty,
        environment=req.environment,
        exec_server_env_config=req.exec_server_env_config,
        managed_network=managed_network,
    )

def unified_exec_network_approval_spec(req: UnifiedExecRequest, *, call_id: str, tool_name: ToolName | str) -> NetworkApprovalSpec | None:
    if not isinstance(req, UnifiedExecRequest):
        raise TypeError("req must be UnifiedExecRequest")
    network = managed_network_for_runtime(req.network, req.sandbox_permissions)
    if network is None:
        return None
    return NetworkApprovalSpec(
        network,
        NetworkApprovalMode.DEFERRED,
        GuardianNetworkAccessTrigger(call_id, flat_tool_name(tool_name), req.command, req.cwd, req.sandbox_permissions, req.additional_permissions, req.justification, req.tty),
        req.hook_command,
    )

def managed_network_for_runtime(network: Any | None, sandbox_permissions: SandboxPermissions) -> Any | None:
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if sandbox_permissions.requires_escalated_permissions():
        return None
    return network

