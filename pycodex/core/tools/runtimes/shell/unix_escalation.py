"""Port of the Rust `unix_escalation` child module."""
from __future__ import annotations
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
from pycodex.core.exec import CancellationToken, DEFAULT_EXEC_COMMAND_TIMEOUT_MS, ExecCapturePolicy, ExecExpiration, ExecRequest, ExecSandboxDenied, ExecSandboxSignal, ExecSandboxTimeout, cancel_when_either, is_likely_sandbox_denied
from pycodex.core.command_canonicalization import canonicalize_command_for_approval as _canonicalize_command_for_approval
from pycodex.core.guardian.approval_request import GuardianNetworkAccessTrigger
from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.tools.network_approval import NetworkApprovalMode, NetworkApprovalSpec
from pycodex.core.tools.sandboxing import ApprovalStore, ExecApprovalRequirement, PermissionRequestPayload, SandboxAttempt, ToolError
from pycodex.execpolicy import Decision
from pycodex.shell_command import parse_shell_lc_plain_commands, parse_shell_lc_single_command_prefix
from pycodex.utils.path_utils import paths_match_after_normalization
from pycodex.protocol import AdditionalPermissionProfile, AskForApproval, CODEX_THREAD_ID_ENV_VAR, ExecToolCallOutput, FileChange, FileSystemAccessMode, FileSystemSandboxEntry, FileSystemSandboxKind, FileSystemSandboxPolicy, GranularApprovalConfig, NetworkSandboxPolicy, NetworkPolicyRuleAction, PermissionProfile, ReviewDecision, SandboxPermissions, StreamOutput, ToolName, WindowsSandboxLevel
from .. import InterceptedExecPolicyContext, InterceptedExecPolicyEvaluation, SandboxCommand, ToolRuntimeError, _env_dict, _maybe_await, _maybe_await_runtime, _path_as_posix_string, _session_env, _string_tuple, build_override_exports, build_proxy_env_exports, canonicalize_command_for_approval, decision_driven_by_policy, exec_env_for_sandbox_permissions, exec_result_from_tool_output, execve_prompt_is_rejected_by_policy, flat_tool_name, join_program_and_argv, map_exec_result
from ..apply_patch import approval_sandbox_permissions, effective_permission_profile
from ..unified_exec import UnifiedExecRequest, managed_network_for_runtime
from .. import ESCALATE_SOCKET_ENV_VAR, EXEC_WRAPPER_ENV_VAR, PROXY_ACTIVE_ENV_KEY, SHELL_ESCALATE_HANDSHAKE_MESSAGE, SHELL_SOCKET_LENGTH_PREFIX_SIZE, SHELL_SOCKET_MAX_FDS_PER_MESSAGE, SHELL_SOCKET_STREAM_MAX_PAYLOAD, SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS
from . import ShellCommandExecutorRunContext, ShellEscalationDecision, ShellEscalationExecution, ShellEscalationPolicyPlan, ShellEscalationSession, ShellRequest, _ctx_service, _intercepted_exec_heuristic_command, _intercepted_exec_policy_host_executables, _intercepted_exec_policy_rules, _match_intercepted_exec_prefix_rules, _prefix_rule_match_with_resolved_program, _render_unix_intercepted_exec_fallback_decision, _resolved_host_executable_for_command, _runtime_policy_match_decision, prepare_unified_exec_zsh_fork_from_session, shell_command_executor_run, shell_escalation_decision_after_review, shell_escalation_policy_plan, shell_escalation_session_env, shell_zsh_fork_cancellation_plan, shell_zsh_fork_exec_params

class DecisionSource(str, Enum):
    PREFIX_RULE = 'prefix_rule'
    UNMATCHED_COMMAND_FALLBACK = 'unmatched_command_fallback'

@dataclass(frozen=True)
class ParsedShellCommand:
    program: str
    script: str
    login: bool

    def __post_init__(self) -> None:
        if not isinstance(self.program, str) or not self.program:
            raise TypeError('program must be a non-empty string')
        if not isinstance(self.script, str):
            raise TypeError('script must be a string')
        if not isinstance(self.login, bool):
            raise TypeError('login must be a bool')

