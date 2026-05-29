"""Shared runtime helpers ported from ``core/src/tools/runtimes/mod.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from datetime import timedelta
from pathlib import Path
from typing import Any, Mapping

from pycodex.core.exec import (
    CancellationToken,
    DEFAULT_EXEC_COMMAND_TIMEOUT_MS,
    ExecCapturePolicy,
    ExecExpiration,
    is_likely_sandbox_denied,
)
from pycodex.core.sandbox_tags import SandboxType
from pycodex.core.shell import Shell, ShellType
from pycodex.core.hook_names import HookToolName
from pycodex.core.tool_sandboxing import ExecApprovalRequirement, PermissionRequestPayload, SandboxAttempt, ToolError
from pycodex.protocol import (
    AdditionalPermissionProfile,
    AskForApproval,
    CODEX_THREAD_ID_ENV_VAR,
    ExecToolCallOutput,
    FileChange,
    FileSystemSandboxPolicy,
    GranularApprovalConfig,
    NetworkSandboxPolicy,
    PermissionProfile,
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


class ShellRuntimeBackend(str, Enum):
    SHELL_COMMAND_CLASSIC = "shell_command_classic"
    SHELL_COMMAND_ZSH_FORK = "shell_command_zsh_fork"


class NetworkApprovalMode(str, Enum):
    IMMEDIATE = "immediate"
    DEFERRED = "deferred"


class DecisionSource(str, Enum):
    PREFIX_RULE = "prefix_rule"
    UNMATCHED_COMMAND_FALLBACK = "unmatched_command_fallback"


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
class GuardianNetworkAccessTrigger:
    call_id: str
    tool_name: str
    command: tuple[str, ...]
    cwd: Path
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None = None
    justification: str | None = None
    tty: bool | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str) or not self.call_id:
            raise TypeError("call_id must be a non-empty string")
        if not isinstance(self.tool_name, str) or not self.tool_name:
            raise TypeError("tool_name must be a non-empty string")
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")
        if self.tty is not None and not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool or None")


@dataclass(frozen=True)
class NetworkApprovalSpec:
    network: Any
    mode: NetworkApprovalMode
    trigger: GuardianNetworkAccessTrigger
    command: str

    def __post_init__(self) -> None:
        if not isinstance(self.mode, NetworkApprovalMode):
            object.__setattr__(self, "mode", NetworkApprovalMode(self.mode))
        if not isinstance(self.trigger, GuardianNetworkAccessTrigger):
            raise TypeError("trigger must be GuardianNetworkAccessTrigger")
        if not isinstance(self.command, str):
            raise TypeError("command must be a string")


@dataclass(frozen=True)
class ParsedShellCommand:
    program: str
    script: str
    login: bool

    def __post_init__(self) -> None:
        if not isinstance(self.program, str) or not self.program:
            raise TypeError("program must be a non-empty string")
        if not isinstance(self.script, str):
            raise TypeError("script must be a string")
        if not isinstance(self.login, bool):
            raise TypeError("login must be a bool")


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    output: str = ""
    duration: timedelta = timedelta(0)
    timed_out: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be an int")
        for field_name in ("stdout", "stderr", "output"):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f"{field_name} must be a string")
        if not isinstance(self.duration, timedelta):
            raise TypeError("duration must be a timedelta")
        if not isinstance(self.timed_out, bool):
            raise TypeError("timed_out must be a bool")


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


@dataclass(frozen=True)
class ShellRequest:
    command: tuple[str, ...]
    shell_type: ShellType | None
    hook_command: str
    cwd: Path
    timeout_ms: int | None
    cancellation_token: Any
    env: dict[str, str]
    explicit_env_overrides: dict[str, str]
    network: Any | None
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None
    justification: str | None
    exec_approval_requirement: ExecApprovalRequirement

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if self.shell_type is not None and not isinstance(self.shell_type, ShellType):
            object.__setattr__(self, "shell_type", ShellType(str(self.shell_type)))
        if not isinstance(self.hook_command, str):
            raise TypeError("hook_command must be a string")
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if self.timeout_ms is not None:
            if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
                raise TypeError("timeout_ms must be an int or None")
            if self.timeout_ms < 0:
                raise ValueError("timeout_ms must be non-negative")
        object.__setattr__(self, "env", _env_dict(self.env))
        object.__setattr__(self, "explicit_env_overrides", _env_dict(self.explicit_env_overrides))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")
        if not isinstance(self.exec_approval_requirement, ExecApprovalRequirement):
            raise TypeError("exec_approval_requirement must be ExecApprovalRequirement")


@dataclass(frozen=True)
class ShellApprovalKey:
    command: tuple[str, ...]
    cwd: Path
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", _string_tuple(self.command, "command"))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, "sandbox_permissions", SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and not isinstance(self.additional_permissions, AdditionalPermissionProfile):
            raise TypeError("additional_permissions must be AdditionalPermissionProfile or None")


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
    entries = file_system_policy.entries + additional_permissions.file_system.entries
    max_depth = additional_permissions.file_system.glob_scan_max_depth or file_system_policy.glob_scan_max_depth
    return FileSystemSandboxPolicy(file_system_policy.kind, entries, max_depth)


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


def extract_shell_script(command: tuple[str, ...] | list[str]) -> ParsedShellCommand:
    command_tuple = _string_tuple(command, "command")
    for index in range(max(len(command_tuple) - 2, 0)):
        program, flag, script = command_tuple[index : index + 3]
        if flag == "-c":
            return ParsedShellCommand(program, script, False)
        if flag == "-lc":
            return ParsedShellCommand(program, script, True)
    raise ToolRuntimeError(ToolError.rejected("unexpected shell command format for zsh-fork execution"))


def join_program_and_argv(program: str | Path, argv: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    argv_tuple = _string_tuple(argv, "argv")
    return (str(program), *argv_tuple[1:])


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


def shell_approval_keys(req: ShellRequest) -> tuple[ShellApprovalKey, ...]:
    if not isinstance(req, ShellRequest):
        raise TypeError("req must be ShellRequest")
    return (ShellApprovalKey(canonicalize_command_for_approval(req.command), req.cwd, req.sandbox_permissions, req.additional_permissions),)


def shell_permission_request_payload(req: ShellRequest) -> PermissionRequestPayload:
    if not isinstance(req, ShellRequest):
        raise TypeError("req must be ShellRequest")
    return PermissionRequestPayload.bash(req.hook_command, req.justification)


def shell_network_approval_spec(req: ShellRequest, *, call_id: str, tool_name: ToolName | str) -> NetworkApprovalSpec | None:
    if not isinstance(req, ShellRequest):
        raise TypeError("req must be ShellRequest")
    network = managed_network_for_runtime(req.network, req.sandbox_permissions)
    if network is None:
        return None
    return NetworkApprovalSpec(
        network,
        NetworkApprovalMode.IMMEDIATE,
        GuardianNetworkAccessTrigger(call_id, flat_tool_name(tool_name), req.command, req.cwd, req.sandbox_permissions, req.additional_permissions, req.justification, None),
        req.hook_command,
    )


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


def canonicalize_command_for_approval(command: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    return _string_tuple(command, "command")


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
) -> dict[str, str]:
    result = _env_dict(env)
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if sandbox_permissions.requires_escalated_permissions() and PROXY_ACTIVE_ENV_KEY in result:
        for key in PROXY_ENV_KEYS:
            result.pop(key, None)
        git_ssh_command = result.get(PROXY_GIT_SSH_COMMAND_ENV_KEY)
        if git_ssh_command is not None and git_ssh_command.startswith(CODEX_PROXY_GIT_SSH_COMMAND_MARKER):
            result.pop(PROXY_GIT_SSH_COMMAND_ENV_KEY, None)
    return result


def disable_powershell_profile_for_elevated_windows_sandbox(
    command: tuple[str, ...] | list[str],
    shell_type: ShellType | None,
    sandbox: SandboxType,
    windows_sandbox_level: WindowsSandboxLevel,
) -> tuple[str, ...]:
    command_tuple = _string_tuple(command, "command")
    if shell_type is not None and not isinstance(shell_type, ShellType):
        shell_type = ShellType(str(shell_type))
    if not isinstance(sandbox, SandboxType):
        sandbox = SandboxType(sandbox)
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))
    if (
        shell_type is not ShellType.POWERSHELL
        or sandbox is not SandboxType.WINDOWS_RESTRICTED_TOKEN
        or windows_sandbox_level is not WindowsSandboxLevel.ELEVATED
        or not command_tuple
    ):
        return command_tuple
    if any(arg.lower() == "-noprofile" for arg in command_tuple[1:]):
        return command_tuple
    return (command_tuple[0], "-NoProfile", *command_tuple[1:])


def maybe_wrap_shell_lc_with_snapshot(
    command: tuple[str, ...] | list[str],
    session_shell: Shell,
    cwd: str | Path,
    explicit_env_overrides: Mapping[str, str],
    env: Mapping[str, str],
    *,
    is_windows: bool = False,
) -> tuple[str, ...]:
    command_tuple = _string_tuple(command, "command")
    if not isinstance(session_shell, Shell):
        raise TypeError("session_shell must be Shell")
    if not isinstance(is_windows, bool):
        raise TypeError("is_windows must be a bool")
    if is_windows:
        return command_tuple
    snapshot = session_shell.shell_snapshot
    if snapshot is None:
        return command_tuple
    snapshot_path = getattr(snapshot, "path", None)
    snapshot_cwd = getattr(snapshot, "cwd", None)
    if not isinstance(snapshot_path, Path) or not isinstance(snapshot_cwd, Path):
        raise TypeError("shell snapshot must expose Path path and cwd")
    if not snapshot_path.exists():
        return command_tuple
    cwd_path = Path(cwd)
    if not _paths_match_after_normalization(snapshot_cwd, cwd_path):
        return command_tuple
    if len(command_tuple) < 3 or command_tuple[1] != "-lc":
        return command_tuple

    override_env = _env_dict(explicit_env_overrides)
    live_env = _env_dict(env)
    if CODEX_THREAD_ID_ENV_VAR in live_env:
        override_env[CODEX_THREAD_ID_ENV_VAR] = live_env[CODEX_THREAD_ID_ENV_VAR]
    override_captures, override_exports = build_override_exports(override_env)
    proxy_captures, proxy_exports = build_proxy_env_exports()
    captures = join_shell_blocks((override_captures, proxy_captures))
    exports = join_shell_blocks((override_exports, proxy_exports))
    original_shell = shell_single_quote(command_tuple[0])
    original_script = shell_single_quote(command_tuple[2])
    quoted_snapshot_path = shell_single_quote(str(snapshot_path))
    trailing_args = "".join(f" '{shell_single_quote(arg)}'" for arg in command_tuple[3:])
    if exports:
        rewritten_script = (
            f"{captures}\n\n"
            f"if . '{quoted_snapshot_path}' >/dev/null 2>&1; then :; fi\n\n"
            f"{exports}\n\n"
            f"exec '{original_shell}' -c '{original_script}'{trailing_args}"
        )
    else:
        rewritten_script = (
            f"if . '{quoted_snapshot_path}' >/dev/null 2>&1; then :; fi\n\n"
            f"exec '{original_shell}' -c '{original_script}'{trailing_args}"
        )
    return (str(session_shell.shell_path), "-c", rewritten_script)


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


def join_shell_blocks(blocks: tuple[str, ...] | list[str]) -> str:
    if not isinstance(blocks, (tuple, list)):
        raise TypeError("blocks must be a tuple or list")
    for block in blocks:
        if not isinstance(block, str):
            raise TypeError("blocks must contain strings")
    return "\n".join(block for block in blocks if block)


def is_valid_shell_variable_name(name: str) -> bool:
    if not isinstance(name, str):
        raise TypeError("name must be a string")
    if not name:
        return False
    first = name[0]
    if first != "_" and not (first.isascii() and first.isalpha()):
        return False
    return all(character == "_" or (character.isascii() and character.isalnum()) for character in name[1:])


def shell_single_quote(input: str) -> str:
    if not isinstance(input, str):
        raise TypeError("input must be a string")
    return input.replace("'", "'\"'\"'")


def _paths_match_after_normalization(left: Path, right: Path) -> bool:
    try:
        return left.resolve() == right.resolve()
    except OSError:
        return left.absolute() == right.absolute()


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


__all__ = [
    "CODEX_PROXY_GIT_SSH_COMMAND_MARKER",
    "PROXY_ACTIVE_ENV_KEY",
    "PROXY_ENV_KEYS",
    "PROXY_GIT_SSH_COMMAND_ENV_KEY",
    "ApplyPatchApprovalKey",
    "ApplyPatchFileSystemSandboxContext",
    "ApplyPatchRequest",
    "ApplyPatchRuntimeOutput",
    "DecisionSource",
    "ExecResult",
    "GuardianNetworkAccessTrigger",
    "NetworkApprovalMode",
    "NetworkApprovalSpec",
    "PROMPT_CONFLICT_REASON",
    "ParsedShellCommand",
    "REJECT_RULES_APPROVAL_REASON",
    "REJECT_SANDBOX_APPROVAL_REASON",
    "SandboxCommand",
    "ShellApprovalKey",
    "ShellRequest",
    "ShellRuntimeBackend",
    "ToolRuntimeError",
    "UnifiedExecApprovalKey",
    "UnifiedExecOptions",
    "UnifiedExecRequest",
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
    "disable_powershell_profile_for_elevated_windows_sandbox",
    "exec_env_for_sandbox_permissions",
    "execve_prompt_is_rejected_by_policy",
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
    "shell_single_quote",
    "shell_approval_keys",
    "shell_network_approval_spec",
    "shell_permission_request_payload",
    "unified_exec_approval_keys",
    "unified_exec_network_approval_spec",
    "unified_exec_options",
    "unified_exec_permission_request_payload",
    "unified_exec_sandbox_cwd",
]
