"""Legacy shell_command handler facade ported from Codex core.

The Rust handler ultimately runs through the shell runtime/orchestrator.  This
stdlib port mirrors the pure boundary behavior: argument parsing, tool spec,
login-shell decision, command derivation, and hook payload shaping.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any

from pycodex.core.exec import ExecCapturePolicy, ExecExpiration, ExecParams
from pycodex.core.exec_env import create_env
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.hook_names import HookToolName
from pycodex.core.shell import Shell
from pycodex.core.tools.handlers.shell_spec import CommandToolOptions, create_shell_command_tool
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.registry import PostToolUsePayload, PreToolUsePayload, ToolInvocation
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    PermissionProfile,
    SandboxPermissions,
    ShellEnvironmentPolicy,
    ThreadId,
    ToolName,
)

JsonValue = Any


class ShellCommandBackend(str, Enum):
    CLASSIC = "classic"
    ZSH_FORK = "zsh_fork"


class ShellCommandBackendConfig(str, Enum):
    CLASSIC = "classic"
    ZSH_FORK = "zsh_fork"


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _json_mapping(arguments: str, label: str) -> dict[str, JsonValue]:
    return _mapping(json.loads(arguments), label)


def _optional_str(data: dict[str, JsonValue], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be a string")
    return value


def _optional_bool(data: dict[str, JsonValue], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be a bool")
    return value


def _optional_int(data: dict[str, JsonValue], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be an integer")
    return value


def _optional_str_tuple(data: dict[str, JsonValue], key: str) -> tuple[str, ...] | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError(f"{key} must be a list of strings")
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
            raise TypeError("command must be a string")
        if self.timeout_ms is not None and (isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int)):
            raise TypeError("timeout_ms must be an integer")
        if self.sandbox_permissions is not None and not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(str(self.sandbox_permissions)))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile")
        if self.prefix_rule is not None and not isinstance(self.prefix_rule, tuple):
            object.__setattr__(self, "prefix_rule", tuple(self.prefix_rule))

    @classmethod
    def from_json(cls, arguments: str) -> "ShellCommandToolCallParams":
        return cls.from_mapping(_json_mapping(arguments, "shell_command arguments"))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ShellCommandToolCallParams":
        data = _mapping(value, "shell_command arguments")
        command = data.get("command")
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        permissions = data.get("sandbox_permissions")
        if isinstance(permissions, str):
            sandbox_permissions = SandboxPermissions(permissions)
        elif permissions is None or isinstance(permissions, SandboxPermissions):
            sandbox_permissions = permissions
        else:
            raise TypeError("sandbox_permissions must be a string")
        additional_permissions = (
            AdditionalPermissionProfile.from_mapping(data["additional_permissions"])
            if data.get("additional_permissions") is not None
            else None
        )
        return cls(
            command=command,
            workdir=_optional_str(data, "workdir"),
            timeout_ms=_optional_int(data, "timeout_ms"),
            login=_optional_bool(data, "login"),
            sandbox_permissions=sandbox_permissions,
            additional_permissions=additional_permissions,
            justification=_optional_str(data, "justification"),
            prefix_rule=_optional_str_tuple(data, "prefix_rule"),
        )

    def sandbox_permissions_or_default(self) -> SandboxPermissions:
        return self.sandbox_permissions or SandboxPermissions.USE_DEFAULT


@dataclass(frozen=True)
class ShellCommandHandlerOptions:
    backend_config: ShellCommandBackendConfig = ShellCommandBackendConfig.CLASSIC
    allow_login_shell: bool = False
    exec_permission_approvals_enabled: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.backend_config, ShellCommandBackendConfig):
            object.__setattr__(self, "backend_config", ShellCommandBackendConfig(str(self.backend_config)))
        if not isinstance(self.allow_login_shell, bool):
            raise TypeError("allow_login_shell must be a bool")
        if not isinstance(self.exec_permission_approvals_enabled, bool):
            raise TypeError("exec_permission_approvals_enabled must be a bool")


class ShellCommandHandler:
    def __init__(self, options: ShellCommandHandlerOptions | ShellCommandBackendConfig | str | None = None) -> None:
        if options is None:
            options = ShellCommandHandlerOptions()
        if isinstance(options, (ShellCommandBackendConfig, str)):
            options = ShellCommandHandlerOptions(backend_config=ShellCommandBackendConfig(str(options)))
        if not isinstance(options, ShellCommandHandlerOptions):
            raise TypeError("options must be ShellCommandHandlerOptions")
        self.options = options
        self.backend = (
            ShellCommandBackend.ZSH_FORK
            if options.backend_config is ShellCommandBackendConfig.ZSH_FORK
            else ShellCommandBackend.CLASSIC
        )

    def tool_name(self) -> ToolName:
        return ToolName.plain("shell_command")

    def spec(self) -> dict[str, JsonValue]:
        return create_shell_command_tool(
            CommandToolOptions(
                self.options.allow_login_shell,
                self.options.exec_permission_approvals_enabled,
            )
        )

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def waits_for_runtime_cancellation(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    @staticmethod
    def resolve_use_login_shell(login: bool | None, allow_login_shell: bool) -> bool:
        if not isinstance(allow_login_shell, bool):
            raise TypeError("allow_login_shell must be a bool")
        if login is not None and not isinstance(login, bool):
            raise TypeError("login must be a bool")
        if login is True and not allow_login_shell:
            raise FunctionCallError.respond_to_model(
                "login shell is disabled by config; omit `login` or set it to false."
            )
        return allow_login_shell if login is None else login

    @staticmethod
    def base_command(shell: Shell, command: str, use_login_shell: bool) -> tuple[str, ...]:
        if not isinstance(shell, Shell):
            raise TypeError("shell must be Shell")
        if not isinstance(command, str):
            raise TypeError("command must be a string")
        return tuple(shell.derive_exec_args(command, use_login_shell))

    @staticmethod
    def to_exec_params(
        params: ShellCommandToolCallParams,
        session: Any,
        turn_context: Any,
        thread_id: ThreadId,
        allow_login_shell: bool,
    ) -> ExecParams:
        if not isinstance(params, ShellCommandToolCallParams):
            raise TypeError("params must be ShellCommandToolCallParams")
        if not isinstance(thread_id, ThreadId):
            raise TypeError("thread_id must be ThreadId")
        shell = _session_user_shell(session)
        use_login_shell = ShellCommandHandler.resolve_use_login_shell(params.login, allow_login_shell)
        command = ShellCommandHandler.base_command(shell, params.command, use_login_shell)
        cwd = _turn_resolve_path(turn_context, params.workdir)
        shell_environment_policy = getattr(turn_context, "shell_environment_policy", None)
        if shell_environment_policy is None:
            shell_environment_policy = ShellEnvironmentPolicy.default()
        if not isinstance(shell_environment_policy, ShellEnvironmentPolicy):
            raise TypeError("turn_context.shell_environment_policy must be ShellEnvironmentPolicy")
        return ExecParams(
            command=command,
            cwd=cwd,
            expiration=ExecExpiration.from_timeout_ms(params.timeout_ms),
            capture_policy=ExecCapturePolicy.SHELL_TOOL,
            env=create_env(shell_environment_policy, thread_id),
            network=getattr(turn_context, "network", None),
            sandbox_permissions=params.sandbox_permissions_or_default(),
            windows_sandbox_level=getattr(turn_context, "windows_sandbox_level", None),
            windows_sandbox_private_desktop=_windows_sandbox_private_desktop(turn_context),
            justification=params.justification,
            arg0=None,
        )

    def shell_runtime_backend(self) -> ShellCommandBackend:
        return self.backend

    @staticmethod
    def build_shell_request(
        exec_params: ExecParams,
        *,
        hook_command: str,
        shell_type: ShellType | str | None,
        cancellation_token: Any = None,
        explicit_env_overrides: Mapping[str, str] | None = None,
        effective_additional_permissions: Any,
        normalized_additional_permissions: AdditionalPermissionProfile | None,
        approval_policy: AskForApproval | GranularApprovalConfig,
        permission_profile: PermissionProfile,
        file_system_sandbox_policy: FileSystemSandboxPolicy,
        sandbox_cwd: Path | str,
        prefix_rule: Sequence[str] | None = None,
        matched_rules: Sequence[object] = (),
    ) -> Any:
        # Rust source: codex-rs/core/src/tools/handlers/shell.rs
        # Behavior anchor: run_exec_like builds ExecApprovalRequest with
        # UseDefault sandbox permissions for preapproved turn permissions, but
        # keeps the effective sandbox permissions on the ShellRequest.
        from pycodex.core.tools.runtimes import ShellRequest
        from pycodex.core.tools.handlers.utils import EffectiveAdditionalPermissions
        from pycodex.execpolicy import ExecApprovalRequest, create_exec_approval_requirement_for_command

        if not isinstance(exec_params, ExecParams):
            raise TypeError("exec_params must be ExecParams")
        if not isinstance(effective_additional_permissions, EffectiveAdditionalPermissions):
            raise TypeError("effective_additional_permissions must be EffectiveAdditionalPermissions")
        approval_sandbox_permissions = (
            SandboxPermissions.USE_DEFAULT
            if effective_additional_permissions.permissions_preapproved
            else effective_additional_permissions.sandbox_permissions
        )
        exec_approval_requirement = create_exec_approval_requirement_for_command(
            ExecApprovalRequest(
                command=exec_params.command,
                approval_policy=approval_policy,
                permission_profile=permission_profile,
                file_system_sandbox_policy=file_system_sandbox_policy,
                sandbox_cwd=Path(sandbox_cwd),
                sandbox_permissions=approval_sandbox_permissions,
                prefix_rule=tuple(prefix_rule) if prefix_rule is not None else None,
                matched_rules=tuple(matched_rules),
            )
        )
        return ShellRequest(
            command=exec_params.command,
            shell_type=shell_type,
            hook_command=hook_command,
            cwd=exec_params.cwd,
            timeout_ms=exec_params.expiration.timeout_ms(),
            cancellation_token=cancellation_token,
            env=dict(exec_params.env),
            explicit_env_overrides=dict(explicit_env_overrides or {}),
            network=exec_params.network,
            sandbox_permissions=effective_additional_permissions.sandbox_permissions,
            additional_permissions=normalized_additional_permissions,
            justification=exec_params.justification,
            exec_approval_requirement=exec_approval_requirement,
            additional_permissions_preapproved=effective_additional_permissions.permissions_preapproved,
        )

    def pre_tool_use_payload(self, invocation: ToolInvocation) -> PreToolUsePayload | None:
        command = shell_command_payload_command(invocation.payload)
        if command is None:
            return None
        return PreToolUsePayload(HookToolName.bash(), {"command": command})

    def with_updated_hook_input(self, invocation: ToolInvocation, updated_input: JsonValue) -> ToolInvocation:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            raise FunctionCallError.respond_to_model(
                "hook input rewrite received unsupported shell_command payload"
            )
        try:
            arguments = _json_mapping(invocation.payload.arguments or "", "shell_command arguments")
            arguments["command"] = updated_hook_command(updated_input)
        except (TypeError, ValueError, json.JSONDecodeError) as err:
            raise FunctionCallError.respond_to_model(str(err)) from err
        return replace(invocation, payload=ToolPayload.function(json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))))

    def post_tool_use_payload(self, invocation: ToolInvocation, result: JsonValue) -> PostToolUsePayload | None:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        response_method = getattr(result, "post_tool_use_response", None)
        if response_method is None:
            return None
        tool_response = response_method(invocation.call_id, invocation.payload)
        if tool_response is None:
            return None
        command = shell_command_payload_command(invocation.payload)
        if command is None:
            return None
        return PostToolUsePayload(HookToolName.bash(), invocation.call_id, {"command": command}, tool_response)


def shell_command_payload_command(payload: ToolPayload) -> str | None:
    if not isinstance(payload, ToolPayload) or payload.type != "function":
        return None
    try:
        return ShellCommandToolCallParams.from_json(payload.arguments or "").command
    except Exception:
        return None


def updated_hook_command(updated_input: JsonValue) -> str:
    from pycodex.core.tools.handlers.utils import updated_hook_command as shared_updated_hook_command

    return shared_updated_hook_command(updated_input)


def _session_user_shell(session: Any) -> Shell:
    user_shell = getattr(session, "user_shell", None)
    shell = user_shell() if callable(user_shell) else getattr(session, "shell", None)
    if not isinstance(shell, Shell):
        raise TypeError("session.user_shell() must return Shell")
    return shell


def _turn_resolve_path(turn_context: Any, workdir: str | None) -> Path:
    resolve_path = getattr(turn_context, "resolve_path", None)
    if callable(resolve_path):
        resolved = resolve_path(workdir)
    else:
        cwd = getattr(turn_context, "cwd", None)
        if cwd is None:
            cwd = Path.cwd()
        resolved = Path(cwd) if workdir is None else Path(cwd) / workdir
    return Path(resolved)


def _windows_sandbox_private_desktop(turn_context: Any) -> bool:
    config = getattr(turn_context, "config", None)
    permissions = getattr(config, "permissions", None)
    value = getattr(permissions, "windows_sandbox_private_desktop", False)
    if not isinstance(value, bool):
        raise TypeError("turn_context.config.permissions.windows_sandbox_private_desktop must be a bool")
    return value


__all__ = [
    "ShellCommandBackend",
    "ShellCommandBackendConfig",
    "ShellCommandHandler",
    "ShellCommandHandlerOptions",
    "ShellCommandToolCallParams",
    "build_shell_request",
    "shell_command_payload_command",
    "updated_hook_command",
]


def build_shell_request(*args: Any, **kwargs: Any) -> Any:
    return ShellCommandHandler.build_shell_request(*args, **kwargs)
