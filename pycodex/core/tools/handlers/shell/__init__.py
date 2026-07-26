"""Legacy shell_command handler facade ported from Codex core.

The Rust handler ultimately runs through the shell runtime/orchestrator.  This
stdlib port mirrors the pure boundary behavior: argument parsing, tool spec,
login-shell decision, command derivation, and hook payload shaping.
"""
from __future__ import annotations
import json
import inspect
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable
from pycodex.core.exec import ExecCapturePolicy, ExecExpiration, ExecParams
from pycodex.core.exec_env import create_env
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType
from pycodex.core.tools.handlers.shell_spec import CommandToolOptions, create_shell_command_tool
from pycodex.core.tools.context import CommandExecutionToolOutput, FunctionToolOutput, ToolPayload
from pycodex.core.tools.registry import PostToolUsePayload, PreToolUsePayload, ToolInvocation
from pycodex.protocol import AdditionalPermissionProfile, AskForApproval, ExecToolCallOutput, FileSystemSandboxPolicy, GranularApprovalConfig, PermissionProfile, SandboxPermissions, ShellEnvironmentPolicy, ThreadId, ToolName, TruncationPolicyConfig
JsonValue = Any
ShellCommandRunner = Callable[['ShellCommandInvocationRequest'], CommandExecutionToolOutput | FunctionToolOutput | str | dict[str, JsonValue] | Any]

def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f'{label} must be a mapping')
    return value

def _json_mapping(arguments: str, label: str) -> dict[str, JsonValue]:
    return _mapping(json.loads(arguments), label)

def _optional_str(data: dict[str, JsonValue], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f'{key} must be a string')
    return value

def _optional_bool(data: dict[str, JsonValue], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f'{key} must be a bool')
    return value

def _optional_int(data: dict[str, JsonValue], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f'{key} must be an integer')
    return value

def _optional_str_tuple(data: dict[str, JsonValue], key: str) -> tuple[str, ...] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all((isinstance(item, str) for item in value)):
        raise TypeError(f'{key} must be a list of strings')
    return tuple(value)

@dataclass(frozen=True)
class ShellCommandToolCallParams:
    command: str
    workdir: str | None = None
    timeout_ms: int | None = None
    login: bool | None = None
    sandbox_permissions: SandboxPermissions | None = None
    additional_permissions: AdditionalPermissionProfile | None = None
    justification: str | None = None
    prefix_rule: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, str):
            raise TypeError('command must be a string')
        if self.timeout_ms is not None and (isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int)):
            raise TypeError('timeout_ms must be an integer')
        if self.sandbox_permissions is not None and (not isinstance(self.sandbox_permissions, SandboxPermissions)):
            object.__setattr__(self, 'sandbox_permissions', SandboxPermissions(str(self.sandbox_permissions)))
        if self.additional_permissions is not None and (not isinstance(self.additional_permissions, AdditionalPermissionProfile)):
            raise TypeError('additional_permissions must be AdditionalPermissionProfile')
        if self.prefix_rule is not None and (not isinstance(self.prefix_rule, tuple)):
            object.__setattr__(self, 'prefix_rule', tuple(self.prefix_rule))

    @classmethod
    def from_json(cls, arguments: str) -> 'ShellCommandToolCallParams':
        return cls.from_mapping(_json_mapping(arguments, 'shell_command arguments'))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> 'ShellCommandToolCallParams':
        data = _mapping(value, 'shell_command arguments')
        command = data.get('command')
        if not isinstance(command, str):
            raise TypeError('command must be a string')
        permissions = data.get('sandbox_permissions')
        if isinstance(permissions, str):
            sandbox_permissions = SandboxPermissions(permissions)
        elif permissions is None or isinstance(permissions, SandboxPermissions):
            sandbox_permissions = permissions
        else:
            raise TypeError('sandbox_permissions must be a string')
        additional_permissions = AdditionalPermissionProfile.from_mapping(data['additional_permissions']) if data.get('additional_permissions') is not None else None
        return cls(command=command, workdir=_optional_str(data, 'workdir'), timeout_ms=_optional_int(data, 'timeout_ms'), login=_optional_bool(data, 'login'), sandbox_permissions=sandbox_permissions, additional_permissions=additional_permissions, justification=_optional_str(data, 'justification'), prefix_rule=_optional_str_tuple(data, 'prefix_rule'))

    def sandbox_permissions_or_default(self) -> SandboxPermissions:
        return self.sandbox_permissions or SandboxPermissions.USE_DEFAULT

