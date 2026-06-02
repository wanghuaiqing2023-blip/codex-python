"""Unified exec tool handler facades ported from Codex core.

This module mirrors the argument, command-resolution, spec, hook payload, and
lightweight local execution behavior from
``core/src/tools/handlers/unified_exec``. Full PTY/session process management
is still delegated to a unified exec manager when available.
"""

from __future__ import annotations

import json
import inspect
import shlex
import subprocess
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pycodex.core.exec import DEFAULT_EXEC_COMMAND_TIMEOUT_MS
from pycodex.core.exec_env import create_env
from pycodex.core.unified_exec import (
    DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    MAX_YIELD_TIME_MS,
    MIN_EMPTY_YIELD_TIME_MS,
    MIN_YIELD_TIME_MS,
    UnifiedExecError,
    clamp_yield_time,
    generate_chunk_id,
    resolve_write_stdin_yield_time,
    should_emit_terminal_interaction,
    terminal_interaction_process_id,
)
from pycodex.core.apply_patch import (
    apply_patch_action_to_disk,
    maybe_parse_apply_patch_verified,
)
from pycodex.core.features import Feature
from pycodex.core.handler_utils import (
    apply_granted_turn_permissions,
    implicit_granted_permissions,
    normalize_and_validate_additional_permissions,
    resolve_tool_environment,
)
from pycodex.core.hook_names import HookToolName
from pycodex.core.shell import Shell, ShellType, default_user_shell, get_shell_by_model_provided_path
from pycodex.core.string_utils import approx_token_count
from pycodex.core.tool_context import ExecCommandToolOutput
from pycodex.core.shell_spec import (
    CommandToolOptions,
    create_exec_command_tool_with_environment_id,
    create_write_stdin_tool,
)
from pycodex.core.tool_context import ToolPayload
from pycodex.core.tool_router import FunctionCallError
from pycodex.core.tool_registry import PostToolUsePayload, PreToolUsePayload, ToolInvocation
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    EventMsg,
    GranularApprovalConfig,
    SandboxPermissions,
    ShellEnvironmentPolicy,
    TerminalInteractionEvent,
    ThreadId,
    ToolName,
    TruncationPolicyConfig,
)

JsonValue = Any

DEFAULT_EXEC_YIELD_TIME_MS = 10_000
DEFAULT_WRITE_STDIN_YIELD_TIME_MS = 250
I32_MIN = -(2**31)
I32_MAX = 2**31 - 1
U64_MAX = 2**64 - 1
USIZE_MAX = 2**64 - 1


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


def _ensure_i32(value: int, label: str) -> None:
    if value < I32_MIN or value > I32_MAX:
        raise ValueError(f"{label} must fit in i32")


def _ensure_u64(value: int, label: str) -> None:
    if value < 0 or value > U64_MAX:
        raise ValueError(f"{label} must fit in u64")


def _ensure_usize(value: int, label: str) -> None:
    if value < 0 or value > USIZE_MAX:
        raise ValueError(f"{label} must fit in usize")


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
        _ensure_u64(self.yield_time_ms, "yield_time_ms")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer")
        if self.max_output_tokens is not None:
            _ensure_usize(self.max_output_tokens, "max_output_tokens")
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
        _ensure_i32(self.session_id, "session_id")
        if not isinstance(self.chars, str):
            raise TypeError("chars must be a string")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        _ensure_u64(self.yield_time_ms, "yield_time_ms")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer")
        if self.max_output_tokens is not None:
            _ensure_usize(self.max_output_tokens, "max_output_tokens")

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
class WriteStdinRequest:
    process_id: int
    input: str
    yield_time_ms: int
    max_output_tokens: int | None
    truncation_policy: TruncationPolicyConfig

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an integer")
        _ensure_i32(self.process_id, "process_id")
        if not isinstance(self.input, str):
            raise TypeError("input must be a string")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        _ensure_u64(self.yield_time_ms, "yield_time_ms")
        if self.max_output_tokens is not None:
            if isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int):
                raise TypeError("max_output_tokens must be an integer")
            _ensure_usize(self.max_output_tokens, "max_output_tokens")
        if not isinstance(self.truncation_policy, TruncationPolicyConfig):
            raise TypeError("truncation_policy must be TruncationPolicyConfig")


