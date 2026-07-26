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






PROMPT_CONFLICT_REASON = "approval required by policy, but AskForApproval is set to Never"
REJECT_SANDBOX_APPROVAL_REASON = "approval required by policy, but AskForApproval::Granular.sandbox_approval is false"
REJECT_RULES_APPROVAL_REASON = "approval required by policy rule, but AskForApproval::Granular.rules is false"


@dataclass(frozen=True)
class SandboxCommand:
    program: str
    args: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    additional_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.program, str) or not self.program:
            raise TypeError("program must be a non-empty string")
        object.__setattr__(self, "args", _string_tuple(self.args, "args"))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "env", _env_dict(self.env))
        if self.additional_permissions is not None and not isinstance(
            self.additional_permissions,
            AdditionalPermissionProfile,
        ):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")


class ToolRuntimeError(Exception):
    """Python exception wrapper for Rust-style ``ToolError`` results."""

    def __init__(self, error: ToolError) -> None:
        if not isinstance(error, ToolError):
            raise TypeError("error must be ToolError")
        self.error = error
        super().__init__(error.message if error.message is not None else str(error.error))






@dataclass(frozen=True)
class InterceptedExecPolicyContext:
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    sandbox_cwd: Path
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    enable_shell_wrapper_parsing: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError("permission_profile must be PermissionProfile")
        if not isinstance(self.file_system_sandbox_policy, FileSystemSandboxPolicy):
            raise TypeError("file_system_sandbox_policy must be FileSystemSandboxPolicy")
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if not isinstance(self.enable_shell_wrapper_parsing, bool):
            raise TypeError("enable_shell_wrapper_parsing must be a bool")


@dataclass(frozen=True)
class InterceptedExecPolicyEvaluation:
    decision: Any
    matched_rules: tuple[Mapping[str, Any], ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "matched_rules", tuple(dict(rule) for rule in self.matched_rules))






