@dataclass(frozen=True)
class RunExecLikeArgs:
    tool_name: ToolName
    exec_params: ExecParams
    cancellation_token: Any
    hook_command: str
    shell_type: ShellType | None
    additional_permissions: AdditionalPermissionProfile | None
    prefix_rule: tuple[str, ...] | None
    session: Any
    turn: Any
    tracker: Any
    call_id: str
    shell_runtime_backend: ShellCommandBackend
    invocation: ToolInvocation
    params: ShellCommandToolCallParams
    workdir: Path
    runner: ShellCommandRunner | None

    def __post_init__(self) -> None:
        if not isinstance(self.tool_name, ToolName):
            raise TypeError('tool_name must be ToolName')
        if not isinstance(self.exec_params, ExecParams):
            raise TypeError('exec_params must be ExecParams')
        if not isinstance(self.hook_command, str):
            raise TypeError('hook_command must be a string')
        if self.shell_type is not None and (not isinstance(self.shell_type, ShellType)):
            object.__setattr__(self, 'shell_type', ShellType(str(self.shell_type)))
        if self.additional_permissions is not None and (not isinstance(self.additional_permissions, AdditionalPermissionProfile)):
            raise TypeError('additional_permissions must be AdditionalPermissionProfile')
        if self.prefix_rule is not None:
            object.__setattr__(self, 'prefix_rule', tuple(self.prefix_rule))
        if not isinstance(self.call_id, str):
            raise TypeError('call_id must be a string')
        if not isinstance(self.shell_runtime_backend, ShellCommandBackend):
            object.__setattr__(self, 'shell_runtime_backend', ShellCommandBackend(str(self.shell_runtime_backend)))
        if not isinstance(self.invocation, ToolInvocation):
            raise TypeError('invocation must be ToolInvocation')
        if not isinstance(self.params, ShellCommandToolCallParams):
            raise TypeError('params must be ShellCommandToolCallParams')
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, 'workdir', Path(self.workdir))
        if self.runner is not None and (not callable(self.runner)):
            raise TypeError('runner must be callable or None')

async def run_exec_like(args: RunExecLikeArgs) -> FunctionToolOutput | str | dict[str, JsonValue] | Any:
    from pycodex.core.tools.handlers import apply_granted_turn_permissions, implicit_granted_permissions, normalize_and_validate_additional_permissions
    if not isinstance(args, RunExecLikeArgs):
        raise TypeError('args must be RunExecLikeArgs')
    turn_environment = _primary_turn_environment(args.turn)
    if turn_environment is None and (not hasattr(args.turn, 'cwd')):
        raise FunctionCallError.respond_to_model('shell is unavailable in this session')
    requested_additional_permissions = args.additional_permissions
    effective_additional_permissions = await apply_granted_turn_permissions(_session_with_permission_accessors(args.session), args.exec_params.cwd, args.exec_params.sandbox_permissions, args.additional_permissions)
    additional_permissions_allowed = _exec_permission_approvals_enabled(args.session) or (_request_permissions_tool_enabled(args.session) and effective_additional_permissions.permissions_preapproved)
    approval_policy = _turn_approval_policy(args.turn)
    if effective_additional_permissions.sandbox_permissions.requests_sandbox_override() and (not effective_additional_permissions.permissions_preapproved) and (not _approval_policy_is_on_request(approval_policy)):
        raise FunctionCallError.respond_to_model(f'approval policy is {approval_policy!r}; reject command - you should not ask for escalated permissions if the approval policy is {approval_policy!r}')
    try:
        normalized_additional_permissions = implicit_granted_permissions(args.exec_params.sandbox_permissions, requested_additional_permissions, effective_additional_permissions)
        if normalized_additional_permissions is None:
            normalized_additional_permissions = normalize_and_validate_additional_permissions(additional_permissions_allowed, approval_policy, effective_additional_permissions.sandbox_permissions, effective_additional_permissions.additional_permissions, effective_additional_permissions.permissions_preapproved, args.exec_params.cwd)
    except (TypeError, ValueError) as error:
        raise FunctionCallError.respond_to_model(str(error)) from error
    shell_request = build_shell_request(args.exec_params, hook_command=args.hook_command, shell_type=args.shell_type, cancellation_token=args.cancellation_token, explicit_env_overrides=_turn_explicit_env_overrides(args.turn), effective_additional_permissions=effective_additional_permissions, normalized_additional_permissions=normalized_additional_permissions, approval_policy=approval_policy, permission_profile=_turn_permission_profile(args.turn), file_system_sandbox_policy=_turn_file_system_sandbox_policy(args.turn), sandbox_cwd=_turn_cwd(args.turn, args.exec_params.cwd), prefix_rule=args.prefix_rule)
    request = ShellCommandInvocationRequest(invocation=args.invocation, params=args.params, exec_params=args.exec_params, hook_command=args.hook_command, shell_type=args.shell_type, prefix_rule=args.prefix_rule, backend=args.shell_runtime_backend, workdir=args.workdir, shell_request=shell_request)
    if args.runner is None:
        result = await _run_product_shell_runtime(request)
    else:
        result = args.runner(request)
        if inspect.isawaitable(result):
            result = await result
    return _shell_command_output(result)