@dataclass(frozen=True)
class ExecCommandRequest:
    call_id: str
    command: tuple[str, ...]
    shell_type: ShellType
    hook_command: str
    process_id: int
    yield_time_ms: int
    max_output_tokens: int | None
    cwd: Path
    sandbox_cwd: Path
    environment: Any
    network: Any
    tty: bool
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None
    additional_permissions_preapproved: bool
    justification: str | None
    prefix_rule: tuple[str, ...] | None
    truncation_policy: TruncationPolicyConfig

    def __post_init__(self) -> None:
        command = tuple(self.command)
        if not command or not all(isinstance(part, str) for part in command):
            raise TypeError("command must be a non-empty tuple of strings")
        object.__setattr__(self, "command", command)
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.shell_type, ShellType):
            object.__setattr__(self, "shell_type", ShellType(self.shell_type))
        if not isinstance(self.hook_command, str):
            raise TypeError("hook_command must be a string")
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an integer")
        _ensure_i32(self.process_id, "process_id")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        _ensure_u64(self.yield_time_ms, "yield_time_ms")
        if self.max_output_tokens is not None:
            if isinstance(self.max_output_tokens, bool) or not isinstance(self.max_output_tokens, int):
                raise TypeError("max_output_tokens must be an integer")
            _ensure_usize(self.max_output_tokens, "max_output_tokens")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.sandbox_cwd, Path):
            object.__setattr__(self, "sandbox_cwd", Path(self.sandbox_cwd))
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(str(self.sandbox_permissions)))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile")
        if not isinstance(self.additional_permissions_preapproved, bool):
            raise TypeError("additional_permissions_preapproved must be a bool")
        if self.prefix_rule is not None and not isinstance(self.prefix_rule, tuple):
            object.__setattr__(self, "prefix_rule", tuple(self.prefix_rule))
        if not isinstance(self.truncation_policy, TruncationPolicyConfig):
            raise TypeError("truncation_policy must be TruncationPolicyConfig")


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


@dataclass(frozen=True)
class ResolvedExecCommandInvocation:
    args: ExecCommandArgs
    environment_args: ExecCommandEnvironmentArgs
    turn_environment: Any
    cwd: Path
    resolved_command: ResolvedCommand

    def __post_init__(self) -> None:
        if not isinstance(self.args, ExecCommandArgs):
            raise TypeError("args must be ExecCommandArgs")
        if not isinstance(self.environment_args, ExecCommandEnvironmentArgs):
            raise TypeError("environment_args must be ExecCommandEnvironmentArgs")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.resolved_command, ResolvedCommand):
            raise TypeError("resolved_command must be ResolvedCommand")


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