@dataclass(frozen=True)
class CandidateCommands:
    commands: tuple[tuple[str, ...], ...]
    used_complex_parsing: bool = False

    def __post_init__(self) -> None:
        commands = tuple((tuple(command) for command in self.commands))
        if not all((all((isinstance(part, str) for part in command)) for command in commands)):
            raise TypeError('commands must contain strings')
        object.__setattr__(self, 'commands', commands)
        if not isinstance(self.used_complex_parsing, bool):
            raise TypeError('used_complex_parsing must be a bool')

@dataclass
class CoreShellActionProvider:
    """Python facade for Rust ``CoreShellActionProvider``.

    It owns policy evaluation plus approval prompting. Concrete guardian,
    hook, and user-prompt implementations are delegated to the session/turn
    runtime objects when present.
    """
    policy: Any
    session: Any
    turn: Any
    call_id: str
    tool_name: Any
    approval_policy: AskForApproval | GranularApprovalConfig
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    sandbox_policy_cwd: Path
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    approval_sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    prompt_permissions: AdditionalPermissionProfile | None = None

    async def determine_action(self, program: str | Path, argv: tuple[str, ...] | list[str], workdir: str | Path) -> ShellEscalationDecision:
        evaluation = evaluate_intercepted_exec_policy(self.policy, str(program), tuple(argv), InterceptedExecPolicyContext(approval_policy=self.approval_policy, permission_profile=self.permission_profile, file_system_sandbox_policy=self.file_system_sandbox_policy, sandbox_cwd=Path(self.sandbox_policy_cwd), sandbox_permissions=self.approval_sandbox_permissions, enable_shell_wrapper_parsing=False))
        plan = shell_escalation_policy_plan(evaluation, sandbox_permissions=self.sandbox_permissions, permission_profile=self.permission_profile, prompt_permissions=self.prompt_permissions)
        return await self.process_decision(plan, str(program), tuple(argv), Path(workdir))

    async def process_decision(self, plan: ShellEscalationPolicyPlan, program: str, argv: tuple[str, ...], workdir: Path) -> ShellEscalationDecision:
        if plan.decision is Decision.ALLOW or str(plan.decision).lower().endswith('allow'):
            return ShellEscalationDecision.escalate(plan.escalation_execution) if plan.needs_escalation else ShellEscalationDecision.run()
        if plan.decision is Decision.FORBIDDEN or str(plan.decision).lower().endswith('forbidden'):
            return ShellEscalationDecision.deny('Execution forbidden by policy')
        rejected = execve_prompt_is_rejected_by_policy(self.approval_policy, plan.decision_source)
        if rejected is not None:
            return ShellEscalationDecision.deny('Execution forbidden by policy')
        review = await self.prompt(program, argv, workdir, plan.prompt_permissions)
        return shell_escalation_decision_after_review(review, needs_escalation=plan.needs_escalation, escalation_execution=plan.escalation_execution)

    async def prompt(self, program: str, argv: tuple[str, ...], workdir: Path, additional_permissions: AdditionalPermissionProfile | None) -> ReviewDecision:
        command = join_program_and_argv(program, argv)
        hooks = getattr(self.session, 'run_permission_request_hooks', None)
        if callable(hooks):
            hook_result = await _maybe_await_runtime(hooks(self.turn, self.call_id, PermissionRequestPayload.bash(' '.join(command))))
            if hook_result == 'allow' or (isinstance(hook_result, ReviewDecision) and hook_result.type == 'approved'):
                return ReviewDecision.approved()
            if hook_result == 'deny' or (isinstance(hook_result, ReviewDecision) and hook_result.type == 'denied'):
                return ReviewDecision.denied()
        guardian = getattr(self.session, 'review_approval_request', None)
        if callable(guardian):
            decision = await _maybe_await_runtime(guardian(self.turn, self.call_id, {'type': 'execve', 'source': self.tool_name, 'program': program, 'argv': tuple(argv), 'cwd': workdir, 'additional_permissions': additional_permissions}))
            if isinstance(decision, ReviewDecision):
                return decision
        prompt = getattr(self.session, 'request_command_approval', None)
        if callable(prompt):
            decision = await _maybe_await_runtime(prompt(self.turn, self.call_id, None, command, workdir, None, None, None, additional_permissions, (ReviewDecision.approved(), ReviewDecision.abort())))
            if isinstance(decision, ReviewDecision):
                return decision
        return ReviewDecision.abort()

