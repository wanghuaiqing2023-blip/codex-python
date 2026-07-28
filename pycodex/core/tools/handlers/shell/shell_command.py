"""Port of the Rust `shell_command` child module."""
from __future__ import annotations
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
from . import JsonValue, RunExecLikeArgs, ShellCommandRunner, ShellCommandToolCallParams, _allow_login_shell, _await_shell_command_handle, _await_shell_command_response, _json_mapping, _maybe_emit_implicit_skill_invocation, _session_thread_id, _session_user_shell, _shell_command_output, _turn_resolve_path, _windows_sandbox_private_desktop, run_exec_like, shell_command_payload_command, updated_hook_command

class ShellCommandBackend(str, Enum):
    CLASSIC = 'classic'
    ZSH_FORK = 'zsh_fork'

class ShellCommandBackendConfig(str, Enum):
    CLASSIC = 'classic'
    ZSH_FORK = 'zsh_fork'

@dataclass(frozen=True)
class ShellCommandHandlerOptions:
    backend_config: ShellCommandBackendConfig = ShellCommandBackendConfig.CLASSIC
    allow_login_shell: bool = False
    exec_permission_approvals_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.backend_config, ShellCommandBackendConfig):
            object.__setattr__(self, 'backend_config', ShellCommandBackendConfig(str(self.backend_config)))
        if not isinstance(self.allow_login_shell, bool):
            raise TypeError('allow_login_shell must be a bool')
        if not isinstance(self.exec_permission_approvals_enabled, bool):
            raise TypeError('exec_permission_approvals_enabled must be a bool')

@dataclass(frozen=True)
class ShellCommandInvocationRequest:
    invocation: ToolInvocation
    params: ShellCommandToolCallParams
    exec_params: ExecParams
    hook_command: str
    shell_type: ShellType | None
    prefix_rule: tuple[str, ...] | None
    backend: ShellCommandBackend
    workdir: Path
    shell_request: Any | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.invocation, ToolInvocation):
            raise TypeError('invocation must be ToolInvocation')
        if not isinstance(self.params, ShellCommandToolCallParams):
            raise TypeError('params must be ShellCommandToolCallParams')
        if not isinstance(self.exec_params, ExecParams):
            raise TypeError('exec_params must be ExecParams')
        if not isinstance(self.hook_command, str):
            raise TypeError('hook_command must be a string')
        if self.shell_type is not None and (not isinstance(self.shell_type, ShellType)):
            object.__setattr__(self, 'shell_type', ShellType(str(self.shell_type)))
        if self.prefix_rule is not None:
            object.__setattr__(self, 'prefix_rule', tuple(self.prefix_rule))
        if not isinstance(self.backend, ShellCommandBackend):
            object.__setattr__(self, 'backend', ShellCommandBackend(str(self.backend)))
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, 'workdir', Path(self.workdir))