async def _run_product_shell_runtime(request: ShellCommandInvocationRequest) -> CommandExecutionToolOutput:
    """Run the Rust-owned shell runtime when no test adapter is injected."""
    from pycodex.core.tools.orchestrator import OrchestratorRunResult, ToolOrchestrator
    from pycodex.core.tools.runtimes import ShellRuntime, ShellRuntimeBackend
    from pycodex.core.tools.sandboxing import ToolCtx, ToolError
    from pycodex.core.user_shell_command import format_exec_output_for_model
    shell_request = request.shell_request
    if shell_request is None:
        raise FunctionCallError.respond_to_model('shell_command request was not prepared')
    backend = ShellRuntimeBackend.SHELL_COMMAND_ZSH_FORK if request.backend is ShellCommandBackend.ZSH_FORK else ShellRuntimeBackend.SHELL_COMMAND_CLASSIC
    runtime = ShellRuntime.for_shell_command(backend)
    invocation = request.invocation
    turn = invocation.turn
    permission_profile = _turn_permission_profile(turn)
    file_system_sandbox_policy = _turn_file_system_sandbox_policy(turn)
    tool_ctx = ToolCtx(session=invocation.session, turn=turn, call_id=invocation.call_id, tool_name=ToolName.plain('shell_command'))
    orchestrator_turn = {'permission_profile': permission_profile, 'file_system_sandbox_policy': file_system_sandbox_policy, 'network_sandbox_policy': permission_profile.network_sandbox_policy(), 'network': getattr(turn, 'network', None), 'cwd': _turn_cwd(turn, request.workdir), 'features': getattr(turn, 'features', None), 'config': getattr(turn, 'config', None), 'windows_sandbox_level': getattr(turn, 'windows_sandbox_level', None), 'codex_linux_sandbox_exe': getattr(turn, 'codex_linux_sandbox_exe', None), 'session_telemetry': getattr(turn, 'session_telemetry', None), 'routes_approval_to_guardian': getattr(turn, 'routes_approval_to_guardian', False)}
    result = await ToolOrchestrator.new().run(runtime, shell_request, tool_ctx, orchestrator_turn, _turn_approval_policy(turn))
    if isinstance(result, ToolError):
        if result.type == 'rejected':
            message = result.message or 'shell command rejected'
        elif isinstance(result.error, Mapping) and isinstance(result.error.get('output'), ExecToolCallOutput):
            result = result.error['output']
            message = ''
        else:
            message = str(result.error)
        if isinstance(result, ToolError):
            raise FunctionCallError.respond_to_model(message)
    elif isinstance(result, OrchestratorRunResult):
        result = result.output
    else:
        raise TypeError('shell command orchestrator returned an invalid result')
    if not isinstance(result, ExecToolCallOutput):
        raise TypeError('shell command runtime returned an invalid output')
    truncation_policy = getattr(turn, 'truncation_policy', None)
    if not isinstance(truncation_policy, TruncationPolicyConfig):
        truncation_policy = TruncationPolicyConfig.tokens(10000)
    model_visible = FunctionToolOutput.from_text(format_exec_output_for_model(result, truncation_policy), success=result.exit_code == 0 and (not result.timed_out))
    return CommandExecutionToolOutput(model_visible=model_visible, exec_output=result)