def resolve_exec_command_invocation(
    invocation: ToolInvocation,
    *,
    session_shell: Shell | None = None,
    shell_mode: UnifiedExecShellMode | None = None,
    allow_login_shell: bool = False,
) -> ResolvedExecCommandInvocation:
    if not isinstance(invocation, ToolInvocation):
        raise TypeError("invocation must be ToolInvocation")
    if invocation.payload.type != "function":
        raise ValueError("exec_command handler received unsupported payload")
    arguments = invocation.payload.arguments or ""
    environment_args = ExecCommandEnvironmentArgs.from_json(arguments)
    turn_environment = resolve_tool_environment(invocation.turn, environment_args.environment_id)
    if turn_environment is None:
        raise ValueError("unified exec is unavailable in this session")
    base_cwd = Path(getattr(turn_environment, "cwd"))
    cwd = base_cwd
    if environment_args.workdir:
        cwd = base_cwd / environment_args.workdir
    args = ExecCommandArgs.from_json(arguments)
    resolved_command = get_command(
        args,
        session_shell=session_shell,
        shell_mode=shell_mode,
        allow_login_shell=allow_login_shell,
    )
    return ResolvedExecCommandInvocation(
        args=args,
        environment_args=environment_args,
        turn_environment=turn_environment,
        cwd=cwd,
        resolved_command=resolved_command,
    )


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

    def handle(self, invocation: ToolInvocation) -> ExecCommandToolOutput:
        try:
            resolved = resolve_exec_command_invocation(
                invocation,
                session_shell=_invocation_session_shell(invocation),
                allow_login_shell=_invocation_allow_login_shell(invocation, self.options.allow_login_shell),
            )
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise _parse_or_validation_error(error) from error
        manager = _invocation_optional_unified_exec_manager(invocation)
        exec_command = getattr(manager, "exec_command", None) if manager is not None else None
        if callable(exec_command):
            return self._handle_with_unified_exec_manager(invocation, resolved, exec_command)
        start = time.monotonic()
        intercepted = intercept_exec_apply_patch(
            resolved.resolved_command.command,
            resolved.cwd,
        )
        if intercepted is not None:
            return ExecCommandToolOutput(
                event_call_id="",
                chunk_id="",
                wall_time_seconds=0.0,
                raw_output=intercepted.encode("utf-8"),
                truncation_policy=_invocation_truncation_policy(invocation),
                max_output_tokens=resolved.args.max_output_tokens,
                process_id=None,
                exit_code=None,
                hook_command=None,
            )
        try:
            completed = subprocess.run(
                resolved.resolved_command.command,
                cwd=resolved.cwd,
                env=_invocation_exec_env(invocation),
                capture_output=True,
                timeout=DEFAULT_EXEC_COMMAND_TIMEOUT_MS / 1000,
                check=False,
            )
            raw_output = completed.stdout + completed.stderr
            exit_code = completed.returncode
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or b""
            stderr = error.stderr or b""
            if isinstance(stdout, str):
                stdout = stdout.encode()
            if isinstance(stderr, str):
                stderr = stderr.encode()
            raw_output = stdout + stderr
            exit_code = 124
        except OSError as error:
            raise FunctionCallError.respond_to_model(f"failed to execute command: {error}") from error
        return ExecCommandToolOutput(
            event_call_id=invocation.call_id,
            chunk_id="",
            wall_time_seconds=time.monotonic() - start,
            raw_output=raw_output,
            truncation_policy=_invocation_truncation_policy(invocation),
            max_output_tokens=resolved.args.max_output_tokens,
            process_id=None,
            exit_code=exit_code,
            original_token_count=approx_token_count(raw_output.decode("utf-8", errors="replace")),
            hook_command=resolved.args.cmd,
        )

    async def _handle_with_unified_exec_manager(
        self,
        invocation: ToolInvocation,
        resolved: ResolvedExecCommandInvocation,
        exec_command: Any,
    ) -> ExecCommandToolOutput:
        manager = _invocation_optional_unified_exec_manager(invocation)
        turn = invocation.turn
        approval_policy = _invocation_approval_policy(invocation)
        process_id = await _allocate_unified_exec_process_id(manager)
        requested_additional_permissions = resolved.args.additional_permissions
        effective_additional_permissions = await apply_granted_turn_permissions(
            _session_with_permission_accessors(invocation.session),
            resolved.cwd,
            resolved.args.sandbox_permissions,
            resolved.args.additional_permissions,
        )
        additional_permissions_allowed = (
            _invocation_feature_enabled(invocation, Feature.EXEC_PERMISSION_APPROVALS)
            or (
                _invocation_feature_enabled(invocation, Feature.REQUEST_PERMISSIONS_TOOL)
                and effective_additional_permissions.permissions_preapproved
            )
        )

        if (
            effective_additional_permissions.sandbox_permissions.requests_sandbox_override()
            and not effective_additional_permissions.permissions_preapproved
            and approval_policy is not AskForApproval.ON_REQUEST
        ):
            await _release_unified_exec_process_id(manager, process_id)
            raise FunctionCallError.respond_to_model(
                f"approval policy is {approval_policy!r}; reject command - "
                f"you cannot ask for escalated permissions if the approval policy is {approval_policy!r}"
            )

        try:
            normalized_additional_permissions = implicit_granted_permissions(
                resolved.args.sandbox_permissions,
                requested_additional_permissions,
                effective_additional_permissions,
            )
            if normalized_additional_permissions is None:
                normalized_additional_permissions = normalize_and_validate_additional_permissions(
                    additional_permissions_allowed,
                    approval_policy,
                    effective_additional_permissions.sandbox_permissions,
                    effective_additional_permissions.additional_permissions,
                    effective_additional_permissions.permissions_preapproved,
                    resolved.cwd,
                )
        except (TypeError, ValueError) as error:
            await _release_unified_exec_process_id(manager, process_id)
            raise FunctionCallError.respond_to_model(str(error)) from error

        intercepted = intercept_exec_apply_patch(
            resolved.resolved_command.command,
            resolved.cwd,
        )
        if intercepted is not None:
            await _release_unified_exec_process_id(manager, process_id)
            return ExecCommandToolOutput(
                event_call_id="",
                chunk_id="",
                wall_time_seconds=0.0,
                raw_output=intercepted.encode("utf-8"),
                truncation_policy=_invocation_truncation_policy(invocation),
                max_output_tokens=resolved.args.max_output_tokens,
                process_id=None,
                exit_code=None,
                hook_command=None,
            )
        request = ExecCommandRequest(
            call_id=invocation.call_id,
            command=resolved.resolved_command.command,
            shell_type=resolved.resolved_command.shell_type,
            hook_command=resolved.args.cmd,
            process_id=process_id,
            yield_time_ms=resolved.args.yield_time_ms,
            max_output_tokens=resolved.args.max_output_tokens,
            cwd=resolved.cwd,
            sandbox_cwd=Path(getattr(resolved.turn_environment, "cwd")),
            environment=getattr(resolved.turn_environment, "environment", None),
            network=getattr(turn, "network", None),
            tty=resolved.args.tty,
            sandbox_permissions=effective_additional_permissions.sandbox_permissions,
            additional_permissions=normalized_additional_permissions,
            additional_permissions_preapproved=effective_additional_permissions.permissions_preapproved,
            justification=resolved.args.justification,
            prefix_rule=resolved.args.prefix_rule,
            truncation_policy=_invocation_truncation_policy(invocation),
        )
        try:
            result = exec_command(request)
            if inspect.isawaitable(result):
                result = await result
            return result
        except UnifiedExecError as error:
            if error.kind == UnifiedExecError.SANDBOX_DENIED and error.output is not None:
                return _sandbox_denied_tool_output(
                    error,
                    invocation,
                    resolved.args,
                    _invocation_truncation_policy(invocation),
                )
            await _release_unified_exec_process_id(manager, process_id)
            command_for_display = shlex.join(resolved.resolved_command.command)
            raise FunctionCallError.respond_to_model(
                f"exec_command failed for `{command_for_display}`: {error}"
            ) from error
        except Exception as error:
            await _release_unified_exec_process_id(manager, process_id)
            command_for_display = shlex.join(resolved.resolved_command.command)
            raise FunctionCallError.respond_to_model(
                f"exec_command failed for `{command_for_display}`: {error}"
            ) from error


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

    async def handle(self, invocation: ToolInvocation) -> JsonValue:
        if not isinstance(invocation, ToolInvocation):
            raise TypeError("invocation must be ToolInvocation")
        if invocation.payload.type != "function":
            raise FunctionCallError.respond_to_model("write_stdin handler received unsupported payload")
        try:
            args = WriteStdinArgs.from_json(invocation.payload.arguments or "")
        except (TypeError, ValueError, json.JSONDecodeError) as error:
            raise _parse_or_validation_error(error) from error
        manager = _invocation_unified_exec_manager(invocation)
        write_stdin = getattr(manager, "write_stdin", None)
        if not callable(write_stdin):
            raise FunctionCallError.respond_to_model("write_stdin failed: unified exec manager unavailable")
        request = WriteStdinRequest(
            process_id=args.session_id,
            input=args.chars,
            yield_time_ms=resolve_write_stdin_yield_time(args.chars, args.yield_time_ms),
            max_output_tokens=args.max_output_tokens,
            truncation_policy=_invocation_truncation_policy(invocation),
        )
        try:
            result = write_stdin(request)
            if inspect.isawaitable(result):
                result = await result
            await _send_write_stdin_terminal_interaction(invocation, args, result)
            return result
        except Exception as error:
            raise FunctionCallError.respond_to_model(f"write_stdin failed: {error}") from error