async def _maybe_await_runtime(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value




























































































SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS: tuple[int, int, int] = (0, 1, 2)






















































































async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value






def _path_as_posix_string(path: str | Path) -> str:
    if isinstance(path, Path):
        return path.as_posix()
    return str(path)


def _session_env(session: Any) -> dict[str, str]:
    env = getattr(session, "env", None)
    value = env() if callable(env) else env
    if value is None:
        return {}
    return _env_dict(value)








def build_sandbox_command(
    command: tuple[str, ...] | list[str],
    cwd: str | Path,
    env: Mapping[str, str],
    additional_permissions: AdditionalPermissionProfile | None = None,
) -> SandboxCommand:
    command_tuple = _string_tuple(command, "command")
    if not command_tuple:
        raise ToolRuntimeError(ToolError.rejected("command args are empty"))
    program, *args = command_tuple
    return SandboxCommand(program, tuple(args), Path(cwd), _env_dict(env), additional_permissions)








































def exec_result_from_tool_output(result: ExecToolCallOutput) -> ExecResult:
    if not isinstance(result, ExecToolCallOutput):
        raise TypeError("result must be ExecToolCallOutput")
    return ExecResult(
        exit_code=result.exit_code,
        stdout=result.stdout.text,
        stderr=result.stderr.text,
        output=result.aggregated_output.text,
        duration=result.duration,
        timed_out=result.timed_out,
    )






















def execve_prompt_is_rejected_by_policy(
    approval_policy: AskForApproval | GranularApprovalConfig | str,
    decision_source: DecisionSource,
) -> str | None:
    if not isinstance(decision_source, DecisionSource):
        decision_source = DecisionSource(decision_source)
    if isinstance(approval_policy, GranularApprovalConfig):
        if decision_source is DecisionSource.PREFIX_RULE and not approval_policy.allows_rules_approval():
            return REJECT_RULES_APPROVAL_REASON
        if (
            decision_source is DecisionSource.UNMATCHED_COMMAND_FALLBACK
            and not approval_policy.allows_sandbox_approval()
        ):
            return REJECT_SANDBOX_APPROVAL_REASON
        return None
    if AskForApproval(approval_policy) is AskForApproval.NEVER:
        return PROMPT_CONFLICT_REASON
    return None




def join_program_and_argv(program: str | Path, argv: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    argv_tuple = _string_tuple(argv, "argv")
    return (str(program), *argv_tuple[1:])






def decision_driven_by_policy(
    matched_rules: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    decision: Any,
) -> bool:
    # Rust source: CoreShellActionProvider::decision_driven_by_policy.
    from pycodex.execpolicy import Decision

    target = Decision(str(getattr(decision, "value", decision)))
    return any(
        "heuristicsRuleMatch" not in rule and _runtime_policy_match_decision(rule) is target
        for rule in matched_rules
    )


























def map_exec_result(sandbox: SandboxType, result: ExecResult) -> ExecToolCallOutput:
    if not isinstance(sandbox, SandboxType):
        sandbox = SandboxType(sandbox)
    if not isinstance(result, ExecResult):
        raise TypeError("result must be ExecResult")
    output = ExecToolCallOutput(
        exit_code=result.exit_code,
        stdout=StreamOutput.new(result.stdout),
        stderr=StreamOutput.new(result.stderr),
        aggregated_output=StreamOutput.new(result.output),
        duration=result.duration,
        timed_out=result.timed_out,
    )
    if result.timed_out:
        raise ToolRuntimeError(ToolError.codex({"sandbox": "timeout", "output": output}))
    if is_likely_sandbox_denied(sandbox, output):
        raise ToolRuntimeError(ToolError.codex({"sandbox": "denied", "output": output, "network_policy_decision": None}))
    return output
























def canonicalize_command_for_approval(command: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return tuple(_canonicalize_command_for_approval(_string_tuple(command, "command")))


def flat_tool_name(tool_name: ToolName | str) -> str:
    try:
        tool_name = ToolName.from_value(tool_name)
    except TypeError as err:
        raise TypeError("tool_name must be ToolName or string") from err
    if not tool_name.name:
        raise TypeError("tool_name must be non-empty")
    namespace = tool_name.namespace
    return f"{namespace}{tool_name.name}" if namespace else tool_name.name


def exec_env_for_sandbox_permissions(
    env: Mapping[str, str],
    sandbox_permissions: SandboxPermissions,
    *,
    target_os: str | None = None,
) -> dict[str, str]:
    result = _env_dict(env)
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if sandbox_permissions.requires_escalated_permissions() and PROXY_ACTIVE_ENV_KEY in result:
        for key in PROXY_ENV_KEYS:
            result.pop(key, None)
        if _is_macos_target(target_os):
            git_ssh_command = result.get(PROXY_GIT_SSH_COMMAND_ENV_KEY)
            if git_ssh_command is not None and git_ssh_command.startswith(CODEX_PROXY_GIT_SSH_COMMAND_MARKER):
                result.pop(PROXY_GIT_SSH_COMMAND_ENV_KEY, None)
    return result


def _is_macos_target(target_os: str | None = None) -> bool:
    if target_os is None:
        target_os = sys.platform
    if not isinstance(target_os, str):
        raise TypeError("target_os must be a string or None")
    return target_os.lower() in {"darwin", "macos", "mac", "osx"}






def build_override_exports(explicit_env_overrides: Mapping[str, str]) -> tuple[str, str]:
    keys = sorted(key for key in _env_dict(explicit_env_overrides) if is_valid_shell_variable_name(key))
    return build_override_exports_for_keys("__CODEX_SNAPSHOT_OVERRIDE", tuple(keys))


def build_proxy_env_exports() -> tuple[str, str]:
    keys = sorted({key for key in PROXY_ENV_KEYS if is_valid_shell_variable_name(key)})
    captures, restores = build_override_exports_for_keys("__CODEX_SNAPSHOT_PROXY_OVERRIDE", tuple(keys))
    proxy_active_blocks = (
        f'{captures}\n__CODEX_SNAPSHOT_PROXY_ENV_SET="${{{PROXY_ACTIVE_ENV_KEY}+x}}"',
        (
            f'if [ -n "$__CODEX_SNAPSHOT_PROXY_ENV_SET" ] || [ -n "${{{PROXY_ACTIVE_ENV_KEY}+x}}" ]; then\n'
            f"{restores}\n"
            "fi"
        ),
    )
    git_blocks = build_codex_proxy_git_ssh_command_exports()
    return (
        join_shell_blocks((proxy_active_blocks[0], git_blocks[0])),
        join_shell_blocks((proxy_active_blocks[1], git_blocks[1])),
    )


def build_codex_proxy_git_ssh_command_exports() -> tuple[str, str]:
    return ("", "")


def build_override_exports_for_keys(variable_prefix: str, keys: tuple[str, ...] | list[str]) -> tuple[str, str]:
    if not isinstance(variable_prefix, str) or not variable_prefix:
        raise TypeError("variable_prefix must be a non-empty string")
    key_tuple = _string_tuple(keys, "keys")
    if not key_tuple:
        return ("", "")
    captures = []
    restores = []
    for idx, key in enumerate(key_tuple):
        set_var = f"{variable_prefix}_SET_{idx}"
        value_var = f"{variable_prefix}_{idx}"
        captures.append(f'{set_var}="${{{key}+x}}"\n{value_var}="${{{key}-}}"')
        restores.append(f'if [ -n "${{{set_var}}}" ]; then export {key}="${{{value_var}}}"; else unset {key}; fi')
    return ("\n".join(captures), "\n".join(restores))








def _string_tuple(value: tuple[str, ...] | list[str], field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (tuple, list)):
        raise TypeError(f"{field_name} must be a tuple or list")
    result = tuple(value)
    for item in result:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} items must be strings")
    return result


def _env_dict(env: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(env, Mapping):
        raise TypeError("env must be a mapping")
    result: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError("env keys and values must be strings")
        result[key] = value
    return result




from .apply_patch import (
    ApplyPatchApprovalKey,
    ApplyPatchFileSystemSandboxContext,
    ApplyPatchRequest,
    ApplyPatchRuntime,
    ApplyPatchRuntimeOutput,
    _effective_glob_scan_depth,
    _file_changes_dict,
    _merge_glob_scan_max_depth,
    apply_patch_approval_keys,
    apply_patch_file_system_sandbox_context_for_attempt,
    apply_patch_permission_request_payload,
    apply_patch_sandbox_cwd,
    apply_patch_wants_no_sandbox_approval,
    approval_sandbox_permissions,
    effective_file_system_sandbox_policy,
    effective_network_sandbox_policy,
    effective_permission_profile,
)

from .shell import (
    CandidateCommands,
    CoreShellActionProvider,
    DecisionSource,
    ExecResult,
    ParsedShellCommand,
    PreparedUnifiedExecZshFork,
    ShellApprovalKey,
    ShellCommandExecutorRunContext,
    ShellEscalateAction,
    ShellEscalateClientAction,
    ShellEscalateClientHandshakePlan,
    ShellEscalateClientPlan,
    ShellEscalateClientSocketPair,
    ShellEscalateClientWrapperPlan,
    ShellEscalatePolicyInput,
    ShellEscalateRequest,
    ShellEscalateResponse,
    ShellEscalateServerPlan,
    ShellEscalationDecision,
    ShellEscalationExecution,
    ShellEscalationPolicyPlan,
    ShellEscalationSession,
    ShellLocalExecvPlan,
    ShellPrepareSandboxedExecContext,
    ShellPrepareSandboxedExecParams,
    ShellPreparedExec,
    ShellRequest,
    ShellRuntime,
    ShellRuntimeBackend,
    ShellSandboxTransformRequest,
    ShellSuperExecMessage,
    ShellSuperExecResult,
    ShellSuperExecSpawnPlan,
    ShellSuperExecSubprocessSpec,
    ShellZshForkCancellationPlan,
    ShellZshForkExecParams,
    _bridge_shell_cancellation,
    _ctx_service,
    _forward_external_shell_cancellation,
    _forward_shell_cancellation,
    _intercepted_exec_heuristic_command,
    _intercepted_exec_policy_host_executables,
    _intercepted_exec_policy_rules,
    _is_unix_absolute_path,
    _is_unix_platform,
    _match_intercepted_exec_prefix_rules,
    _parse_shell_super_exec_result,
    _prefix_rule_match_with_resolved_program,
    _render_unix_intercepted_exec_fallback_decision,
    _resolved_host_executable_for_command,
    _runtime_policy_match_decision,
    _runtime_prefix_rule_from_object,
    _runtime_prefix_rule_matched_prefix,
    _runtime_session_shell,
    commands_for_intercepted_exec_policy,
    disable_powershell_profile_for_elevated_windows_sandbox,
    evaluate_intercepted_exec_policy,
    extract_shell_script,
    is_valid_shell_variable_name,
    join_shell_blocks,
    maybe_wrap_shell_lc_with_snapshot,
    prepare_unified_exec_zsh_fork,
    prepare_unified_exec_zsh_fork_from_session,
    shell_approval_keys,
    shell_command_executor_exec_request,
    shell_command_executor_run,
    shell_escalate_action_from_decision,
    shell_escalate_client_action_from_response,
    shell_escalate_client_handshake_payload,
    shell_escalate_client_handshake_plan,
    shell_escalate_client_handshake_plan_send,
    shell_escalate_client_handshake_run,
    shell_escalate_client_plan_from_response,
    shell_escalate_client_plan_run,
    shell_escalate_client_request_exchange,
    shell_escalate_client_request_run,
    shell_escalate_client_response_run,
    shell_escalate_client_send_handshake,
    shell_escalate_client_socket_pair,
    shell_escalate_client_wrapper_plan,
    shell_escalate_client_wrapper_plan_run,
    shell_escalate_client_wrapper_plan_send_handshake,
    shell_escalate_client_wrapper_run,
    shell_escalate_client_wrapper_run_with_socket_pair,
    shell_escalate_decision_for_request,
    shell_escalate_policy_input_from_request,
    shell_escalate_request_from_client,
    shell_escalate_response_from_decision,
    shell_escalate_server_continue_after_response,
    shell_escalate_server_decision_run,
    shell_escalate_server_decision_send_response,
    shell_escalate_server_plan_from_decision,
    shell_escalate_server_plan_send_response,
    shell_escalate_server_request_run,
    shell_escalation_decision_after_review,
    shell_escalation_decision_for_approved_review,
    shell_escalation_decision_for_policy_decision,
    shell_escalation_merge_env_overlay,
    shell_escalation_policy_plan,
    shell_escalation_request_env,
    shell_escalation_session_env,
    shell_escalation_socket_fd_from_env,
    shell_local_execv_plan,
    shell_local_execv_run,
    shell_network_approval_spec,
    shell_permission_request_payload,
    shell_prepare_escalated_exec,
    shell_prepare_escalated_exec_params,
    shell_prepare_sandboxed_exec,
    shell_prepared_exec_effective_arg0,
    shell_prepared_exec_program_and_args,
    shell_request_escalation_execution,
    shell_single_quote,
    shell_socket_build_length_prefixed_payload,
    shell_socket_extract_length_prefixed_payload,
    shell_socket_recv_stream_frame_with_fds,
    shell_socket_recvmsg_with_fds,
    shell_socket_send_stream_frame_with_fds,
    shell_socket_sendmsg_with_fds,
    shell_socket_validate_fds_for_message,
    shell_super_exec_dup2_preexec_fn,
    shell_super_exec_duplicate_fd_for_transfer,
    shell_super_exec_exchange_exit_code,
    shell_super_exec_exit_code_from_result,
    shell_super_exec_fd_pairs,
    shell_super_exec_message_for_escalate_action,
    shell_super_exec_popen_kwargs,
    shell_super_exec_result_from_exit_status,
    shell_super_exec_run_prepared,
    shell_super_exec_run_subprocess,
    shell_super_exec_send_receive_exit_code,
    shell_super_exec_spawn_plan,
    shell_super_exec_stdio_transfer_fds,
    shell_super_exec_subprocess_spec,
    shell_zsh_fork_cancellation_plan,
    shell_zsh_fork_exec_params,
    try_run_zsh_fork,
)

from .unified_exec import (
    UnifiedExecApprovalKey,
    UnifiedExecDirectRunPlan,
    UnifiedExecOptions,
    UnifiedExecRequest,
    UnifiedExecRuntime,
    build_unified_exec_sandbox_command,
    managed_network_for_runtime,
    unified_exec_approval_keys,
    unified_exec_direct_run_plan,
    unified_exec_network_approval_spec,
    unified_exec_options,
    unified_exec_permission_request_payload,
    unified_exec_sandbox_cwd,
)

__all__ = [
    "CODEX_PROXY_GIT_SSH_COMMAND_MARKER",
    "PROXY_ACTIVE_ENV_KEY",
    "PROXY_ENV_KEYS",
    "PROXY_GIT_SSH_COMMAND_ENV_KEY",
    "ApplyPatchApprovalKey",
    "ApplyPatchFileSystemSandboxContext",
    "ApplyPatchRequest",
    "ApplyPatchRuntime",
    "ApplyPatchRuntimeOutput",
    "CandidateCommands",
    "CoreShellActionProvider",
    "DecisionSource",
    "ESCALATE_SOCKET_ENV_VAR",
    "EXEC_WRAPPER_ENV_VAR",
    "ExecResult",
    "GuardianNetworkAccessTrigger",
    "InterceptedExecPolicyContext",
    "InterceptedExecPolicyEvaluation",
    "NetworkApprovalMode",
    "NetworkApprovalSpec",
    "PROMPT_CONFLICT_REASON",
    "ParsedShellCommand",
    "PreparedUnifiedExecZshFork",
    "REJECT_RULES_APPROVAL_REASON",
    "REJECT_SANDBOX_APPROVAL_REASON",
    "SHELL_ESCALATE_HANDSHAKE_MESSAGE",
    "SHELL_SOCKET_MAX_FDS_PER_MESSAGE",
    "SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS",
    "SandboxCommand",
    "ShellApprovalKey",
    "ShellCommandExecutorRunContext",
    "ShellEscalateAction",
    "ShellEscalateClientHandshakePlan",
    "ShellEscalateClientSocketPair",
    "ShellEscalateClientWrapperPlan",
    "ShellEscalateClientAction",
    "ShellEscalateClientPlan",
    "ShellEscalatePolicyInput",
    "ShellEscalateRequest",
    "ShellEscalateResponse",
    "ShellEscalationDecision",
    "ShellEscalationExecution",
    "ShellEscalationPolicyPlan",
    "ShellEscalationSession",
    "ShellEscalateServerPlan",
    "ShellLocalExecvPlan",
    "ShellPrepareSandboxedExecParams",
    "ShellPrepareSandboxedExecContext",
    "ShellSandboxTransformRequest",
    "ShellPreparedExec",
    "ShellSuperExecMessage",
    "ShellSuperExecResult",
    "ShellSuperExecSpawnPlan",
    "ShellSuperExecSubprocessSpec",
    "ShellZshForkCancellationPlan",
    "ShellZshForkExecParams",
    "ShellRequest",
    "ShellRuntime",
    "ShellRuntimeBackend",
    "ToolRuntimeError",
    "UnifiedExecApprovalKey",
    "UnifiedExecDirectRunPlan",
    "UnifiedExecOptions",
    "UnifiedExecRequest",
    "UnifiedExecRuntime",
    "approval_sandbox_permissions",
    "apply_patch_approval_keys",
    "apply_patch_permission_request_payload",
    "apply_patch_sandbox_cwd",
    "apply_patch_wants_no_sandbox_approval",
    "build_codex_proxy_git_ssh_command_exports",
    "build_override_exports",
    "build_override_exports_for_keys",
    "build_proxy_env_exports",
    "build_sandbox_command",
    "build_unified_exec_sandbox_command",
    "canonicalize_command_for_approval",
    "commands_for_intercepted_exec_policy",
    "decision_driven_by_policy",
    "disable_powershell_profile_for_elevated_windows_sandbox",
    "exec_env_for_sandbox_permissions",
    "exec_result_from_tool_output",
    "execve_prompt_is_rejected_by_policy",
    "evaluate_intercepted_exec_policy",
    "extract_shell_script",
    "effective_file_system_sandbox_policy",
    "effective_network_sandbox_policy",
    "effective_permission_profile",
    "apply_patch_file_system_sandbox_context_for_attempt",
    "flat_tool_name",
    "is_valid_shell_variable_name",
    "join_shell_blocks",
    "join_program_and_argv",
    "map_exec_result",
    "maybe_wrap_shell_lc_with_snapshot",
    "managed_network_for_runtime",
    "prepare_unified_exec_zsh_fork",
    "shell_prepared_exec_effective_arg0",
    "shell_prepared_exec_program_and_args",
    "prepare_unified_exec_zsh_fork_from_session",
    "shell_escalate_action_from_decision",
    "shell_escalate_client_action_from_response",
    "shell_escalate_client_handshake_payload",
    "shell_escalate_client_handshake_plan",
    "shell_escalate_client_handshake_plan_send",
    "shell_escalate_client_handshake_run",
    "shell_escalate_client_plan_from_response",
    "shell_escalate_client_plan_run",
    "shell_escalate_client_request_run",
    "shell_escalate_client_request_exchange",
    "shell_escalate_client_response_run",
    "shell_escalate_client_send_handshake",
    "shell_escalate_client_socket_pair",
    "shell_escalate_client_wrapper_plan",
    "shell_escalate_client_wrapper_plan_run",
    "shell_escalate_client_wrapper_plan_send_handshake",
    "shell_escalate_client_wrapper_run",
    "shell_escalate_client_wrapper_run_with_socket_pair",
    "shell_escalate_decision_for_request",
    "shell_escalate_policy_input_from_request",
    "shell_escalate_request_from_client",
    "shell_escalate_response_from_decision",
    "shell_escalate_server_continue_after_response",
    "shell_escalate_server_decision_send_response",
    "shell_escalate_server_decision_run",
    "shell_escalate_server_plan_from_decision",
    "shell_escalate_server_plan_send_response",
    "shell_escalate_server_request_run",
    "shell_escalation_merge_env_overlay",
    "shell_escalation_request_env",
    "shell_escalation_session_env",
    "shell_escalation_socket_fd_from_env",
    "shell_escalation_policy_plan",
    "shell_local_execv_plan",
    "shell_local_execv_run",
    "shell_super_exec_duplicate_fd_for_transfer",
    "shell_super_exec_exchange_exit_code",
    "shell_super_exec_exit_code_from_result",
    "shell_super_exec_fd_pairs",
    "shell_super_exec_message_for_escalate_action",
    "shell_super_exec_result_from_exit_status",
    "shell_super_exec_send_receive_exit_code",
    "shell_super_exec_spawn_plan",
    "shell_super_exec_stdio_transfer_fds",
    "shell_super_exec_subprocess_spec",
    "shell_super_exec_dup2_preexec_fn",
    "shell_super_exec_popen_kwargs",
    "shell_super_exec_run_prepared",
    "shell_super_exec_run_subprocess",
    "shell_request_escalation_execution",
    "shell_zsh_fork_cancellation_plan",
    "shell_zsh_fork_exec_params",
    "try_run_zsh_fork",
    "shell_escalation_decision_after_review",
    "shell_escalation_decision_for_approved_review",
    "shell_escalation_decision_for_policy_decision",
    "shell_single_quote",
    "shell_socket_recvmsg_with_fds",
    "shell_socket_recv_stream_frame_with_fds",
    "shell_socket_send_stream_frame_with_fds",
    "shell_socket_sendmsg_with_fds",
    "shell_socket_validate_fds_for_message",
    "shell_approval_keys",
    "shell_command_executor_exec_request",
    "shell_command_executor_run",
    "shell_network_approval_spec",
    "shell_permission_request_payload",
    "shell_prepare_escalated_exec",
    "shell_prepare_escalated_exec_params",
    "shell_prepare_sandboxed_exec",
    "unified_exec_approval_keys",
    "unified_exec_direct_run_plan",
    "unified_exec_network_approval_spec",
    "unified_exec_options",
    "unified_exec_permission_request_payload",
    "unified_exec_sandbox_cwd",
]