async def try_run_zsh_fork(req: ShellRequest, attempt: SandboxAttempt, ctx: Any, command: tuple[str, ...] | list[str], *, escalation_server_factory: Any | None=None) -> ExecToolCallOutput | None:
    """Run a shell command through the zsh-fork escalation facade."""
    shell_zsh_path = _ctx_service(ctx, 'shell_zsh_path')
    if shell_zsh_path is None:
        return None
    user_shell = getattr(getattr(ctx, 'session', None), 'user_shell', None)
    user_shell_value = user_shell() if callable(user_shell) else user_shell
    shell_type = getattr(user_shell_value, 'shell_type', ShellType.ZSH)
    if shell_type is not ShellType.ZSH:
        return None
    params = shell_zsh_fork_exec_params(command, req.cwd, getattr(req, 'timeout_ms', None))
    stopwatch = CancellationToken()
    cancellation = shell_zsh_fork_cancellation_plan(stopwatch, getattr(attempt, 'network_denial_cancellation_token', None))
    executor = ShellCommandExecutorRunContext(command=tuple(command), cwd=Path(req.cwd), env=exec_env_for_sandbox_permissions(req.env, req.sandbox_permissions), network=managed_network_for_runtime(req.network, req.sandbox_permissions), sandbox=getattr(attempt, 'sandbox', SandboxType.NONE), sandbox_policy_cwd=Path(req.cwd), windows_sandbox_level=WindowsSandboxLevel.DISABLED, permission_profile=PermissionProfile.read_only(), file_system_sandbox_policy=FileSystemSandboxPolicy.unrestricted(), network_sandbox_policy=NetworkSandboxPolicy.RESTRICTED)
    if escalation_server_factory is None:
        escalation_server_factory = _ctx_service(ctx, 'escalation_server_factory')
    if callable(escalation_server_factory):
        result = await _maybe_await_runtime(escalation_server_factory(shell_zsh_path, _ctx_service(ctx, 'main_execve_wrapper_exe')).exec(params, cancellation.cancel_token, executor))
    else:
        result = await shell_command_executor_run(executor, command=tuple(command), cwd=Path(req.cwd), env_overlay={}, cancel_rx=cancellation.cancel_token)
    return map_exec_result(getattr(attempt, 'sandbox', SandboxType.NONE), result)

async def prepare_unified_exec_zsh_fork(req: UnifiedExecRequest, attempt: SandboxAttempt, ctx: Any, exec_request: Any, shell_zsh_path: str | Path, main_execve_wrapper_exe: str | Path, *, escalation_server_factory: Any | None=None) -> PreparedUnifiedExecZshFork | None:
    """Prepare unified-exec zsh-fork session and extend the exec env."""
    del attempt
    parsed = None
    try:
        parsed = extract_shell_script(tuple(exec_request.command))
    except ToolRuntimeError:
        return None
    if parsed.program != str(shell_zsh_path):
        return None
    if escalation_server_factory is None:
        escalation_server_factory = _ctx_service(ctx, 'escalation_server_factory')
    if callable(escalation_server_factory):
        session = await _maybe_await_runtime(escalation_server_factory(Path(shell_zsh_path), Path(main_execve_wrapper_exe)).start_session(CancellationToken(), None))
    else:
        session = ShellEscalationSession(shell_escalation_session_env(0, Path(main_execve_wrapper_exe)))
    return prepare_unified_exec_zsh_fork_from_session(exec_request, Path(shell_zsh_path), session)

@dataclass(frozen=True)
class PreparedUnifiedExecZshFork:
    exec_request: Any
    escalation_session: Any