def updated_hook_command(updated_input: JsonValue) -> str:
    data = _mapping(updated_input, "updated hook input")
    command = data.get("command")
    if not isinstance(command, str):
        raise TypeError("updated hook input command must be a string")
    return command


def _sandbox_denied_tool_output(
    error: UnifiedExecError,
    invocation: ToolInvocation,
    args: ExecCommandArgs,
    truncation_policy: TruncationPolicyConfig,
) -> ExecCommandToolOutput:
    output = error.output
    if output is None:
        raise TypeError("sandbox denied error must carry output")
    aggregated_output = getattr(output, "aggregated_output", None)
    raw_text = getattr(aggregated_output, "text", None)
    if raw_text is None:
        raw_text = getattr(output, "raw_output", b"")
        if isinstance(raw_text, bytes):
            raw_text = raw_text.decode("utf-8", errors="replace")
    if not isinstance(raw_text, str):
        raw_text = str(raw_text)
    duration = getattr(output, "duration", None)
    wall_time_seconds = duration.total_seconds() if hasattr(duration, "total_seconds") else 0.0
    exit_code = getattr(output, "exit_code", None)
    if exit_code is not None and (isinstance(exit_code, bool) or not isinstance(exit_code, int)):
        raise TypeError("sandbox denied output exit_code must be an integer or None")
    return ExecCommandToolOutput(
        event_call_id=invocation.call_id,
        chunk_id=generate_chunk_id(),
        wall_time_seconds=wall_time_seconds,
        raw_output=raw_text.encode("utf-8"),
        truncation_policy=truncation_policy,
        max_output_tokens=args.max_output_tokens,
        process_id=None,
        exit_code=exit_code,
        original_token_count=approx_token_count(raw_text),
        hook_command=args.cmd,
    )