def shell_command_payload_command(payload: ToolPayload) -> str | None:
    if not isinstance(payload, ToolPayload) or payload.type != 'function':
        return None
    try:
        return ShellCommandToolCallParams.from_json(payload.arguments or '').command
    except Exception:
        return None

def updated_hook_command(updated_input: JsonValue) -> str:
    from pycodex.core.tools.handlers import updated_hook_command as shared_updated_hook_command
    return shared_updated_hook_command(updated_input)

def _session_user_shell(session: Any) -> Shell:
    user_shell = getattr(session, 'user_shell', None)
    shell = user_shell() if callable(user_shell) else getattr(session, 'shell', None)
    if not isinstance(shell, Shell):
        raise TypeError('session.user_shell() must return Shell')
    return shell

def _turn_resolve_path(turn_context: Any, workdir: str | None) -> Path:
    resolve_path = getattr(turn_context, 'resolve_path', None)
    if callable(resolve_path):
        resolved = resolve_path(workdir)
    else:
        cwd = getattr(turn_context, 'cwd', None)
        if cwd is None:
            cwd = Path.cwd()
        resolved = Path(cwd) if workdir is None else Path(cwd) / workdir
    return Path(resolved)

def _windows_sandbox_private_desktop(turn_context: Any) -> bool:
    config = getattr(turn_context, 'config', None)
    permissions = getattr(config, 'permissions', None)
    value = getattr(permissions, 'windows_sandbox_private_desktop', False)
    if not isinstance(value, bool):
        raise TypeError('turn_context.config.permissions.windows_sandbox_private_desktop must be a bool')
    return value

async def _await_shell_command_handle(handler: ShellCommandHandler, invocation: ToolInvocation, params: ShellCommandToolCallParams, workdir: Path, maybe_emitted: Any) -> FunctionToolOutput:
    await maybe_emitted
    response = handler._handle_after_skill_invocation(invocation, params, workdir)
    if inspect.isawaitable(response):
        return await response
    return response

async def _await_shell_command_response(response: Any) -> CommandExecutionToolOutput | FunctionToolOutput:
    return _shell_command_output(await response)

def _shell_command_output(response: CommandExecutionToolOutput | FunctionToolOutput | str | dict[str, JsonValue]) -> CommandExecutionToolOutput | FunctionToolOutput:
    if isinstance(response, CommandExecutionToolOutput | FunctionToolOutput):
        return response
    if isinstance(response, str):
        return FunctionToolOutput.from_text(response, True)
    if isinstance(response, Mapping):
        text = response.get('text')
        if not isinstance(text, str):
            text = json.dumps(dict(response), ensure_ascii=False, separators=(',', ':'))
        success = response.get('success', True)
        if success is not None and (not isinstance(success, bool)):
            raise TypeError('shell command runner success must be a bool or None')
        post = response.get('post_tool_use_response')
        return FunctionToolOutput(({'type': 'input_text', 'text': text},), success=success, post_tool_use_response_value=post)
    raise TypeError('shell command runner must return FunctionToolOutput, string, or mapping')

def _maybe_emit_implicit_skill_invocation(sess: Any, turn_context: Any, command: str, workdir: Path) -> Any:
    from pycodex.core.skills import maybe_emit_implicit_skill_invocation
    return maybe_emit_implicit_skill_invocation(sess, turn_context, command, workdir)

def _primary_turn_environment(turn_context: Any) -> Any | None:
    environments = getattr(turn_context, 'environments', None)
    primary = getattr(environments, 'primary', None)
    if callable(primary):
        return primary()
    if primary is not None:
        return primary
    if isinstance(environments, (tuple, list)):
        return environments[0] if environments else None
    candidates = getattr(environments, 'turn_environments', None)
    if candidates is None:
        candidates = getattr(environments, 'environments', None)
    if candidates is not None:
        return candidates[0] if candidates else None
    return None

def _session_with_permission_accessors(session: Any) -> Any:

    class SessionPermissionAccess:

        def granted_session_permissions(self) -> AdditionalPermissionProfile | None:
            getter = getattr(session, 'granted_session_permissions', None)
            return getter() if callable(getter) else getattr(session, 'granted_permissions', None)

        def granted_turn_permissions(self) -> AdditionalPermissionProfile | None:
            getter = getattr(session, 'granted_turn_permissions', None)
            return getter() if callable(getter) else getattr(session, 'granted_turn_permission_profile', None)
    return SessionPermissionAccess()

