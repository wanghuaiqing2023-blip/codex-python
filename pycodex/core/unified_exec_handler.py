"""Unified exec tool handler facades ported from Codex core.

This module mirrors the pure argument, command-resolution, spec, and hook
payload behavior from ``core/src/tools/handlers/unified_exec``. It deliberately
does not start processes; process management stays outside this stdlib port.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.core.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType, default_user_shell, get_shell_by_model_provided_path
from pycodex.core.shell_spec import (
    CommandToolOptions,
    create_exec_command_tool_with_environment_id,
    create_write_stdin_tool,
)
from pycodex.core.tool_context import ToolPayload
from pycodex.core.tool_registry import PostToolUsePayload, PreToolUsePayload, ToolInvocation
from pycodex.protocol import AdditionalPermissionProfile, SandboxPermissions, ToolName

JsonValue = Any

DEFAULT_EXEC_YIELD_TIME_MS = 10_000
DEFAULT_WRITE_STDIN_YIELD_TIME_MS = 250


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
class ExecCommandArgs:
    cmd: str
    workdir: str | None = None
    shell: str | None = None
    login: bool | None = None
    tty: bool = False
    yield_time_ms: int = DEFAULT_EXEC_YIELD_TIME_MS
    max_output_tokens: int | None = None
    sandbox_permissions: SandboxPermissions = SandboxPermissions.USE_DEFAULT
    additional_permissions: AdditionalPermissionProfile | None = None
    justification: str | None = None
    prefix_rule: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.cmd, str):
            raise TypeError("cmd must be a string")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer")
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(str(self.sandbox_permissions)))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile")
        if self.prefix_rule is not None and not isinstance(self.prefix_rule, tuple):
            object.__setattr__(self, "prefix_rule", tuple(self.prefix_rule))

    @classmethod
    def from_json(cls, arguments: str) -> "ExecCommandArgs":
        return cls.from_mapping(_json_mapping(arguments, "exec_command arguments"))

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ExecCommandArgs":
        data = _mapping(value, "exec_command arguments")
        cmd = data.get("cmd")
        if not isinstance(cmd, str):
            raise TypeError("cmd must be a string")
        permissions = data.get("sandbox_permissions", SandboxPermissions.USE_DEFAULT.value)
        if isinstance(permissions, SandboxPermissions):
            sandbox_permissions = permissions
        elif isinstance(permissions, str):
            sandbox_permissions = SandboxPermissions(permissions)
        else:
            raise TypeError("sandbox_permissions must be a string")
        additional_permissions = (
            AdditionalPermissionProfile.from_mapping(data["additional_permissions"])
            if data.get("additional_permissions") is not None
            else None
        )
        return cls(
            cmd=cmd,
            workdir=_optional_str(data, "workdir"),
            shell=_optional_str(data, "shell"),
            login=_optional_bool(data, "login"),
            tty=data.get("tty", False),
            yield_time_ms=data.get("yield_time_ms", DEFAULT_EXEC_YIELD_TIME_MS),
            max_output_tokens=_optional_int(data, "max_output_tokens"),
            sandbox_permissions=sandbox_permissions,
            additional_permissions=additional_permissions,
            justification=_optional_str(data, "justification"),
            prefix_rule=_optional_str_tuple(data, "prefix_rule"),
        )

    def to_mapping(self) -> dict[str, JsonValue]:
        data: dict[str, JsonValue] = {
            "cmd": self.cmd,
            "tty": self.tty,
            "yield_time_ms": self.yield_time_ms,
            "sandbox_permissions": self.sandbox_permissions.value,
        }
        if self.workdir is not None:
            data["workdir"] = self.workdir
        if self.shell is not None:
            data["shell"] = self.shell
        if self.login is not None:
            data["login"] = self.login
        if self.max_output_tokens is not None:
            data["max_output_tokens"] = self.max_output_tokens
        if self.additional_permissions is not None:
            data["additional_permissions"] = self.additional_permissions.to_mapping()
        if self.justification is not None:
            data["justification"] = self.justification
        if self.prefix_rule is not None:
            data["prefix_rule"] = list(self.prefix_rule)
        return data


@dataclass(frozen=True)
class ExecCommandEnvironmentArgs:
    environment_id: str | None = None
    workdir: str | None = None

    @classmethod
    def from_json(cls, arguments: str) -> "ExecCommandEnvironmentArgs":
        data = _json_mapping(arguments, "exec_command environment arguments")
        return cls(environment_id=_optional_str(data, "environment_id"), workdir=_optional_str(data, "workdir"))


@dataclass(frozen=True)
class WriteStdinArgs:
    session_id: int
    chars: str = ""
    yield_time_ms: int = DEFAULT_WRITE_STDIN_YIELD_TIME_MS
    max_output_tokens: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.session_id, bool) or not isinstance(self.session_id, int):
            raise TypeError("session_id must be an integer")
        if not isinstance(self.chars, str):
            raise TypeError("chars must be a string")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer")

    @classmethod
    def from_json(cls, arguments: str) -> "WriteStdinArgs":
        data = _json_mapping(arguments, "write_stdin arguments")
        session_id = data.get("session_id")
        if isinstance(session_id, bool) or not isinstance(session_id, int):
            raise TypeError("session_id must be an integer")
        return cls(
            session_id=session_id,
            chars=data.get("chars", ""),
            yield_time_ms=data.get("yield_time_ms", DEFAULT_WRITE_STDIN_YIELD_TIME_MS),
            max_output_tokens=_optional_int(data, "max_output_tokens"),
        )


@dataclass(frozen=True)
class ZshForkConfig:
    shell_zsh_path: Path | str
    main_execve_wrapper_exe: Path | str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.shell_zsh_path, Path):
            object.__setattr__(self, "shell_zsh_path", Path(self.shell_zsh_path))
        if self.main_execve_wrapper_exe is not None and not isinstance(self.main_execve_wrapper_exe, Path):
            object.__setattr__(self, "main_execve_wrapper_exe", Path(self.main_execve_wrapper_exe))


@dataclass(frozen=True)
class UnifiedExecShellMode:
    zsh_fork_config: ZshForkConfig | None = None

    @classmethod
    def direct(cls) -> "UnifiedExecShellMode":
        return cls()

    @classmethod
    def zsh_fork(cls, config: ZshForkConfig) -> "UnifiedExecShellMode":
        if not isinstance(config, ZshForkConfig):
            raise TypeError("config must be ZshForkConfig")
        return cls(config)


@dataclass(frozen=True)
class ResolvedCommand:
    command: tuple[str, ...]
    shell_type: ShellType


def get_command(
    args: ExecCommandArgs,
    session_shell: Shell | None = None,
    shell_mode: UnifiedExecShellMode | None = None,
    allow_login_shell: bool = False,
) -> ResolvedCommand:
    if not isinstance(args, ExecCommandArgs):
        raise TypeError("args must be ExecCommandArgs")
    if session_shell is None:
        session_shell = default_user_shell()
    if shell_mode is None:
        shell_mode = UnifiedExecShellMode.direct()
    if not isinstance(session_shell, Shell):
        raise TypeError("session_shell must be Shell")
    if not isinstance(shell_mode, UnifiedExecShellMode):
        raise TypeError("shell_mode must be UnifiedExecShellMode")

    if args.login is True and not allow_login_shell:
        raise ValueError("login shell is disabled by config; omit `login` or set it to false.")
    use_login_shell = args.login if args.login is not None else allow_login_shell

    if shell_mode.zsh_fork_config is not None:
        return ResolvedCommand(
            (
                str(shell_mode.zsh_fork_config.shell_zsh_path),
                "-lc" if use_login_shell else "-c",
                args.cmd,
            ),
            ShellType.ZSH,
        )

    shell = get_shell_by_model_provided_path(args.shell) if args.shell is not None else session_shell
    return ResolvedCommand(tuple(shell.derive_exec_args(args.cmd, use_login_shell)), shell.shell_type)


def post_unified_exec_tool_use_payload(invocation: ToolInvocation, result: JsonValue) -> PostToolUsePayload | None:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if invocation.payload.type != "function":
        return None
    tool_input_method = getattr(result, "post_tool_use_input", None)
    tool_id_method = getattr(result, "post_tool_use_id", None)
    tool_response_method = getattr(result, "post_tool_use_response", None)
    if tool_input_method is None or tool_id_method is None or tool_response_method is None:
        return None
    tool_input = tool_input_method(invocation.payload)
    if tool_input is None:
        return None
    tool_use_id = tool_id_method(invocation.call_id)
    tool_response = tool_response_method(tool_use_id, invocation.payload)
    if tool_response is None:
        return None
    return PostToolUsePayload(HookToolName.bash(), tool_use_id, tool_input, tool_response)


@dataclass(frozen=True)
class ExecCommandHandlerOptions:
    allow_login_shell: bool = False
    exec_permission_approvals_enabled: bool = False
    include_environment_id: bool = False


class ExecCommandHandler:
    def __init__(self, options: ExecCommandHandlerOptions | None = None) -> None:
        self.options = options or ExecCommandHandlerOptions()

    def tool_name(self) -> ToolName:
        return ToolName.plain("exec_command")

    def spec(self) -> dict[str, JsonValue]:
        return create_exec_command_tool_with_environment_id(
            CommandToolOptions(self.options.allow_login_shell, self.options.exec_permission_approvals_enabled),
            self.options.include_environment_id,
        )

    def supports_parallel_tool_calls(self) -> bool:
        return True

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def pre_tool_use_payload(self, invocation: ToolInvocation) -> PreToolUsePayload | None:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            return None
        try:
            args = ExecCommandArgs.from_json(invocation.payload.arguments or "")
        except Exception:
            return None
        return PreToolUsePayload(HookToolName.bash(), {"command": args.cmd})

    def with_updated_hook_input(self, invocation: ToolInvocation, updated_input: JsonValue) -> ToolInvocation:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            raise ValueError("hook input rewrite received unsupported exec_command payload")
        arguments = _json_mapping(invocation.payload.arguments or "", "exec_command arguments")
        arguments["cmd"] = updated_hook_command(updated_input)
        return replace(invocation, payload=ToolPayload.function(json.dumps(arguments, ensure_ascii=False, separators=(",", ":"))))

    def post_tool_use_payload(self, invocation: ToolInvocation, result: JsonValue) -> PostToolUsePayload | None:
        return post_unified_exec_tool_use_payload(invocation, result)


class WriteStdinHandler:
    def tool_name(self) -> ToolName:
        return ToolName.plain("write_stdin")

    def spec(self) -> dict[str, JsonValue]:
        return create_write_stdin_tool()

    def matches_kind(self, payload: ToolPayload) -> bool:
        return isinstance(payload, ToolPayload) and payload.type == "function"

    def pre_tool_use_payload(self, _invocation: ToolInvocation) -> None:
        return None

    def post_tool_use_payload(self, invocation: ToolInvocation, result: JsonValue) -> PostToolUsePayload | None:
        return post_unified_exec_tool_use_payload(invocation, result)


def updated_hook_command(updated_input: JsonValue) -> str:
    data = _mapping(updated_input, "updated hook input")
    command = data.get("command")
    if not isinstance(command, str):
        raise TypeError("updated hook input command must be a string")
    return command


__all__ = [
    "DEFAULT_EXEC_YIELD_TIME_MS",
    "DEFAULT_WRITE_STDIN_YIELD_TIME_MS",
    "ExecCommandArgs",
    "ExecCommandEnvironmentArgs",
    "ExecCommandHandler",
    "ExecCommandHandlerOptions",
    "ResolvedCommand",
    "UnifiedExecShellMode",
    "WriteStdinArgs",
    "WriteStdinHandler",
    "ZshForkConfig",
    "get_command",
    "post_unified_exec_tool_use_payload",
    "updated_hook_command",
]