def _parse_or_validation_error(error: BaseException) -> FunctionCallError:
    return FunctionCallError.respond_to_model(f"failed to parse function arguments: {error}")


def intercept_exec_apply_patch(
    command: tuple[str, ...] | list[str],
    cwd: Path | str,
) -> str | None:
    result = maybe_parse_apply_patch_verified(tuple(command), Path(cwd))
    if result.type == "body":
        assert result.body is not None
        return apply_patch_action_to_disk(result.body)
    if result.type == "correctness_error":
        raise FunctionCallError.respond_to_model(
            f"apply_patch verification failed: {result.error}"
        )
    if result.type == "shell_parse_error":
        return None
    if result.type == "not_apply_patch":
        return None
    raise FunctionCallError.respond_to_model("apply_patch handler received invalid patch input")


def _invocation_session_shell(invocation: ToolInvocation) -> Shell | None:
    session = getattr(invocation, "session", None)
    user_shell = getattr(session, "user_shell", None)
    if callable(user_shell):
        shell = user_shell()
        if shell is not None and not isinstance(shell, Shell):
            raise TypeError("session.user_shell() must return Shell or None")
        return shell
    return None


def _invocation_allow_login_shell(invocation: ToolInvocation, fallback: bool) -> bool:
    turn = getattr(invocation, "turn", None)
    config = getattr(turn, "config", None)
    permissions = getattr(config, "permissions", None)
    value = getattr(permissions, "allow_login_shell", None)
    if value is None:
        return fallback
    if not isinstance(value, bool):
        raise TypeError("turn.config.permissions.allow_login_shell must be a bool")
    return value