def shell_request_escalation_execution(sandbox_permissions: SandboxPermissions, permission_profile: PermissionProfile, additional_permissions: AdditionalPermissionProfile | None) -> ShellEscalationExecution:
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError('permission_profile must be PermissionProfile')
    if additional_permissions is not None and (not isinstance(additional_permissions, AdditionalPermissionProfile)):
        raise TypeError('additional_permissions must be AdditionalPermissionProfile or None')
    if sandbox_permissions is SandboxPermissions.REQUIRE_ESCALATED:
        return ShellEscalationExecution.unsandboxed()
    if sandbox_permissions is SandboxPermissions.WITH_ADDITIONAL_PERMISSIONS and additional_permissions is not None:
        return ShellEscalationExecution.permissions(permission_profile)
    return ShellEscalationExecution.turn_default()

def extract_shell_script(command: tuple[str, ...] | list[str]) -> ParsedShellCommand:
    command_tuple = _string_tuple(command, 'command')
    for index in range(max(len(command_tuple) - 2, 0)):
        program, flag, script = command_tuple[index:index + 3]
        if flag == '-c':
            return ParsedShellCommand(program, script, False)
        if flag == '-lc':
            return ParsedShellCommand(program, script, True)
    raise ToolRuntimeError(ToolError.rejected('unexpected shell command format for zsh-fork execution'))

def commands_for_intercepted_exec_policy(program: str | Path, argv: tuple[str, ...] | list[str]) -> CandidateCommands:
    argv_tuple = _string_tuple(argv, 'argv')
    if len(argv_tuple) == 3:
        _, flag, script = argv_tuple
        shell_command = (str(program), flag, script)
        commands = parse_shell_lc_plain_commands(shell_command)
        if commands is not None:
            return CandidateCommands(tuple((tuple(command) for command in commands)), False)
        single_command = parse_shell_lc_single_command_prefix(shell_command)
        if single_command is not None:
            return CandidateCommands((tuple(single_command),), True)
    return CandidateCommands((join_program_and_argv(program, argv_tuple),), False)

def evaluate_intercepted_exec_policy(policy: Any, program: str | Path, argv: tuple[str, ...] | list[str], context: InterceptedExecPolicyContext) -> InterceptedExecPolicyEvaluation:
    from pycodex.execpolicy import Decision, strongest_decision
    if not isinstance(context, InterceptedExecPolicyContext):
        raise TypeError('context must be InterceptedExecPolicyContext')
    if context.enable_shell_wrapper_parsing:
        candidate = commands_for_intercepted_exec_policy(program, argv)
    else:
        candidate = CandidateCommands((join_program_and_argv(program, argv),), False)
    rules = _intercepted_exec_policy_rules(policy)
    host_executables = _intercepted_exec_policy_host_executables(policy)
    matched_rules: list[Mapping[str, Any]] = []
    decisions: list[Decision] = []
    for command in candidate.commands:
        command_matches = _match_intercepted_exec_prefix_rules(command, rules)
        resolved_program = _resolved_host_executable_for_command(command, host_executables)
        if resolved_program is not None:
            host_command = (Path(command[0]).name, *command[1:])
            command_matches = tuple((_prefix_rule_match_with_resolved_program(match, resolved_program) for match in _match_intercepted_exec_prefix_rules(host_command, rules)))
        if command_matches:
            matched_rules.extend(command_matches)
            decisions.extend((decision for match in command_matches for decision in (_runtime_policy_match_decision(match),) if decision is not None))
            continue
        fallback_decision = _render_unix_intercepted_exec_fallback_decision(_intercepted_exec_heuristic_command(command), context, used_complex_parsing=candidate.used_complex_parsing)
        matched_rules.append({'heuristicsRuleMatch': {'command': list(command), 'decision': fallback_decision.value}})
        decisions.append(fallback_decision)
    return InterceptedExecPolicyEvaluation(strongest_decision(decisions), tuple(matched_rules))
__all__ = ['CandidateCommands', 'CoreShellActionProvider', 'DecisionSource', 'ParsedShellCommand', 'PreparedUnifiedExecZshFork', 'commands_for_intercepted_exec_policy', 'evaluate_intercepted_exec_policy', 'extract_shell_script', 'prepare_unified_exec_zsh_fork', 'shell_request_escalation_execution', 'try_run_zsh_fork']