def _feature_enabled(session: Any, feature_name: str) -> bool:
    features = getattr(session, 'features', None)
    if callable(features):
        features = features()
    enabled = getattr(features, 'enabled', None)
    if callable(enabled):
        try:
            return bool(enabled(feature_name))
        except Exception:
            return False
    if isinstance(features, Mapping):
        return bool(features.get(feature_name, False))
    return bool(getattr(session, feature_name, False))

def _exec_permission_approvals_enabled(session: Any) -> bool:
    return _feature_enabled(session, 'exec_permission_approvals') or _feature_enabled(session, 'ExecPermissionApprovals')

def _request_permissions_tool_enabled(session: Any) -> bool:
    return _feature_enabled(session, 'request_permissions_tool') or _feature_enabled(session, 'RequestPermissionsTool')

def _turn_approval_policy(turn_context: Any) -> AskForApproval | GranularApprovalConfig:
    value = getattr(turn_context, 'approval_policy', AskForApproval.ON_REQUEST)
    if callable(value):
        value = value()
    else:
        cell_value = getattr(value, 'value', None)
        if callable(cell_value):
            value = cell_value()
    if isinstance(value, (AskForApproval, GranularApprovalConfig)):
        return value
    return AskForApproval.parse(str(value))

def _approval_policy_is_on_request(policy: AskForApproval | GranularApprovalConfig) -> bool:
    return isinstance(policy, AskForApproval) and policy is AskForApproval.ON_REQUEST

def _turn_explicit_env_overrides(turn_context: Any) -> dict[str, str]:
    policy = getattr(turn_context, 'shell_environment_policy', None)
    values = getattr(policy, 'set_values', None)
    if values is None:
        values = getattr(policy, 'set', None)
    if values is None:
        return {}
    return {str(key): str(value) for key, value in dict(values).items()}

def _turn_permission_profile(turn_context: Any) -> PermissionProfile:
    value = getattr(turn_context, 'permission_profile', None)
    if callable(value):
        value = value()
    if value is None:
        config = getattr(turn_context, 'config', None)
        value = getattr(config, 'permission_profile', None)
        if callable(value):
            value = value()
    if value is None:
        return PermissionProfile.disabled()
    if not isinstance(value, PermissionProfile):
        raise TypeError('turn_context.permission_profile must be PermissionProfile')
    return value

def _turn_file_system_sandbox_policy(turn_context: Any) -> FileSystemSandboxPolicy:
    value = getattr(turn_context, 'file_system_sandbox_policy', None)
    if callable(value):
        value = value()
    if value is None:
        profile = _turn_permission_profile(turn_context)
        return profile.file_system_sandbox_policy()
    if not isinstance(value, FileSystemSandboxPolicy):
        raise TypeError('turn_context.file_system_sandbox_policy must be FileSystemSandboxPolicy')
    return value

def _turn_cwd(turn_context: Any, fallback: Path) -> Path:
    value = getattr(turn_context, 'cwd', fallback)
    if callable(value):
        value = value()
    return Path(value)

def _session_thread_id(session: Any) -> ThreadId:
    thread_id = getattr(session, 'conversation_id', None)
    if isinstance(thread_id, ThreadId):
        return thread_id
    if isinstance(thread_id, str):
        return ThreadId.from_string(thread_id)
    return ThreadId.new()

def _allow_login_shell(turn_context: Any, fallback: bool) -> bool:
    config = getattr(turn_context, 'config', None)
    permissions = getattr(config, 'permissions', None)
    value = getattr(permissions, 'allow_login_shell', fallback)
    if not isinstance(value, bool):
        raise TypeError('turn_context.config.permissions.allow_login_shell must be a bool')
    return value
__all__ = ['ShellCommandBackend', 'ShellCommandBackendConfig', 'ShellCommandHandler', 'ShellCommandHandlerOptions', 'ShellCommandInvocationRequest', 'ShellCommandRunner', 'ShellCommandToolCallParams', 'RunExecLikeArgs', 'build_shell_request', 'run_exec_like', 'shell_command_payload_command', 'updated_hook_command']

def build_shell_request(*args: Any, **kwargs: Any) -> Any:
    return ShellCommandHandler.build_shell_request(*args, **kwargs)

from .shell_command import (
    ShellCommandBackend,
    ShellCommandBackendConfig,
    ShellCommandHandler,
    ShellCommandHandlerOptions,
    ShellCommandInvocationRequest,
)