def _invocation_truncation_policy(invocation: ToolInvocation) -> TruncationPolicyConfig:
    turn = getattr(invocation, "turn", None)
    policy = getattr(turn, "truncation_policy", None)
    if policy is None:
        return TruncationPolicyConfig.tokens(10_000)
    if not isinstance(policy, TruncationPolicyConfig):
        raise TypeError("turn.truncation_policy must be TruncationPolicyConfig")
    return policy


def _invocation_exec_env(invocation: ToolInvocation) -> dict[str, str]:
    policy = _invocation_shell_environment_policy(invocation)
    thread_id = _invocation_thread_id(invocation)
    return create_env(policy, thread_id)


def _invocation_shell_environment_policy(invocation: ToolInvocation) -> ShellEnvironmentPolicy:
    turn = getattr(invocation, "turn", None)
    policy = getattr(turn, "shell_environment_policy", None)
    if policy is None:
        return ShellEnvironmentPolicy.default()
    if not isinstance(policy, ShellEnvironmentPolicy):
        raise TypeError("turn.shell_environment_policy must be ShellEnvironmentPolicy")
    return policy


def _invocation_thread_id(invocation: ToolInvocation) -> ThreadId | None:
    session = getattr(invocation, "session", None)
    for value in (
        getattr(session, "conversation_id", None),
        getattr(session, "thread_id", None),
        getattr(invocation.turn, "thread_id", None),
    ):
        if value is None:
            continue
        if isinstance(value, ThreadId):
            return value
        raise TypeError("thread id for exec environment must be ThreadId")
    return None


def _invocation_unified_exec_manager(invocation: ToolInvocation) -> Any:
    session = getattr(invocation, "session", None)
    services = getattr(session, "services", None)
    manager = getattr(services, "unified_exec_manager", None)
    if manager is None:
        raise FunctionCallError.respond_to_model("write_stdin failed: unified exec manager unavailable")
    return manager


def _invocation_optional_unified_exec_manager(invocation: ToolInvocation) -> Any:
    session = getattr(invocation, "session", None)
    services = getattr(session, "services", None)
    return getattr(services, "unified_exec_manager", None)


async def _allocate_unified_exec_process_id(manager: Any) -> int:
    allocate = getattr(manager, "allocate_process_id", None)
    if not callable(allocate):
        return 0
    process_id = allocate()
    if inspect.isawaitable(process_id):
        process_id = await process_id
    if isinstance(process_id, bool) or not isinstance(process_id, int):
        raise TypeError("allocate_process_id must return an integer")
    _ensure_i32(process_id, "process_id")
    return process_id


async def _release_unified_exec_process_id(manager: Any, process_id: int) -> None:
    release = getattr(manager, "release_process_id", None)
    if not callable(release):
        return
    result = release(process_id)
    if inspect.isawaitable(result):
        await result


def _invocation_additional_permissions_preapproved(invocation: ToolInvocation) -> bool:
    for owner in (getattr(invocation, "turn", None), getattr(invocation, "session", None)):
        if owner is None:
            continue
        value = getattr(owner, "additional_permissions_preapproved", None)
        if value is None:
            value = getattr(owner, "permissions_preapproved", None)
        if value is None:
            continue
        if not isinstance(value, bool):
            raise TypeError("additional_permissions_preapproved must be a bool")
        return value
    return False