class ShellCommandHandler:

    def __init__(self, options: ShellCommandHandlerOptions | ShellCommandBackendConfig | str | None=None, runner: ShellCommandRunner | None=None) -> None:
        if options is None:
            options = ShellCommandHandlerOptions()
        if isinstance(options, (ShellCommandBackendConfig, str)):
            options = ShellCommandHandlerOptions(backend_config=ShellCommandBackendConfig(str(options)))
        if not isinstance(options, ShellCommandHandlerOptions):
            raise TypeError('options must be ShellCommandHandlerOptions')
        if runner is not None and (not callable(runner)):
            raise TypeError('runner must be callable or None')
        self.options = options
        self._runner = runner
        self.backend = ShellCommandBackend.ZSH_FORK if options.backend_config is ShellCommandBackendConfig.ZSH_FORK else ShellCommandBackend.CLASSIC

    def tool_name(self) -> ToolName:
        return ToolName.plain('shell_command')

    def spec(self) -> dict[str, JsonValue]:
        return create_shell_command_tool(CommandToolOptions(self.options.allow_login_shell, self.options.exec_permission_approvals_enabled))

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def waits_for_runtime_cancellation(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == 'function'

    def handle(self, invocation: ToolInvocation) -> FunctionToolOutput | Any:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError('invocation must be ToolInvocation')
        if invocation.payload.type != 'function':
            raise FunctionCallError.respond_to_model(f'unsupported payload for shell_command handler: {self.tool_name()}')
        arguments = invocation.payload.arguments
        if arguments is None:
            raise FunctionCallError.respond_to_model(f'unsupported payload for shell_command handler: {self.tool_name()}')
        try:
            params = ShellCommandToolCallParams.from_json(arguments)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            raise FunctionCallError.respond_to_model(f'failed to parse function arguments: {err}') from err
        turn = invocation.turn
        session = invocation.session
        workdir = _turn_resolve_path(turn, params.workdir)
        maybe_emitted = _maybe_emit_implicit_skill_invocation(session, turn, params.command, workdir)
        if inspect.isawaitable(maybe_emitted):
            return _await_shell_command_handle(self, invocation, params, workdir, maybe_emitted)
        return self._handle_after_skill_invocation(invocation, params, workdir)

    def _handle_after_skill_invocation(self, invocation: ToolInvocation, params: ShellCommandToolCallParams, workdir: Path) -> FunctionToolOutput | Any:
        session = invocation.session
        turn = invocation.turn
        exec_params = self.to_exec_params(params, session, turn, _session_thread_id(session), _allow_login_shell(turn, self.options.allow_login_shell))
        runner = self._runner or getattr(session, 'shell_command_runner', None)
        response = run_exec_like(RunExecLikeArgs(tool_name=self.tool_name(), exec_params=exec_params, cancellation_token=getattr(invocation, 'cancellation_token', None), hook_command=params.command, shell_type=self.session_shell(session).shell_type, additional_permissions=params.additional_permissions, prefix_rule=params.prefix_rule, session=session, turn=turn, tracker=getattr(invocation, 'tracker', None), call_id=invocation.call_id, shell_runtime_backend=self.shell_runtime_backend(), invocation=invocation, params=params, workdir=workdir, runner=runner))
        if inspect.isawaitable(response):
            return _await_shell_command_response(response)
        return _shell_command_output(response)

    @staticmethod
    def resolve_use_login_shell(login: bool | None, allow_login_shell: bool) -> bool:
        if not isinstance(allow_login_shell, bool):
            raise TypeError('allow_login_shell must be a bool')
        if login is not None and (not isinstance(login, bool)):
            raise TypeError('login must be a bool')
        if login is True and (not allow_login_shell):
            raise FunctionCallError.respond_to_model('login shell is disabled by config; omit `login` or set it to false.')
        return allow_login_shell if login is None else login

    @staticmethod
    def session_shell(session: Any) -> Shell:
        """Resolve the canonical shell shared by execution and event projection."""
        return _session_user_shell(session)

    @staticmethod
    def base_command(shell: Shell, command: str, use_login_shell: bool) -> tuple[str, ...]:
        if not isinstance(shell, Shell):
            raise TypeError('shell must be Shell')
        if not isinstance(command, str):
            raise TypeError('command must be a string')
        return tuple(shell.derive_exec_args(command, use_login_shell))

    @staticmethod
    def to_exec_params(params: ShellCommandToolCallParams, session: Any, turn_context: Any, thread_id: ThreadId, allow_login_shell: bool) -> ExecParams:
        if not isinstance(params, ShellCommandToolCallParams):
            raise TypeError('params must be ShellCommandToolCallParams')
        if not isinstance(thread_id, ThreadId):
            raise TypeError('thread_id must be ThreadId')
        shell = ShellCommandHandler.session_shell(session)
        use_login_shell = ShellCommandHandler.resolve_use_login_shell(params.login, allow_login_shell)
        command = ShellCommandHandler.base_command(shell, params.command, use_login_shell)
        cwd = _turn_resolve_path(turn_context, params.workdir)
        shell_environment_policy = getattr(turn_context, 'shell_environment_policy', None)
        if shell_environment_policy is None:
            shell_environment_policy = ShellEnvironmentPolicy.default()
        if not isinstance(shell_environment_policy, ShellEnvironmentPolicy):
            raise TypeError('turn_context.shell_environment_policy must be ShellEnvironmentPolicy')
        return ExecParams(command=command, cwd=cwd, expiration=ExecExpiration.from_timeout_ms(params.timeout_ms), capture_policy=ExecCapturePolicy.SHELL_TOOL, env=create_env(shell_environment_policy, thread_id), network=getattr(turn_context, 'network', None), sandbox_permissions=params.sandbox_permissions_or_default(), windows_sandbox_level=getattr(turn_context, 'windows_sandbox_level', None), windows_sandbox_private_desktop=_windows_sandbox_private_desktop(turn_context), justification=params.justification, arg0=None)

    def shell_runtime_backend(self) -> ShellCommandBackend:
        return self.backend

    @staticmethod
    def build_shell_request(exec_params: ExecParams, *, hook_command: str, shell_type: ShellType | str | None, cancellation_token: Any=None, explicit_env_overrides: Mapping[str, str] | None=None, effective_additional_permissions: Any, normalized_additional_permissions: AdditionalPermissionProfile | None, approval_policy: AskForApproval | GranularApprovalConfig, permission_profile: PermissionProfile, file_system_sandbox_policy: FileSystemSandboxPolicy, sandbox_cwd: Path | str, prefix_rule: Sequence[str] | None=None, matched_rules: Sequence[object]=()) -> Any:
        from pycodex.core.tools.runtimes import ShellRequest
        from pycodex.core.tools.handlers import EffectiveAdditionalPermissions
        from pycodex.core.exec_policy import (
            ExecApprovalRequest,
            create_exec_approval_requirement_for_command,
        )
        if not isinstance(exec_params, ExecParams):
            raise TypeError('exec_params must be ExecParams')
        if not isinstance(effective_additional_permissions, EffectiveAdditionalPermissions):
            raise TypeError('effective_additional_permissions must be EffectiveAdditionalPermissions')
        approval_sandbox_permissions = SandboxPermissions.USE_DEFAULT if effective_additional_permissions.permissions_preapproved else effective_additional_permissions.sandbox_permissions
        exec_approval_requirement = create_exec_approval_requirement_for_command(ExecApprovalRequest(command=exec_params.command, approval_policy=approval_policy, permission_profile=permission_profile, file_system_sandbox_policy=file_system_sandbox_policy, sandbox_cwd=Path(sandbox_cwd), sandbox_permissions=approval_sandbox_permissions, prefix_rule=tuple(prefix_rule) if prefix_rule is not None else None, matched_rules=tuple(matched_rules)))
        return ShellRequest(command=exec_params.command, shell_type=shell_type, hook_command=hook_command, cwd=exec_params.cwd, timeout_ms=exec_params.expiration.timeout_ms(), cancellation_token=cancellation_token, env=dict(exec_params.env), explicit_env_overrides=dict(explicit_env_overrides or {}), network=exec_params.network, sandbox_permissions=effective_additional_permissions.sandbox_permissions, additional_permissions=normalized_additional_permissions, justification=exec_params.justification, exec_approval_requirement=exec_approval_requirement, additional_permissions_preapproved=effective_additional_permissions.permissions_preapproved, capture_policy=exec_params.capture_policy)

    def pre_tool_use_payload(self, invocation: ToolInvocation) -> PreToolUsePayload | None:
        command = shell_command_payload_command(invocation.payload)
        if command is None:
            return None
        return PreToolUsePayload(HookToolName.bash(), {'command': command})

    def with_updated_hook_input(self, invocation: ToolInvocation, updated_input: JsonValue) -> ToolInvocation:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError('invocation must be ToolInvocation')
        if invocation.payload.type != 'function':
            raise FunctionCallError.respond_to_model('hook input rewrite received unsupported shell_command payload')
        try:
            arguments = _json_mapping(invocation.payload.arguments or '', 'shell_command arguments')
            arguments['command'] = updated_hook_command(updated_input)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            raise FunctionCallError.respond_to_model(str(err)) from err
        return replace(invocation, payload=ToolPayload.function(json.dumps(arguments, ensure_ascii=False, separators=(',', ':'))))

    def post_tool_use_payload(self, invocation: ToolInvocation, result: JsonValue) -> PostToolUsePayload | None:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError('invocation must be ToolInvocation')
        response_method = getattr(result, 'post_tool_use_response', None)
        if response_method is None:
            return None
        tool_response = response_method(invocation.call_id, invocation.payload)
        if tool_response is None:
            return None
        command = shell_command_payload_command(invocation.payload)
        if command is None:
            return None
        return PostToolUsePayload(HookToolName.bash(), invocation.call_id, {'command': command}, tool_response)
__all__ = ['ShellCommandBackend', 'ShellCommandBackendConfig', 'ShellCommandHandler', 'ShellCommandHandlerOptions', 'ShellCommandInvocationRequest']