def _invocation_approval_policy(invocation: ToolInvocation) -> AskForApproval | GranularApprovalConfig:
    turn = getattr(invocation, "turn", None)
    value = getattr(turn, "approval_policy", AskForApproval.ON_REQUEST)
    method = getattr(value, "value", None)
    if callable(method):
        value = method()
    if isinstance(value, GranularApprovalConfig):
        return value
    if not isinstance(value, AskForApproval):
        value = AskForApproval.parse(str(value))
    return value


def _invocation_feature_enabled(invocation: ToolInvocation, feature: Feature) -> bool:
    session = getattr(invocation, "session", None)
    features = getattr(session, "features", None)
    if callable(features):
        features = features()
    enabled = getattr(features, "enabled", None)
    if not callable(enabled):
        return False
    result = enabled(feature)
    if not isinstance(result, bool):
        raise TypeError("features.enabled() must return a bool")
    return result


class _PermissionAccessorSessionProxy:
    def __init__(self, session: Any) -> None:
        self._session = session

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def granted_session_permissions(self) -> AdditionalPermissionProfile | None:
        reader = getattr(self._session, "granted_session_permissions", None)
        if callable(reader):
            result = reader()
            if inspect.isawaitable(result):
                result = await result
            return result
        return None

    async def granted_turn_permissions(self) -> AdditionalPermissionProfile | None:
        reader = getattr(self._session, "granted_turn_permissions", None)
        if callable(reader):
            result = reader()
            if inspect.isawaitable(result):
                result = await result
            return result
        return None


def _session_with_permission_accessors(session: Any) -> Any:
    if callable(getattr(session, "granted_session_permissions", None)) and callable(
        getattr(session, "granted_turn_permissions", None)
    ):
        return session
    return _PermissionAccessorSessionProxy(session)


async def _send_write_stdin_terminal_interaction(
    invocation: ToolInvocation,
    args: WriteStdinArgs,
    result: JsonValue,
) -> None:
    process_id = getattr(result, "process_id", None)
    if not should_emit_terminal_interaction(args.chars, process_id):
        return
    session = getattr(invocation, "session", None)
    send_event = getattr(session, "send_event", None)
    if not callable(send_event):
        return
    event_call_id = getattr(result, "event_call_id", invocation.call_id)
    event = EventMsg.with_payload(
        "terminal_interaction",
        TerminalInteractionEvent(
            call_id=str(event_call_id),
            process_id=str(terminal_interaction_process_id(process_id, args.session_id)),
            stdin=args.chars,
        ),
    )
    sent = send_event(getattr(invocation, "turn", None), event)
    if inspect.isawaitable(sent):
        await sent


__all__ = [
    "DEFAULT_EXEC_YIELD_TIME_MS",
    "DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS",
    "DEFAULT_WRITE_STDIN_YIELD_TIME_MS",
    "ExecCommandArgs",
    "ExecCommandEnvironmentArgs",
    "ExecCommandHandler",
    "ExecCommandHandlerOptions",
    "ExecCommandRequest",
    "MAX_YIELD_TIME_MS",
    "MIN_EMPTY_YIELD_TIME_MS",
    "MIN_YIELD_TIME_MS",
    "ResolvedExecCommandInvocation",
    "ResolvedCommand",
    "UnifiedExecShellMode",
    "WriteStdinArgs",
    "WriteStdinHandler",
    "WriteStdinRequest",
    "ZshForkConfig",
    "clamp_yield_time",
    "get_command",
    "intercept_exec_apply_patch",
    "post_unified_exec_tool_use_payload",
    "resolve_exec_command_invocation",
    "resolve_write_stdin_yield_time",
    "updated_hook_command",
]
