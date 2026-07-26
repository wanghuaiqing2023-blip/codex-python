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
if not hasattr(socket, 'SCM_RIGHTS'):
    socket.SCM_RIGHTS = 1
if not hasattr(socket, 'CMSG_SPACE'):
    socket.CMSG_SPACE = lambda length: length
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
PROXY_ACTIVE_ENV_KEY = 'CODEX_PROXY_ACTIVE'
PROXY_ENV_KEYS = (PROXY_ACTIVE_ENV_KEY, 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY', 'http_proxy', 'https_proxy', 'all_proxy', 'no_proxy')
PROXY_GIT_SSH_COMMAND_ENV_KEY = 'GIT_SSH_COMMAND'
CODEX_PROXY_GIT_SSH_COMMAND_MARKER = 'codex-proxy-git-ssh'
ESCALATE_SOCKET_ENV_VAR = 'CODEX_ESCALATE_SOCKET'
EXEC_WRAPPER_ENV_VAR = 'EXEC_WRAPPER'
SHELL_ESCALATE_HANDSHAKE_MESSAGE = b'\x00'
SHELL_SOCKET_MAX_FDS_PER_MESSAGE = 16
SHELL_SOCKET_LENGTH_PREFIX_SIZE = 4
SHELL_SOCKET_STREAM_MAX_PAYLOAD = 8192
from .. import InterceptedExecPolicyContext, InterceptedExecPolicyEvaluation, SandboxCommand, ToolRuntimeError, _env_dict, _maybe_await, _maybe_await_runtime, _path_as_posix_string, _session_env, _string_tuple, build_override_exports, build_proxy_env_exports, canonicalize_command_for_approval, decision_driven_by_policy, exec_env_for_sandbox_permissions, exec_result_from_tool_output, execve_prompt_is_rejected_by_policy, flat_tool_name, join_program_and_argv, map_exec_result
from ..apply_patch import approval_sandbox_permissions, effective_permission_profile
from ..unified_exec import UnifiedExecRequest, managed_network_for_runtime
from .. import ESCALATE_SOCKET_ENV_VAR, EXEC_WRAPPER_ENV_VAR, PROXY_ACTIVE_ENV_KEY, SHELL_ESCALATE_HANDSHAKE_MESSAGE, SHELL_SOCKET_LENGTH_PREFIX_SIZE, SHELL_SOCKET_MAX_FDS_PER_MESSAGE, SHELL_SOCKET_STREAM_MAX_PAYLOAD, SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS

class ShellRuntimeBackend(str, Enum):
    SHELL_COMMAND_CLASSIC = 'shell_command_classic'
    SHELL_COMMAND_ZSH_FORK = 'shell_command_zsh_fork'

@dataclass(frozen=True)
class ShellEscalationPolicyPlan:
    decision: Any
    decision_source: DecisionSource
    needs_escalation: bool
    escalation_execution: 'ShellEscalationExecution'
    prompt_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.decision_source, DecisionSource):
            object.__setattr__(self, 'decision_source', DecisionSource(self.decision_source))
        if not isinstance(self.needs_escalation, bool):
            raise TypeError('needs_escalation must be a bool')
        if not isinstance(self.escalation_execution, ShellEscalationExecution):
            raise TypeError('escalation_execution must be ShellEscalationExecution')
        if self.prompt_permissions is not None and (not isinstance(self.prompt_permissions, AdditionalPermissionProfile)):
            raise TypeError('prompt_permissions must be AdditionalPermissionProfile or None')

@dataclass(frozen=True)
class ShellEscalationExecution:
    type: str
    permission_profile: Any | None = None

    def __post_init__(self) -> None:
        if self.type not in {'turn_default', 'unsandboxed', 'permissions'}:
            raise ValueError(f'unknown shell escalation execution type: {self.type}')
        if self.type == 'permissions':
            if self.permission_profile is None:
                raise TypeError('permissions escalation requires a permission profile')
        elif self.permission_profile is not None:
            raise ValueError(f'{self.type} escalation must not include a permission profile')

    @classmethod
    def turn_default(cls) -> 'ShellEscalationExecution':
        return cls('turn_default')

    @classmethod
    def unsandboxed(cls) -> 'ShellEscalationExecution':
        return cls('unsandboxed')

    @classmethod
    def permissions(cls, permission_profile: Any) -> 'ShellEscalationExecution':
        return cls('permissions', permission_profile)

@dataclass(frozen=True)
class ShellEscalationDecision:
    type: str
    execution: ShellEscalationExecution | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {'run', 'escalate', 'deny', 'prompt'}:
            raise ValueError(f'unknown shell escalation decision type: {self.type}')
        if self.type == 'escalate':
            if not isinstance(self.execution, ShellEscalationExecution):
                raise TypeError('escalate decision requires ShellEscalationExecution')
            if self.reason is not None:
                raise ValueError('escalate decision must not include reason')
        elif self.type == 'prompt':
            if self.execution is not None:
                raise ValueError('prompt decision must not include execution')
            if self.reason is not None and (not isinstance(self.reason, str)):
                raise TypeError('reason must be a string or None')
        elif self.type == 'deny':
            if self.execution is not None:
                raise ValueError('deny decision must not include execution')
            if self.reason is not None and (not isinstance(self.reason, str)):
                raise TypeError('reason must be a string or None')
        elif self.execution is not None or self.reason is not None:
            raise ValueError('run decision must not include execution or reason')

    @classmethod
    def run(cls) -> 'ShellEscalationDecision':
        return cls('run')

    @classmethod
    def escalate(cls, execution: ShellEscalationExecution) -> 'ShellEscalationDecision':
        return cls('escalate', execution=execution)

    @classmethod
    def prompt(cls, reason: str | None=None) -> 'ShellEscalationDecision':
        return cls('prompt', reason=reason)

    @classmethod
    def deny(cls, reason: str | None=None) -> 'ShellEscalationDecision':
        return cls('deny', reason=reason)

@dataclass(frozen=True)
class ShellPrepareSandboxedExecParams:
    command: tuple[str, ...]
    workdir: Path
    env: dict[str, str]
    permission_profile: PermissionProfile
    additional_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'command', _string_tuple(self.command, 'command'))
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, 'workdir', Path(self.workdir))
        object.__setattr__(self, 'env', _env_dict(self.env))
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError('permission_profile must be PermissionProfile')
        if self.additional_permissions is not None and (not isinstance(self.additional_permissions, AdditionalPermissionProfile)):
            raise TypeError('additional_permissions must be AdditionalPermissionProfile or None')

@dataclass(frozen=True)
class ShellPrepareSandboxedExecContext:
    sandbox_policy_cwd: Path
    network: Any | None = None
    codex_linux_sandbox_exe: Path | None = None
    use_legacy_landlock: bool = False
    windows_sandbox_level: WindowsSandboxLevel = WindowsSandboxLevel.DISABLED
    windows_sandbox_private_desktop: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.sandbox_policy_cwd, Path):
            object.__setattr__(self, 'sandbox_policy_cwd', Path(self.sandbox_policy_cwd))
        if self.codex_linux_sandbox_exe is not None and (not isinstance(self.codex_linux_sandbox_exe, Path)):
            object.__setattr__(self, 'codex_linux_sandbox_exe', Path(self.codex_linux_sandbox_exe))
        if not isinstance(self.use_legacy_landlock, bool):
            raise TypeError('use_legacy_landlock must be a bool')
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(self, 'windows_sandbox_level', WindowsSandboxLevel.parse(str(self.windows_sandbox_level)))
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError('windows_sandbox_private_desktop must be a bool')

@dataclass(frozen=True)
class ShellSandboxTransformRequest:
    command: SandboxCommand
    permissions: PermissionProfile
    sandbox: Any
    enforce_managed_network: bool
    network: Any | None
    sandbox_policy_cwd: Path
    codex_linux_sandbox_exe: Path | None
    use_legacy_landlock: bool
    windows_sandbox_level: WindowsSandboxLevel
    windows_sandbox_private_desktop: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.command, SandboxCommand):
            raise TypeError('command must be SandboxCommand')
        if not isinstance(self.permissions, PermissionProfile):
            raise TypeError('permissions must be PermissionProfile')
        if not isinstance(self.enforce_managed_network, bool):
            raise TypeError('enforce_managed_network must be a bool')
        if not isinstance(self.sandbox_policy_cwd, Path):
            object.__setattr__(self, 'sandbox_policy_cwd', Path(self.sandbox_policy_cwd))
        if self.codex_linux_sandbox_exe is not None and (not isinstance(self.codex_linux_sandbox_exe, Path)):
            object.__setattr__(self, 'codex_linux_sandbox_exe', Path(self.codex_linux_sandbox_exe))
        if not isinstance(self.use_legacy_landlock, bool):
            raise TypeError('use_legacy_landlock must be a bool')
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(self, 'windows_sandbox_level', WindowsSandboxLevel.parse(str(self.windows_sandbox_level)))
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError('windows_sandbox_private_desktop must be a bool')

@dataclass(frozen=True)
class ShellCommandExecutorRunContext:
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    network: Any | None
    sandbox: SandboxType
    sandbox_policy_cwd: Path
    windows_sandbox_level: WindowsSandboxLevel
    permission_profile: PermissionProfile
    file_system_sandbox_policy: FileSystemSandboxPolicy
    network_sandbox_policy: NetworkSandboxPolicy
    arg0: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'command', _string_tuple(self.command, 'command'))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, 'cwd', Path(self.cwd))
        object.__setattr__(self, 'env', _env_dict(self.env))
        if not isinstance(self.sandbox, SandboxType):
            object.__setattr__(self, 'sandbox', SandboxType(str(self.sandbox)))
        if not isinstance(self.sandbox_policy_cwd, Path):
            object.__setattr__(self, 'sandbox_policy_cwd', Path(self.sandbox_policy_cwd))
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(self, 'windows_sandbox_level', WindowsSandboxLevel.parse(str(self.windows_sandbox_level)))
        if not isinstance(self.permission_profile, PermissionProfile):
            raise TypeError('permission_profile must be PermissionProfile')
        if not isinstance(self.file_system_sandbox_policy, FileSystemSandboxPolicy):
            raise TypeError('file_system_sandbox_policy must be FileSystemSandboxPolicy')
        if not isinstance(self.network_sandbox_policy, NetworkSandboxPolicy):
            object.__setattr__(self, 'network_sandbox_policy', NetworkSandboxPolicy.parse(str(self.network_sandbox_policy)))
        if self.arg0 is not None and (not isinstance(self.arg0, str)):
            raise TypeError('arg0 must be a string or None')

@dataclass(frozen=True)
class ShellZshForkExecParams:
    command: str
    workdir: str
    timeout_ms: int
    login: bool

    def __post_init__(self) -> None:
        if not isinstance(self.command, str):
            raise TypeError('command must be a string')
        if not isinstance(self.workdir, str):
            raise TypeError('workdir must be a string')
        if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
            raise TypeError('timeout_ms must be an integer')
        if self.timeout_ms < 0:
            raise ValueError('timeout_ms must be non-negative')
        if not isinstance(self.login, bool):
            raise TypeError('login must be a bool')

@dataclass(frozen=True)
class ShellZshForkCancellationPlan:
    stopwatch_token: CancellationToken
    cancel_token: CancellationToken
    network_denial_cancellation_token: CancellationToken | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.stopwatch_token, CancellationToken):
            raise TypeError('stopwatch_token must be CancellationToken')
        if not isinstance(self.cancel_token, CancellationToken):
            raise TypeError('cancel_token must be CancellationToken')
        if self.network_denial_cancellation_token is not None and (not isinstance(self.network_denial_cancellation_token, CancellationToken)):
            raise TypeError('network_denial_cancellation_token must be CancellationToken or None')

@dataclass
class ShellEscalationSession:
    """Runtime session facade for the zsh-fork escalation socket env."""
    env_vars: dict[str, str]
    close_callback: Any | None = None

    def __post_init__(self) -> None:
        self.env_vars = _env_dict(self.env_vars)

    def env(self) -> dict[str, str]:
        return dict(self.env_vars)

    def close_client_socket(self) -> None:
        if callable(self.close_callback):
            self.close_callback()

def _ctx_service(ctx: Any, name: str) -> Any:
    services = getattr(getattr(ctx, 'session', None), 'services', None)
    return getattr(services, name, None)

@dataclass(frozen=True)
class ShellEscalateAction:
    type: str
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {'run', 'escalate', 'deny'}:
            raise ValueError(f'unknown shell escalate action type: {self.type}')
        if self.type == 'deny':
            if self.reason is not None and (not isinstance(self.reason, str)):
                raise TypeError('reason must be a string or None')
        elif self.reason is not None:
            raise ValueError(f'{self.type} action must not include reason')

    @classmethod
    def run(cls) -> 'ShellEscalateAction':
        return cls('run')

    @classmethod
    def escalate(cls) -> 'ShellEscalateAction':
        return cls('escalate')

    @classmethod
    def deny(cls, reason: str | None=None) -> 'ShellEscalateAction':
        return cls('deny', reason)

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'ShellEscalateAction':
        if not isinstance(value, Mapping):
            raise TypeError('shell escalate action must be a mapping')
        action_type = value.get('type')
        if action_type == 'run':
            return cls.run()
        if action_type == 'escalate':
            return cls.escalate()
        if action_type == 'deny':
            return cls.deny(value.get('reason'))
        raise ValueError(f'unknown shell escalate action type: {action_type!r}')

    def to_mapping(self) -> dict[str, str | None]:
        if self.type == 'deny':
            return {'type': 'deny', 'reason': self.reason}
        return {'type': self.type}

@dataclass(frozen=True)
class ShellEscalateRequest:
    file: Path
    argv: tuple[str, ...]
    workdir: Path
    env: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.file, Path):
            object.__setattr__(self, 'file', Path(self.file))
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, 'argv', tuple(self.argv))
        for arg in self.argv:
            if not isinstance(arg, str):
                raise TypeError('escalate request argv entries must be strings')
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, 'workdir', Path(self.workdir))
        if not isinstance(self.env, dict):
            object.__setattr__(self, 'env', dict(self.env))
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError('escalate request env must map strings to strings')

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'ShellEscalateRequest':
        if not isinstance(value, Mapping):
            raise TypeError('shell escalate request must be a mapping')
        return cls(value.get('file'), tuple(value.get('argv', ())), value.get('workdir'), dict(value.get('env', {})))

    def to_mapping(self) -> dict[str, Any]:
        return {'file': self.file.as_posix(), 'argv': list(self.argv), 'workdir': self.workdir.as_posix(), 'env': dict(self.env)}

@dataclass(frozen=True)
class ShellEscalateClientHandshakePlan:
    handshake_client_fd: int
    message: bytes
    fds: tuple[int, ...]

    def __post_init__(self) -> None:
        if isinstance(self.handshake_client_fd, bool) or not isinstance(self.handshake_client_fd, int):
            raise TypeError('handshake_client_fd must be an integer')
        if self.handshake_client_fd < 0:
            raise ValueError(f'{ESCALATE_SOCKET_ENV_VAR} is not a valid file descriptor: {self.handshake_client_fd}')
        if not isinstance(self.message, bytes):
            raise TypeError('message must be bytes')
        if not isinstance(self.fds, tuple):
            object.__setattr__(self, 'fds', tuple(self.fds))
        for fd in self.fds:
            if isinstance(fd, bool) or not isinstance(fd, int):
                raise TypeError('fds must contain integer file descriptors')
            if fd < 0:
                raise ValueError(f'attached fd is not a valid file descriptor: {fd}')

@dataclass(frozen=True)
class ShellEscalateClientSocketPair:
    server: Any
    client: Any
    server_fd: int
    client_fd: int

    def __post_init__(self) -> None:
        for name, fd in (('server_fd', self.server_fd), ('client_fd', self.client_fd)):
            if isinstance(fd, bool) or not isinstance(fd, int):
                raise TypeError(f'{name} must be an integer')
            if fd < 0:
                raise ValueError(f'{name} is not a valid file descriptor: {fd}')

@dataclass(frozen=True)
class ShellEscalateClientWrapperPlan:
    socket_pair: ShellEscalateClientSocketPair
    handshake: ShellEscalateClientHandshakePlan

    def __post_init__(self) -> None:
        if not isinstance(self.socket_pair, ShellEscalateClientSocketPair):
            raise TypeError('socket_pair must be ShellEscalateClientSocketPair')
        if not isinstance(self.handshake, ShellEscalateClientHandshakePlan):
            raise TypeError('handshake must be ShellEscalateClientHandshakePlan')

@dataclass(frozen=True)
class ShellEscalatePolicyInput:
    program: Path
    argv: tuple[str, ...]
    workdir: Path

    def __post_init__(self) -> None:
        if not isinstance(self.program, Path):
            object.__setattr__(self, 'program', Path(self.program))
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, 'argv', tuple(self.argv))
        for arg in self.argv:
            if not isinstance(arg, str):
                raise TypeError('escalate policy argv entries must be strings')
        if not isinstance(self.workdir, Path):
            object.__setattr__(self, 'workdir', Path(self.workdir))

def shell_escalate_policy_input_from_request(request: ShellEscalateRequest | Mapping[str, Any]) -> ShellEscalatePolicyInput:
    if not isinstance(request, ShellEscalateRequest):
        request = ShellEscalateRequest.from_mapping(request)
    program = request.file if request.file.is_absolute() else request.workdir / request.file
    return ShellEscalatePolicyInput(program, request.argv, request.workdir)

def shell_escalate_decision_for_request(request: ShellEscalateRequest | Mapping[str, Any], determine_action: Any) -> ShellEscalationDecision:
    policy_input = shell_escalate_policy_input_from_request(request)
    decision = determine_action(policy_input.program, policy_input.argv, policy_input.workdir)
    if not isinstance(decision, ShellEscalationDecision):
        raise TypeError('determine_action must return ShellEscalationDecision')
    return decision

def shell_escalation_session_env(client_socket_fd: int, execve_wrapper: str | Path) -> dict[str, str]:
    if isinstance(client_socket_fd, bool) or not isinstance(client_socket_fd, int):
        raise TypeError('client_socket_fd must be an integer')
    return {ESCALATE_SOCKET_ENV_VAR: str(client_socket_fd), EXEC_WRAPPER_ENV_VAR: Path(execve_wrapper).as_posix()}

def shell_escalation_request_env(env: Mapping[str, str]) -> dict[str, str]:
    if not isinstance(env, Mapping):
        raise TypeError('env must be a mapping')
    result: dict[str, str] = {}
    for key, value in env.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise TypeError('env keys and values must be strings')
        if key in {ESCALATE_SOCKET_ENV_VAR, EXEC_WRAPPER_ENV_VAR}:
            continue
        result[key] = value
    return result

def shell_escalation_merge_env_overlay(base_env: Mapping[str, str], env_overlay: Mapping[str, str]) -> dict[str, str]:
    result = _env_dict(base_env)
    overlay = _env_dict(env_overlay)
    for key in (ESCALATE_SOCKET_ENV_VAR, EXEC_WRAPPER_ENV_VAR):
        if key in overlay:
            result[key] = overlay[key]
    return result

def shell_escalation_socket_fd_from_env(env: Mapping[str, str] | None=None) -> int:
    if env is None:
        env = os.environ
    if not isinstance(env, Mapping):
        raise TypeError('env must be a mapping')
    raw_fd = env[ESCALATE_SOCKET_ENV_VAR]
    if not isinstance(raw_fd, str):
        raise TypeError(f'{ESCALATE_SOCKET_ENV_VAR} must be a string')
    client_fd = int(raw_fd)
    if client_fd < 0:
        raise ValueError(f'{ESCALATE_SOCKET_ENV_VAR} is not a valid file descriptor: {client_fd}')
    return client_fd

def shell_escalate_client_handshake_payload(server_socket_fd: int, message: bytes=SHELL_ESCALATE_HANDSHAKE_MESSAGE) -> tuple[bytes, tuple[int, ...]]:
    if not isinstance(message, bytes):
        raise TypeError('handshake message must be bytes')
    if isinstance(server_socket_fd, bool) or not isinstance(server_socket_fd, int):
        raise TypeError('server_socket_fd must be an integer')
    if server_socket_fd < 0:
        raise ValueError(f'server_socket_fd is not a valid file descriptor: {server_socket_fd}')
    return (message, (server_socket_fd,))

def shell_escalate_client_socket_pair(*, pair_factory: Any=socket.socketpair) -> ShellEscalateClientSocketPair:
    pair = pair_factory()
    if not isinstance(pair, tuple) or len(pair) != 2:
        raise TypeError('pair_factory must return a pair')
    server, client = pair
    server_fileno = getattr(server, 'fileno', None)
    client_fileno = getattr(client, 'fileno', None)
    if not callable(server_fileno) or not callable(client_fileno):
        raise TypeError('socket pair entries must expose fileno()')
    return ShellEscalateClientSocketPair(server, client, server_fileno(), client_fileno())

def shell_socket_validate_fds_for_message(fds: Iterable[int], *, max_fds: int=SHELL_SOCKET_MAX_FDS_PER_MESSAGE) -> tuple[int, ...]:
    result = tuple(fds)
    if len(result) > max_fds:
        raise ValueError(f'too many fds: {len(result)}')
    for fd in result:
        if isinstance(fd, bool) or not isinstance(fd, int):
            raise TypeError('fds must be an integer file descriptor')
        if fd < 0:
            raise ValueError(f'fd is not a valid file descriptor: {fd}')
    return result

def shell_socket_sendmsg_with_fds(sock: Any, data: bytes, fds: Iterable[int]=(), *, sendmsg: Any | None=None) -> int:
    if not isinstance(data, bytes):
        raise TypeError('data must be bytes')
    fd_tuple = shell_socket_validate_fds_for_message(fds)
    if sendmsg is None:
        sendmsg = sock.sendmsg
    ancillary = []
    if fd_tuple:
        ancillary = [(socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', fd_tuple))]
    written = sendmsg([data], ancillary)
    if written != len(data):
        raise OSError(f'short datagram write: wrote {written} bytes out of {len(data)}')
    return written

def shell_socket_recvmsg_with_fds(sock: Any, buffer_size: int, *, max_fds: int=SHELL_SOCKET_MAX_FDS_PER_MESSAGE, recvmsg: Any | None=None) -> tuple[bytes, tuple[int, ...]]:
    if isinstance(buffer_size, bool) or not isinstance(buffer_size, int):
        raise TypeError('buffer_size must be an integer')
    if buffer_size < 1:
        raise ValueError('buffer_size must be positive')
    if isinstance(max_fds, bool) or not isinstance(max_fds, int):
        raise TypeError('max_fds must be an integer')
    if max_fds < 0:
        raise ValueError('max_fds must be non-negative')
    if recvmsg is None:
        recvmsg = sock.recvmsg
    item_size = array.array('i').itemsize
    ancbuf_size = socket.CMSG_SPACE(max_fds * item_size)
    data, ancillary, flags, _address = recvmsg(buffer_size, ancbuf_size)
    if flags & getattr(socket, 'MSG_CTRUNC', 0):
        raise OSError('ancillary data truncated while receiving fds')
    received_fds: list[int] = []
    for level, kind, cmsg_data in ancillary:
        if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
            continue
        fd_array = array.array('i')
        usable_length = len(cmsg_data) - len(cmsg_data) % item_size
        fd_array.frombytes(cmsg_data[:usable_length])
        received_fds.extend(fd_array)
    return (bytes(data), shell_socket_validate_fds_for_message(received_fds, max_fds=max_fds))

def shell_socket_send_stream_frame_with_fds(sock: Any, payload: bytes, fds: Iterable[int]=(), *, sendmsg: Any | None=None, send: Any | None=None) -> int:
    if not isinstance(payload, bytes):
        raise TypeError('payload must be bytes')
    fd_tuple = shell_socket_validate_fds_for_message(fds)
    if sendmsg is None and send is None:
        sendmsg = getattr(sock, 'sendmsg', None)
        send = getattr(sock, 'send', None)
    if sendmsg is None and send is None:
        raise TypeError('must provide sendmsg/send or object with sendmsg/send')
    if send is None and (not callable(sendmsg)):
        raise TypeError('send callback must be callable')
    if sendmsg is not None and (not callable(sendmsg)):
        raise TypeError('sendmsg callback must be callable')
    if send is not None and (not callable(send)):
        raise TypeError('send callback must be callable')
    frame = shell_socket_build_length_prefixed_payload(payload)
    offset = 0
    payload_len = len(frame)
    first_chunk = True
    while offset < payload_len:
        chunk = frame[offset:offset + SHELL_SOCKET_STREAM_MAX_PAYLOAD]
        current_fds = fd_tuple if first_chunk else ()
        if sendmsg is not None:
            ancillary: list[Any] = []
            if current_fds:
                ancillary.append((socket.SOL_SOCKET, socket.SCM_RIGHTS, array.array('i', current_fds)))
            sent = sendmsg([chunk], ancillary)
        elif current_fds:
            try:
                sent = send(chunk, current_fds)
            except TypeError:
                sent = send(chunk)
        else:
            try:
                sent = send(chunk, ())
            except TypeError:
                sent = send(chunk)
        if sent is None:
            sent = len(chunk)
        elif not isinstance(sent, int):
            raise TypeError('send callback must return int or None')
        if sent == 0:
            raise OSError('socket closed while sending frame payload')
        if sent < 0:
            raise OSError('socket closed while sending frame payload')
        offset += sent
        first_chunk = False
    return offset

def shell_socket_recv_stream_frame_with_fds(sock: Any, *, max_fds: int=SHELL_SOCKET_MAX_FDS_PER_MESSAGE, recvmsg: Any | None=None, recv: Any | None=None) -> tuple[bytes, tuple[int, ...]]:
    if isinstance(max_fds, bool) or not isinstance(max_fds, int):
        raise TypeError('max_fds must be an integer')
    if max_fds < 0:
        raise ValueError('max_fds must be non-negative')
    if recvmsg is None:
        recvmsg = getattr(sock, 'recvmsg', None)
    if recv is None:
        recv = getattr(sock, 'recv', None)
    if recvmsg is None and recv is None:
        raise TypeError('sock must provide recvmsg/recv or explicit recvmsg/recv must be provided')
    if recvmsg is not None and (not callable(recvmsg)):
        raise TypeError('recvmsg must be callable')
    if recv is not None and (not callable(recv)):
        raise TypeError('recv must be callable')
    item_size = array.array('i').itemsize
    ancbuf_size = socket.CMSG_SPACE(max_fds * item_size)
    header = bytearray()
    transferred_fds: tuple[int, ...] = ()
    captured_control = False
    if recv is None and recvmsg is None:
        raise TypeError('sock must provide recvmsg/recv or explicit recvmsg/recv must be provided')

    def _recv_any(size: int) -> bytes:
        if recv is not None:
            return recv(size)
        data, _ancillary, _flags, _address = recvmsg(size, 0)
        return data
    while len(header) < SHELL_SOCKET_LENGTH_PREFIX_SIZE:
        remaining = SHELL_SOCKET_LENGTH_PREFIX_SIZE - len(header)
        if not captured_control and recvmsg is not None:
            data, ancillary, flags, _address = recvmsg(remaining, ancbuf_size)
            captured_control = True
            if flags & getattr(socket, 'MSG_CTRUNC', 0):
                raise OSError('ancillary data truncated while receiving fds')
            received_fds: list[int] = []
            for level, kind, cmsg_data in ancillary:
                if level != socket.SOL_SOCKET or kind != socket.SCM_RIGHTS:
                    continue
                fd_array = array.array('i')
                usable_length = len(cmsg_data) - len(cmsg_data) % item_size
                fd_array.frombytes(cmsg_data[:usable_length])
                received_fds.extend(fd_array)
            transferred_fds = shell_socket_validate_fds_for_message(received_fds, max_fds=max_fds)
        else:
            data = _recv_any(SHELL_SOCKET_STREAM_MAX_PAYLOAD)
        if not data:
            raise OSError('socket closed while receiving frame header')
        header.extend(data[:remaining])
        if len(data) > remaining:
            raise OSError('frame header overflow while receiving frame body')
    payload_len = struct.unpack('<I', bytes(header[:SHELL_SOCKET_LENGTH_PREFIX_SIZE]))[0]
    payload = bytearray()
    while len(payload) < payload_len:
        chunk = _recv_any(min(SHELL_SOCKET_STREAM_MAX_PAYLOAD, payload_len - len(payload)))
        if not chunk:
            raise OSError('socket closed while receiving frame payload')
        payload.extend(chunk)
    return (bytes(payload), transferred_fds)

def shell_socket_build_length_prefixed_payload(payload: bytes) -> bytes:
    if len(payload) > 4294967295:
        raise ValueError('message too large')
    return struct.pack('<I', len(payload)) + payload

def shell_socket_extract_length_prefixed_payload(data: bytes | bytearray | memoryview) -> bytes:
    raw = bytes(data)
    if len(raw) < SHELL_SOCKET_LENGTH_PREFIX_SIZE:
        return raw
    payload_len = struct.unpack('<I', raw[:SHELL_SOCKET_LENGTH_PREFIX_SIZE])[0]
    if payload_len == len(raw) - SHELL_SOCKET_LENGTH_PREFIX_SIZE:
        return raw[SHELL_SOCKET_LENGTH_PREFIX_SIZE:]
    return raw

def shell_escalate_client_wrapper_plan(*, env: Mapping[str, str] | None=None, pair_factory: Any=socket.socketpair, message: bytes=SHELL_ESCALATE_HANDSHAKE_MESSAGE) -> ShellEscalateClientWrapperPlan:
    socket_pair = shell_escalate_client_socket_pair(pair_factory=pair_factory)
    handshake = shell_escalate_client_handshake_plan(socket_pair.server_fd, env=env, message=message)
    return ShellEscalateClientWrapperPlan(socket_pair, handshake)

def shell_escalate_client_send_handshake(server_socket_fd: int, *, send_with_fds: Any, message: bytes=SHELL_ESCALATE_HANDSHAKE_MESSAGE) -> Any:
    payload, fds = shell_escalate_client_handshake_payload(server_socket_fd, message)
    try:
        return send_with_fds(payload, fds)
    except Exception as exc:
        raise RuntimeError('failed to send handshake datagram') from exc

def shell_escalate_client_handshake_plan(server_socket_fd: int, *, env: Mapping[str, str] | None=None, message: bytes=SHELL_ESCALATE_HANDSHAKE_MESSAGE) -> ShellEscalateClientHandshakePlan:
    handshake_client_fd = shell_escalation_socket_fd_from_env(env)
    payload, fds = shell_escalate_client_handshake_payload(server_socket_fd, message)
    return ShellEscalateClientHandshakePlan(handshake_client_fd, payload, fds)

def shell_escalate_client_handshake_plan_send(plan: ShellEscalateClientHandshakePlan, *, send_with_fds: Any) -> Any:
    if not isinstance(plan, ShellEscalateClientHandshakePlan):
        raise TypeError('plan must be ShellEscalateClientHandshakePlan')
    try:
        return send_with_fds(plan.handshake_client_fd, plan.message, plan.fds)
    except Exception as exc:
        raise RuntimeError('failed to send handshake datagram') from exc

def shell_escalate_client_handshake_run(server_socket_fd: int, *, send_with_fds: Any, env: Mapping[str, str] | None=None, message: bytes=SHELL_ESCALATE_HANDSHAKE_MESSAGE) -> Any:
    plan = shell_escalate_client_handshake_plan(server_socket_fd, env=env, message=message)
    return shell_escalate_client_handshake_plan_send(plan, send_with_fds=send_with_fds)

def shell_escalate_request_from_client(file: str | Path, argv: Iterable[str], *, workdir: str | Path | None=None, env: Mapping[str, str] | None=None) -> ShellEscalateRequest:
    if workdir is None:
        workdir = Path.cwd()
    if env is None:
        env = {}
    return ShellEscalateRequest(file, tuple(argv), workdir, shell_escalation_request_env(env))

def shell_escalate_client_request_exchange(request: ShellEscalateRequest | Mapping[str, Any], *, send_request: Any, receive_response: Any | None=None, client: Any | None=None) -> ShellEscalateResponse:
    if not isinstance(request, ShellEscalateRequest):
        request = ShellEscalateRequest.from_mapping(request)
    try:
        if client is None:
            sent_response = send_request(request)
        else:
            sent_response = send_request(client, request)
    except Exception as exc:
        raise RuntimeError('failed to send EscalateRequest') from exc
    if receive_response is None:
        response = sent_response
    else:
        try:
            response = receive_response() if client is None else receive_response(client)
        except Exception as exc:
            raise RuntimeError('failed to receive EscalateResponse') from exc
    if not isinstance(response, ShellEscalateResponse):
        response = ShellEscalateResponse.from_mapping(response)
    return response

@dataclass(frozen=True)
class ShellEscalateResponse:
    action: ShellEscalateAction

    def __post_init__(self) -> None:
        if not isinstance(self.action, ShellEscalateAction):
            object.__setattr__(self, 'action', ShellEscalateAction.from_mapping(self.action))

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'ShellEscalateResponse':
        if not isinstance(value, Mapping):
            raise TypeError('shell escalate response must be a mapping')
        return cls(ShellEscalateAction.from_mapping(value.get('action')))

    def to_mapping(self) -> dict[str, dict[str, str | None]]:
        return {'action': self.action.to_mapping()}

@dataclass(frozen=True)
class ShellEscalateClientAction:
    type: str
    exit_code: int | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.type not in {'run', 'escalate', 'deny'}:
            raise ValueError(f'unknown shell escalate client action type: {self.type}')
        if self.type == 'deny':
            if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
                raise TypeError('deny client action exit_code must be an integer')
            if self.message is not None and (not isinstance(self.message, str)):
                raise TypeError('deny client action message must be a string or None')
        elif self.exit_code is not None or self.message is not None:
            raise ValueError(f'{self.type} client action must not include exit_code or message')

    @classmethod
    def run(cls) -> 'ShellEscalateClientAction':
        return cls('run')

    @classmethod
    def escalate(cls) -> 'ShellEscalateClientAction':
        return cls('escalate')

    @classmethod
    def deny(cls, reason: str | None=None) -> 'ShellEscalateClientAction':
        if reason is not None and (not isinstance(reason, str)):
            raise TypeError('deny reason must be a string or None')
        message = f'Execution denied: {reason}' if reason is not None else 'Execution denied'
        return cls('deny', exit_code=1, message=message)

def shell_escalate_client_action_from_response(response: ShellEscalateResponse | Mapping[str, Any]) -> ShellEscalateClientAction:
    if not isinstance(response, ShellEscalateResponse):
        response = ShellEscalateResponse.from_mapping(response)
    if response.action.type == 'run':
        return ShellEscalateClientAction.run()
    if response.action.type == 'escalate':
        return ShellEscalateClientAction.escalate()
    if response.action.type == 'deny':
        return ShellEscalateClientAction.deny(response.action.reason)
    raise ValueError(f'unknown shell escalate action type: {response.action.type}')

@dataclass(frozen=True)
class ShellLocalExecvPlan:
    file: str
    argv: tuple[str, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.file, str):
            raise TypeError('execv file must be a string')
        if '\x00' in self.file:
            raise ValueError('NUL in file')
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, 'argv', tuple(self.argv))
        for arg in self.argv:
            if not isinstance(arg, str):
                raise TypeError('execv argv entries must be strings')
            if '\x00' in arg:
                raise ValueError('NUL in argv')

def shell_local_execv_plan(file: str, argv: Iterable[str]) -> ShellLocalExecvPlan:
    return ShellLocalExecvPlan(file, tuple(argv))

def shell_local_execv_run(plan: ShellLocalExecvPlan, *, execv: Any=os.execv) -> Any:
    if not isinstance(plan, ShellLocalExecvPlan):
        raise TypeError('plan must be ShellLocalExecvPlan')
    return execv(plan.file, plan.argv)

@dataclass(frozen=True)
class ShellEscalateClientPlan:
    action: ShellEscalateClientAction
    local_execv: ShellLocalExecvPlan | None = None
    super_exec: ShellSuperExecMessage | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.action, ShellEscalateClientAction):
            raise TypeError('action must be ShellEscalateClientAction')
        if self.action.type == 'run':
            if not isinstance(self.local_execv, ShellLocalExecvPlan):
                raise TypeError('run client plan must include local_execv')
            if self.super_exec is not None:
                raise ValueError('run client plan must not include super_exec')
        elif self.action.type == 'escalate':
            if not isinstance(self.super_exec, ShellSuperExecMessage):
                raise TypeError('escalate client plan must include super_exec')
            if self.local_execv is not None:
                raise ValueError('escalate client plan must not include local_execv')
        elif self.action.type == 'deny':
            if self.local_execv is not None or self.super_exec is not None:
                raise ValueError('deny client plan must not include exec plans')

def shell_escalate_client_plan_from_response(response: ShellEscalateResponse | Mapping[str, Any], file: str, argv: Iterable[str], destination_fds: Iterable[int] | None=None) -> ShellEscalateClientPlan:
    action = shell_escalate_client_action_from_response(response)
    if action.type == 'run':
        return ShellEscalateClientPlan(action, local_execv=shell_local_execv_plan(file, argv))
    if action.type == 'escalate':
        if destination_fds is None:
            destination_fds = SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS
        return ShellEscalateClientPlan(action, super_exec=ShellSuperExecMessage(tuple(destination_fds)))
    return ShellEscalateClientPlan(action)

def shell_escalate_client_plan_run(plan: ShellEscalateClientPlan, *, execv: Any=os.execv, super_exec: Any | None=None, super_exec_send_with_fds: Any | None=None, super_exec_receive_result: Any | None=None, super_exec_client: Any | None=None, stdio: Iterable[Any] | None=None, dup: Any=os.dup, stderr: Any=sys.stderr) -> Any:
    if not isinstance(plan, ShellEscalateClientPlan):
        raise TypeError('plan must be ShellEscalateClientPlan')
    if plan.action.type == 'run':
        return shell_local_execv_run(plan.local_execv, execv=execv)
    if plan.action.type == 'escalate':
        if super_exec is not None:
            if super_exec_send_with_fds is not None or super_exec_receive_result is not None:
                raise TypeError('super_exec cannot be used with split super_exec callbacks')
        elif super_exec_send_with_fds is None and super_exec_receive_result is None:
            raise TypeError('super-exec execution requires super_exec or split super_exec callbacks')
        elif super_exec_send_with_fds is None or super_exec_receive_result is None:
            raise TypeError('super_exec_send_with_fds and super_exec_receive_result must be both provided')
        transferred_fds = shell_super_exec_stdio_transfer_fds(stdio, dup=dup)
        if super_exec is not None:
            return shell_super_exec_exchange_exit_code(plan.super_exec, transferred_fds, exchange=super_exec)
        if super_exec_send_with_fds is not None and super_exec_receive_result is not None:
            if super_exec_client is None:
                super_exec_send_with_fds(plan.super_exec, transferred_fds)
                result = super_exec_receive_result()
                return shell_super_exec_exit_code_from_result(_parse_shell_super_exec_result(result))
            return shell_super_exec_send_receive_exit_code(plan.super_exec, transferred_fds, send_with_fds=super_exec_send_with_fds, receive_result=super_exec_receive_result, client=super_exec_client)
        if super_exec_send_with_fds is not None or super_exec_receive_result is not None:
            raise TypeError('super_exec_send_with_fds and super_exec_receive_result must be both provided')
        raise TypeError('super-exec execution requires super_exec or split super_exec callbacks')
    if plan.action.type == 'deny':
        stderr.write(f'{plan.action.message}\n')
        return plan.action.exit_code
    raise ValueError(f'unknown shell escalate client action type: {plan.action.type}')

def shell_escalate_client_response_run(response: ShellEscalateResponse | Mapping[str, Any], file: str, argv: Iterable[str], *, destination_fds: Iterable[int] | None=None, execv: Any=os.execv, super_exec: Any | None=None, super_exec_send_with_fds: Any | None=None, super_exec_receive_result: Any | None=None, super_exec_client: Any | None=None, stdio: Iterable[Any] | None=None, dup: Any=os.dup, stderr: Any=sys.stderr) -> Any:
    plan = shell_escalate_client_plan_from_response(response, file, argv, destination_fds=destination_fds)
    return shell_escalate_client_plan_run(plan, execv=execv, super_exec=super_exec, super_exec_send_with_fds=super_exec_send_with_fds, super_exec_receive_result=super_exec_receive_result, super_exec_client=super_exec_client, stdio=stdio, dup=dup, stderr=stderr)

def shell_escalate_client_request_run(file: str | Path, argv: Iterable[str], *, send_request: Any, receive_response: Any | None=None, client: Any | None=None, workdir: str | Path | None=None, env: Mapping[str, str] | None=None, destination_fds: Iterable[int] | None=None, execv: Any=os.execv, super_exec: Any | None=None, super_exec_send_with_fds: Any | None=None, super_exec_receive_result: Any | None=None, super_exec_client: Any | None=None, stdio: Iterable[Any] | None=None, dup: Any=os.dup, stderr: Any=sys.stderr) -> Any:
    request = shell_escalate_request_from_client(file, argv, workdir=workdir, env=env)
    response = shell_escalate_client_request_exchange(request, send_request=send_request, receive_response=receive_response, client=client)
    return shell_escalate_client_response_run(response, request.file.as_posix(), request.argv, destination_fds=destination_fds, execv=execv, super_exec=super_exec, super_exec_send_with_fds=super_exec_send_with_fds, super_exec_receive_result=super_exec_receive_result, super_exec_client=super_exec_client, stdio=stdio, dup=dup, stderr=stderr)

def shell_escalate_client_wrapper_run(file: str | Path, argv: Iterable[str], *, server_socket_fd: int, send_with_fds: Any, send_request: Any, receive_response: Any | None=None, workdir: str | Path | None=None, env: Mapping[str, str] | None=None, destination_fds: Iterable[int] | None=None, execv: Any=os.execv, super_exec: Any | None=None, super_exec_send_with_fds: Any | None=None, super_exec_receive_result: Any | None=None, super_exec_client: Any | None=None, stdio: Iterable[Any] | None=None, dup: Any=os.dup, stderr: Any=sys.stderr) -> Any:
    shell_escalate_client_handshake_run(server_socket_fd, send_with_fds=send_with_fds, env=env)
    return shell_escalate_client_request_run(file, argv, send_request=send_request, receive_response=receive_response, workdir=workdir, env=env, destination_fds=destination_fds, execv=execv, super_exec=super_exec, super_exec_send_with_fds=super_exec_send_with_fds, super_exec_receive_result=super_exec_receive_result, super_exec_client=super_exec_client, stdio=stdio, dup=dup, stderr=stderr)

def shell_escalate_client_wrapper_plan_run(plan: ShellEscalateClientWrapperPlan, file: str | Path, argv: Iterable[str], *, send_with_fds: Any, send_request: Any, receive_response: Any | None=None, request_client: Any | None=None, workdir: str | Path | None=None, env: Mapping[str, str] | None=None, destination_fds: Iterable[int] | None=None, execv: Any=os.execv, super_exec: Any | None=None, super_exec_send_with_fds: Any | None=None, super_exec_receive_result: Any | None=None, super_exec_client: Any | None=None, stdio: Iterable[Any] | None=None, dup: Any=os.dup, stderr: Any=sys.stderr) -> Any:
    if not isinstance(plan, ShellEscalateClientWrapperPlan):
        raise TypeError('plan must be ShellEscalateClientWrapperPlan')
    shell_escalate_client_wrapper_plan_send_handshake(plan, send_with_fds=send_with_fds)
    exchange_client = request_client
    if exchange_client is None and receive_response is not None:
        exchange_client = plan.socket_pair.client
    exchange_super_exec_client = super_exec_client
    if exchange_super_exec_client is None and super_exec is None and (super_exec_send_with_fds is not None) and (super_exec_receive_result is not None):
        exchange_super_exec_client = plan.socket_pair.client
    return shell_escalate_client_request_run(file, argv, send_request=send_request, receive_response=receive_response, client=exchange_client, workdir=workdir, env=env, destination_fds=destination_fds, execv=execv, super_exec=super_exec, super_exec_send_with_fds=super_exec_send_with_fds, super_exec_receive_result=super_exec_receive_result, super_exec_client=exchange_super_exec_client, stdio=stdio, dup=dup, stderr=stderr)

def shell_escalate_client_wrapper_plan_send_handshake(plan: ShellEscalateClientWrapperPlan, *, send_with_fds: Any) -> Any:
    if not isinstance(plan, ShellEscalateClientWrapperPlan):
        raise TypeError('plan must be ShellEscalateClientWrapperPlan')
    shell_escalate_client_handshake_plan_send(plan.handshake, send_with_fds=send_with_fds)
    return plan.socket_pair.client

def shell_escalate_client_wrapper_run_with_socket_pair(file: str | Path, argv: Iterable[str], *, send_with_fds: Any, send_request: Any, pair_factory: Any=socket.socketpair, receive_response: Any | None=None, request_client: Any | None=None, workdir: str | Path | None=None, env: Mapping[str, str] | None=None, destination_fds: Iterable[int] | None=None, execv: Any=os.execv, super_exec: Any | None=None, super_exec_send_with_fds: Any | None=None, super_exec_receive_result: Any | None=None, super_exec_client: Any | None=None, stdio: Iterable[Any] | None=None, dup: Any=os.dup, stderr: Any=sys.stderr) -> Any:
    plan = shell_escalate_client_wrapper_plan(env=env, pair_factory=pair_factory)
    return shell_escalate_client_wrapper_plan_run(plan, file, argv, send_with_fds=send_with_fds, send_request=send_request, receive_response=receive_response, request_client=request_client, workdir=workdir, env=env, destination_fds=destination_fds, execv=execv, super_exec=super_exec, super_exec_send_with_fds=super_exec_send_with_fds, super_exec_receive_result=super_exec_receive_result, super_exec_client=super_exec_client, stdio=stdio, dup=dup, stderr=stderr)

@dataclass(frozen=True)
class ShellSuperExecMessage:
    fds: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.fds, tuple):
            object.__setattr__(self, 'fds', tuple(self.fds))
        for fd in self.fds:
            if isinstance(fd, bool) or not isinstance(fd, int):
                raise TypeError('fds must be an integer file descriptor')

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'ShellSuperExecMessage':
        if not isinstance(value, Mapping):
            raise TypeError('shell super exec message must be a mapping')
        fds = value.get('fds', ())
        if isinstance(fds, (str, bytes)) or not isinstance(fds, Iterable):
            raise TypeError('fds must be an iterable of integer file descriptors')
        return cls(tuple(fds))

    def to_mapping(self) -> dict[str, list[int]]:
        return {'fds': list(self.fds)}

    def to_payload(self) -> bytes:
        return json.dumps(self.to_mapping()).encode('utf-8')

    def to_framed_payload(self) -> bytes:
        return shell_socket_build_length_prefixed_payload(self.to_payload())

@dataclass(frozen=True)
class ShellSuperExecResult:
    exit_code: int

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError('exit_code must be an integer')

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> 'ShellSuperExecResult':
        if not isinstance(value, Mapping):
            raise TypeError('shell super exec result must be a mapping')
        return cls(value.get('exit_code'))

    def to_mapping(self) -> dict[str, int]:
        return {'exit_code': self.exit_code}

def shell_super_exec_duplicate_fd_for_transfer(fd: Any, name: str, *, dup: Any=os.dup) -> int:
    if not isinstance(name, str):
        raise TypeError('name must be a string')
    source_fd = fd
    if not isinstance(source_fd, int):
        fileno = getattr(source_fd, 'fileno', None)
        if not callable(fileno):
            raise TypeError('fd must be an integer file descriptor or expose fileno()')
        try:
            source_fd = fileno()
        except io.UnsupportedOperation:
            fallback_fds = {'stdin': 0, 'stdout': 1, 'stderr': 2}
            if name in fallback_fds:
                source_fd = fallback_fds[name]
            else:
                raise
    if isinstance(source_fd, bool) or not isinstance(source_fd, int):
        raise TypeError('fd must be an integer file descriptor or expose fileno()')
    try:
        return dup(source_fd)
    except OSError as exc:
        raise OSError(f'failed to duplicate {name} for escalation transfer') from exc

def shell_super_exec_stdio_transfer_fds(stdio: Iterable[Any] | None=None, *, names: Iterable[str]=('stdin', 'stdout', 'stderr'), dup: Any=os.dup) -> tuple[int, ...]:
    if stdio is None:
        stdio = (sys.stdin, sys.stdout, sys.stderr)
    streams = tuple(stdio)
    labels = tuple(names)
    if len(streams) != len(labels):
        raise ValueError('stdio and names must contain the same number of entries')
    return tuple((shell_super_exec_duplicate_fd_for_transfer(stream, name, dup=dup) for stream, name in zip(streams, labels)))

def shell_super_exec_message_for_escalate_action(action: ShellEscalateAction | Mapping[str, Any], destination_fds: Iterable[int]=SHELL_SUPER_EXEC_STDIO_DESTINATION_FDS) -> ShellSuperExecMessage | None:
    if not isinstance(action, ShellEscalateAction):
        action = ShellEscalateAction.from_mapping(action)
    if action.type == 'escalate':
        return ShellSuperExecMessage(tuple(destination_fds))
    return None

def shell_super_exec_exit_code_from_result(result: ShellSuperExecResult | Mapping[str, Any]) -> int:
    if not isinstance(result, ShellSuperExecResult):
        result = ShellSuperExecResult.from_mapping(result)
    return result.exit_code

def shell_super_exec_exchange_exit_code(message: ShellSuperExecMessage | Mapping[str, Any], transferred_fds: Iterable[int], *, exchange: Any) -> int:
    if not isinstance(message, ShellSuperExecMessage):
        message = ShellSuperExecMessage.from_mapping(message)
    transferred = tuple(transferred_fds)
    result = exchange(message, transferred)
    return shell_super_exec_exit_code_from_result(result)

def shell_super_exec_send_receive_exit_code(message: ShellSuperExecMessage | Mapping[str, Any], transferred_fds: Iterable[int], *, send_with_fds: Any, receive_result: Any, client: Any | None=None) -> int:
    if not isinstance(message, ShellSuperExecMessage):
        message = ShellSuperExecMessage.from_mapping(message)
    transferred = tuple(transferred_fds)
    payload = message.to_payload()
    framed_payload = message.to_framed_payload()
    send_error: Exception | None = None
    positional_args: int | None = None
    payload_annotation: object = None
    try:
        signature = inspect.signature(send_with_fds)
        positional_parameters = [parameter for parameter in signature.parameters.values() if parameter.kind in (parameter.POSITIONAL_ONLY, parameter.POSITIONAL_OR_KEYWORD)]
        if any((parameter.kind == parameter.VAR_POSITIONAL for parameter in signature.parameters.values())):
            positional_args = None
        else:
            positional_args = len(positional_parameters)
        payload_index = 1 if client is not None else 0
        if len(positional_parameters) > payload_index:
            payload_annotation = positional_parameters[payload_index].annotation
    except (TypeError, ValueError):
        positional_args = None
    wants_object_fallback = payload_annotation is object
    if client is None:
        attempts = [(payload, transferred), (framed_payload, transferred), (message, transferred)] if wants_object_fallback or positional_args not in (2, 3) else [(framed_payload, transferred), (payload, transferred), (message, transferred)]
    else:
        attempts = [(client, payload, transferred), (client, framed_payload, transferred), (client, message, transferred)] if wants_object_fallback else [(client, framed_payload, transferred), (client, payload, transferred), (client, message, transferred)]
    for attempt in attempts:
        try:
            send_with_fds(*attempt)
            send_error = None
            break
        except Exception as exc:
            send_error = exc
            if not isinstance(exc, TypeError):
                break
            continue
    if send_error is not None:
        raise RuntimeError('failed to send SuperExecMessage') from send_error
    return shell_super_exec_exit_code_from_result(_parse_shell_super_exec_result(receive_result() if client is None else receive_result(client)))

def _parse_shell_super_exec_result(result: object) -> object:
    if isinstance(result, tuple) and len(result) == 2 and isinstance(result[0], (bytes, bytearray, memoryview)):
        payload_bytes = shell_socket_extract_length_prefixed_payload(result[0])
        return json.loads(payload_bytes.decode('utf-8'))
    if isinstance(result, (bytes, bytearray, memoryview)):
        payload_bytes = shell_socket_extract_length_prefixed_payload(bytes(result))
        return json.loads(payload_bytes.decode('utf-8'))
    return result

def shell_super_exec_fd_pairs(message: ShellSuperExecMessage | Mapping[str, Any], transferred_fds: Iterable[int]) -> tuple[tuple[int, int], ...]:
    if not isinstance(message, ShellSuperExecMessage):
        message = ShellSuperExecMessage.from_mapping(message)
    transferred = tuple(transferred_fds)
    if len(transferred) != len(message.fds):
        raise ValueError(f'mismatched number of fds in SuperExecMessage: {len(message.fds)} in the message, {len(transferred)} from the control message')
    return tuple(zip(message.fds, transferred))

def shell_super_exec_result_from_exit_status(exit_code: int | None) -> ShellSuperExecResult:
    if exit_code is None:
        return ShellSuperExecResult(127)
    return ShellSuperExecResult(exit_code)

@dataclass(frozen=True)
class ShellPreparedExec:
    command: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    arg0: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.command, tuple):
            object.__setattr__(self, 'command', tuple(self.command))
        for part in self.command:
            if not isinstance(part, str):
                raise TypeError('prepared exec command entries must be strings')
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, 'cwd', Path(self.cwd))
        if not isinstance(self.env, dict):
            object.__setattr__(self, 'env', dict(self.env))
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError('prepared exec env must map strings to strings')
        if self.arg0 is not None and (not isinstance(self.arg0, str)):
            raise TypeError('prepared exec arg0 must be a string or None')

def shell_prepared_exec_program_and_args(prepared: ShellPreparedExec) -> tuple[str, tuple[str, ...]]:
    if not isinstance(prepared, ShellPreparedExec):
        raise TypeError('prepared must be ShellPreparedExec')
    if not prepared.command:
        raise ValueError('prepared escalated command must not be empty')
    return (prepared.command[0], prepared.command[1:])

def shell_prepared_exec_effective_arg0(program: str, arg0: str | None) -> str:
    if not isinstance(program, str):
        raise TypeError('program must be a string')
    if arg0 is not None and (not isinstance(arg0, str)):
        raise TypeError('arg0 must be a string or None')
    return arg0 if arg0 is not None else program

@dataclass(frozen=True)
class ShellSuperExecSpawnPlan:
    program: str
    args: tuple[str, ...]
    arg0: str
    cwd: Path
    env: dict[str, str]
    fd_pairs: tuple[tuple[int, int], ...]
    stdio_null: bool = True
    kill_on_drop: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.program, str):
            raise TypeError('program must be a string')
        if not isinstance(self.args, tuple):
            object.__setattr__(self, 'args', tuple(self.args))
        for arg in self.args:
            if not isinstance(arg, str):
                raise TypeError('spawn plan args must be strings')
        if not isinstance(self.arg0, str):
            raise TypeError('arg0 must be a string')
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, 'cwd', Path(self.cwd))
        if not isinstance(self.env, dict):
            object.__setattr__(self, 'env', dict(self.env))
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError('spawn plan env must map strings to strings')
        if not isinstance(self.fd_pairs, tuple):
            object.__setattr__(self, 'fd_pairs', tuple(self.fd_pairs))
        for dst_fd, src_fd in self.fd_pairs:
            if isinstance(dst_fd, bool) or not isinstance(dst_fd, int):
                raise TypeError('spawn plan destination fds must be integers')
            if isinstance(src_fd, bool) or not isinstance(src_fd, int):
                raise TypeError('spawn plan source fds must be integers')
        if not isinstance(self.stdio_null, bool):
            raise TypeError('stdio_null must be a bool')
        if not isinstance(self.kill_on_drop, bool):
            raise TypeError('kill_on_drop must be a bool')

def shell_super_exec_spawn_plan(prepared: ShellPreparedExec, message: ShellSuperExecMessage | Mapping[str, Any], transferred_fds: Iterable[int]) -> ShellSuperExecSpawnPlan:
    program, args = shell_prepared_exec_program_and_args(prepared)
    return ShellSuperExecSpawnPlan(program=program, args=args, arg0=shell_prepared_exec_effective_arg0(program, prepared.arg0), cwd=prepared.cwd, env=dict(prepared.env), fd_pairs=shell_super_exec_fd_pairs(message, transferred_fds))

@dataclass(frozen=True)
class ShellSuperExecSubprocessSpec:
    executable: str
    argv: tuple[str, ...]
    cwd: Path
    env: dict[str, str]
    fd_pairs: tuple[tuple[int, int], ...]
    stdio_null: bool = True
    kill_on_cancel: bool = True

    def __post_init__(self) -> None:
        if not isinstance(self.executable, str):
            raise TypeError('executable must be a string')
        if not isinstance(self.argv, tuple):
            object.__setattr__(self, 'argv', tuple(self.argv))
        if not self.argv:
            raise ValueError('subprocess argv must not be empty')
        for arg in self.argv:
            if not isinstance(arg, str):
                raise TypeError('subprocess argv entries must be strings')
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, 'cwd', Path(self.cwd))
        if not isinstance(self.env, dict):
            object.__setattr__(self, 'env', dict(self.env))
        for key, value in self.env.items():
            if not isinstance(key, str) or not isinstance(value, str):
                raise TypeError('subprocess env must map strings to strings')
        if not isinstance(self.fd_pairs, tuple):
            object.__setattr__(self, 'fd_pairs', tuple(self.fd_pairs))
        for dst_fd, src_fd in self.fd_pairs:
            if isinstance(dst_fd, bool) or not isinstance(dst_fd, int):
                raise TypeError('subprocess destination fds must be integers')
            if isinstance(src_fd, bool) or not isinstance(src_fd, int):
                raise TypeError('subprocess source fds must be integers')
        if not isinstance(self.stdio_null, bool):
            raise TypeError('stdio_null must be a bool')
        if not isinstance(self.kill_on_cancel, bool):
            raise TypeError('kill_on_cancel must be a bool')

def shell_super_exec_subprocess_spec(plan: ShellSuperExecSpawnPlan) -> ShellSuperExecSubprocessSpec:
    if not isinstance(plan, ShellSuperExecSpawnPlan):
        raise TypeError('plan must be ShellSuperExecSpawnPlan')
    return ShellSuperExecSubprocessSpec(executable=plan.program, argv=(plan.arg0, *plan.args), cwd=plan.cwd, env=dict(plan.env), fd_pairs=plan.fd_pairs, stdio_null=plan.stdio_null, kill_on_cancel=plan.kill_on_drop)

def shell_super_exec_dup2_preexec_fn(fd_pairs: Iterable[tuple[int, int]]):
    pairs = tuple(fd_pairs)
    for dst_fd, src_fd in pairs:
        if isinstance(dst_fd, bool) or not isinstance(dst_fd, int):
            raise TypeError('preexec destination fds must be integers')
        if isinstance(src_fd, bool) or not isinstance(src_fd, int):
            raise TypeError('preexec source fds must be integers')

    def preexec() -> None:
        for dst_fd, src_fd in pairs:
            os.dup2(src_fd, dst_fd)
    return preexec

def shell_super_exec_popen_kwargs(spec: ShellSuperExecSubprocessSpec) -> dict[str, Any]:
    if not isinstance(spec, ShellSuperExecSubprocessSpec):
        raise TypeError('spec must be ShellSuperExecSubprocessSpec')
    kwargs: dict[str, Any] = {'args': spec.argv, 'executable': spec.executable, 'cwd': spec.cwd, 'env': dict(spec.env), 'preexec_fn': shell_super_exec_dup2_preexec_fn(spec.fd_pairs)}
    if spec.stdio_null:
        kwargs['stdin'] = subprocess.DEVNULL
        kwargs['stdout'] = subprocess.DEVNULL
        kwargs['stderr'] = subprocess.DEVNULL
    return kwargs

def shell_super_exec_run_subprocess(spec: ShellSuperExecSubprocessSpec, *, cancellation_tokens: Iterable[CancellationToken]=(), popen_factory: Any=subprocess.Popen, poll_interval: float=0.05) -> ShellSuperExecResult:
    if not isinstance(spec, ShellSuperExecSubprocessSpec):
        raise TypeError('spec must be ShellSuperExecSubprocessSpec')
    tokens = tuple(cancellation_tokens)
    for token in tokens:
        if not isinstance(token, CancellationToken):
            raise TypeError('cancellation_tokens must contain CancellationToken instances')
    if not isinstance(poll_interval, (int, float)) or isinstance(poll_interval, bool) or poll_interval < 0:
        raise TypeError('poll_interval must be a non-negative number')
    child = popen_factory(**shell_super_exec_popen_kwargs(spec))
    killed = False
    while True:
        if spec.kill_on_cancel and any((token.is_cancelled() for token in tokens)):
            if not killed:
                child.kill()
                killed = True
            return shell_super_exec_result_from_exit_status(child.wait())
        exit_code = child.poll()
        if exit_code is not None:
            return shell_super_exec_result_from_exit_status(exit_code)
        if poll_interval:
            time.sleep(poll_interval)

def shell_super_exec_run_prepared(prepared: ShellPreparedExec, message: ShellSuperExecMessage | Mapping[str, Any], transferred_fds: Iterable[int], *, cancellation_tokens: Iterable[CancellationToken]=(), popen_factory: Any=subprocess.Popen, poll_interval: float=0.05) -> ShellSuperExecResult:
    plan = shell_super_exec_spawn_plan(prepared, message, transferred_fds)
    spec = shell_super_exec_subprocess_spec(plan)
    return shell_super_exec_run_subprocess(spec, cancellation_tokens=cancellation_tokens, popen_factory=popen_factory, poll_interval=poll_interval)

@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    stdout: str = ''
    stderr: str = ''
    output: str = ''
    duration: timedelta = timedelta(0)
    timed_out: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError('exit_code must be an int')
        for field_name in ('stdout', 'stderr', 'output'):
            if not isinstance(getattr(self, field_name), str):
                raise TypeError(f'{field_name} must be a string')
        if not isinstance(self.duration, timedelta):
            raise TypeError('duration must be a timedelta')
        if not isinstance(self.timed_out, bool):
            raise TypeError('timed_out must be a bool')

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
    additional_permissions_preapproved: bool = False
    capture_policy: ExecCapturePolicy = ExecCapturePolicy.SHELL_TOOL

    def __post_init__(self) -> None:
        object.__setattr__(self, 'command', _string_tuple(self.command, 'command'))
        if self.shell_type is not None and (not isinstance(self.shell_type, ShellType)):
            object.__setattr__(self, 'shell_type', ShellType(str(self.shell_type)))
        if not isinstance(self.hook_command, str):
            raise TypeError('hook_command must be a string')
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, 'cwd', Path(self.cwd))
        if self.timeout_ms is not None:
            if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
                raise TypeError('timeout_ms must be an int or None')
            if self.timeout_ms < 0:
                raise ValueError('timeout_ms must be non-negative')
        object.__setattr__(self, 'env', _env_dict(self.env))
        object.__setattr__(self, 'explicit_env_overrides', _env_dict(self.explicit_env_overrides))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, 'sandbox_permissions', SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and (not isinstance(self.additional_permissions, AdditionalPermissionProfile)):
            raise TypeError('additional_permissions must be AdditionalPermissionProfile or None')
        if self.justification is not None and (not isinstance(self.justification, str)):
            raise TypeError('justification must be a string or None')
        if not isinstance(self.exec_approval_requirement, ExecApprovalRequirement):
            raise TypeError('exec_approval_requirement must be ExecApprovalRequirement')
        if not isinstance(self.additional_permissions_preapproved, bool):
            raise TypeError('additional_permissions_preapproved must be a bool')
        if not isinstance(self.capture_policy, ExecCapturePolicy):
            object.__setattr__(self, 'capture_policy', ExecCapturePolicy(self.capture_policy))

    def approval_sandbox_permissions(self) -> SandboxPermissions:
        return approval_sandbox_permissions(self.sandbox_permissions, self.additional_permissions_preapproved)

@dataclass(frozen=True)
class ShellApprovalKey:
    command: tuple[str, ...]
    cwd: Path
    sandbox_permissions: SandboxPermissions
    additional_permissions: AdditionalPermissionProfile | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, 'command', _string_tuple(self.command, 'command'))
        if not isinstance(self.cwd, Path):
            object.__setattr__(self, 'cwd', Path(self.cwd))
        if not isinstance(self.sandbox_permissions, SandboxPermissions):
            object.__setattr__(self, 'sandbox_permissions', SandboxPermissions(self.sandbox_permissions))
        if self.additional_permissions is not None and (not isinstance(self.additional_permissions, AdditionalPermissionProfile)):
            raise TypeError('additional_permissions must be AdditionalPermissionProfile or None')

class ShellRuntime:
    """Approval, sandbox, and process owner for ``shell_command``.

    Rust owner: ``codex-core::tools::runtimes::shell::ShellRuntime`` at the
    repository-pinned Codex commit.  Unlike the former Python facade, this is
    a product runtime and does not require callers to inject a test runner.
    """

    def __init__(self, backend: ShellRuntimeBackend) -> None:
        if not isinstance(backend, ShellRuntimeBackend):
            backend = ShellRuntimeBackend(str(backend))
        self.backend = backend

    @classmethod
    def for_shell_command(cls, backend: ShellRuntimeBackend) -> 'ShellRuntime':
        return cls(backend)

    def approval_keys(self, req: ShellRequest) -> tuple[ShellApprovalKey, ...]:
        return shell_approval_keys(req)

    def sandbox_preference(self) -> str:
        return 'auto'

    def escalate_on_failure(self) -> bool:
        return True

    def exec_approval_requirement(self, req: ShellRequest) -> ExecApprovalRequirement:
        return req.exec_approval_requirement

    def permission_request_payload(self, req: ShellRequest) -> PermissionRequestPayload:
        return shell_permission_request_payload(req)

    def sandbox_permissions(self, req: ShellRequest) -> SandboxPermissions:
        return req.sandbox_permissions

    def sandbox_cwd(self, req: ShellRequest) -> Path:
        return req.cwd

    def network_approval_spec(self, req: ShellRequest, ctx: Any) -> NetworkApprovalSpec | None:
        return shell_network_approval_spec(req, call_id=str(getattr(ctx, 'call_id')), tool_name=getattr(ctx, 'tool_name'))

    async def start_approval_async(self, req: ShellRequest, ctx: Any) -> ReviewDecision:
        keys = self.approval_keys(req)
        services = getattr(ctx.session, 'services', None)
        store = getattr(services, 'approval_store', None)
        if store is None:
            store = ApprovalStore()
            if services is not None:
                setattr(services, 'approval_store', store)
        approved_for_session = ReviewDecision.approved_for_session()
        if keys and all((store.get(key) == approved_for_session for key in keys)):
            return approved_for_session
        retry_reason = getattr(ctx, 'retry_reason', None)
        reason = retry_reason or req.justification
        guardian_review_id = getattr(ctx, 'guardian_review_id', None)
        if guardian_review_id is not None:
            reviewer = getattr(ctx.session, 'review_approval_request', None)
            if callable(reviewer):
                decision = reviewer(ctx.turn, guardian_review_id, {'type': 'shell', 'id': str(ctx.call_id), 'command': req.command, 'cwd': req.cwd, 'sandbox_permissions': req.sandbox_permissions, 'additional_permissions': req.additional_permissions, 'justification': req.justification}, retry_reason)
                if inspect.isawaitable(decision):
                    decision = await decision
                return ReviewDecision.from_mapping(decision)
        prompt = getattr(ctx.session, 'request_command_approval', None)
        if not callable(prompt):
            return ReviewDecision.abort()
        decision = prompt(ctx.turn, str(ctx.call_id), None, req.command, req.cwd, reason, getattr(ctx, 'network_approval_context', None), req.exec_approval_requirement.proposed_execpolicy_amendment, req.additional_permissions, None)
        if inspect.isawaitable(decision):
            decision = await decision
        decision = ReviewDecision.from_mapping(decision)
        if decision == approved_for_session:
            for key in keys:
                store.put(key, approved_for_session)
        return decision

    async def run(self, req: ShellRequest, attempt: SandboxAttempt, ctx: Any) -> ExecToolCallOutput | ToolError:
        from pycodex.core.sandboxing import execute_exec_request_with_after_spawn
        from pycodex.shell_command.powershell import prefix_powershell_script_with_utf8
        session_shell = _runtime_session_shell(ctx.session, req)
        env = exec_env_for_sandbox_permissions(req.env, req.sandbox_permissions)
        command = maybe_wrap_shell_lc_with_snapshot(req.command, session_shell, req.cwd, req.explicit_env_overrides, env, is_windows=sys.platform == 'win32')
        command = disable_powershell_profile_for_elevated_windows_sandbox(command, req.shell_type, attempt.sandbox, attempt.windows_sandbox_level)
        if session_shell.shell_type is ShellType.POWERSHELL:
            command = tuple(prefix_powershell_script_with_utf8(command))
        effective_permissions = effective_permission_profile(attempt.permissions, req.additional_permissions)
        managed_network = managed_network_for_runtime(req.network, req.sandbox_permissions)
        if managed_network is not None:
            apply_to_env = getattr(managed_network, 'apply_to_env', None)
            if callable(apply_to_env):
                apply_to_env(env)
        expiration = ExecExpiration.from_timeout_ms(req.timeout_ms)
        cancellation, watchers = _bridge_shell_cancellation(req.cancellation_token, attempt.network_denial_cancellation_token)
        if cancellation is not None:
            expiration = expiration.with_cancellation(cancellation)
        exec_request = ExecRequest(command=tuple(command), cwd=req.cwd, env=env, network=managed_network, expiration=expiration, capture_policy=req.capture_policy, sandbox=attempt.sandbox, windows_sandbox_policy_cwd=attempt.sandbox_cwd, windows_sandbox_level=attempt.windows_sandbox_level, windows_sandbox_private_desktop=attempt.windows_sandbox_private_desktop, permission_profile=effective_permissions, file_system_sandbox_policy=effective_permissions.file_system_sandbox_policy(), network_sandbox_policy=effective_permissions.network_sandbox_policy())
        try:
            return await execute_exec_request_with_after_spawn(exec_request)
        except ExecSandboxTimeout as error:
            return error.output
        except ExecSandboxDenied as error:
            return ToolError.codex({'sandbox': 'denied', 'output': error.output, 'network_policy_decision': None})
        except ExecSandboxSignal as error:
            return ToolError.codex(error)
        except Exception as error:
            return ToolError.codex(error)
        finally:
            for watcher in watchers:
                watcher.cancel()

def _runtime_session_shell(session: Any, req: ShellRequest) -> Shell:
    user_shell = getattr(session, 'user_shell', None)
    shell = user_shell() if callable(user_shell) else getattr(session, 'shell', None)
    if isinstance(shell, Shell):
        return shell
    shell_type = req.shell_type or ShellType.UNKNOWN
    program = req.command[0] if req.command else ''
    return Shell(shell_type, program)

def _bridge_shell_cancellation(*tokens: Any) -> tuple[CancellationToken | None, tuple[asyncio.Task[Any], ...]]:
    active_tokens = tuple((token for token in tokens if token is not None))
    if not active_tokens:
        return (None, ())
    cancellation = CancellationToken()
    watchers: list[asyncio.Task[Any]] = []
    for token in active_tokens:
        if isinstance(token, CancellationToken):
            watchers.append(asyncio.create_task(_forward_shell_cancellation(token, cancellation)))
            continue
        waiter = getattr(token, 'cancelled', None)
        if callable(waiter):
            watchers.append(asyncio.create_task(_forward_external_shell_cancellation(waiter, cancellation)))
    return (cancellation if watchers else None, tuple(watchers))

async def _forward_shell_cancellation(source: CancellationToken, target: CancellationToken) -> None:
    await source.cancelled()
    target.cancel()

async def _forward_external_shell_cancellation(waiter: Any, target: CancellationToken) -> None:
    result = waiter()
    if inspect.isawaitable(result):
        await result
    target.cancel()

def _is_unix_platform() -> bool:
    return os.name == 'posix'

def prepare_unified_exec_zsh_fork_from_session(exec_request: Any, shell_zsh_path: str | Path, escalation_session: Any) -> PreparedUnifiedExecZshFork | None:
    try:
        parsed = extract_shell_script(exec_request.command)
    except ToolRuntimeError:
        return None
    if parsed.program != _path_as_posix_string(shell_zsh_path):
        return None
    env = {**_env_dict(exec_request.env), **_session_env(escalation_session)}
    return PreparedUnifiedExecZshFork(exec_request=replace(exec_request, env=env), escalation_session=escalation_session)

def shell_zsh_fork_exec_params(command: tuple[str, ...] | list[str], cwd: str | Path, timeout_ms: int | None) -> ShellZshForkExecParams:
    parsed = extract_shell_script(command)
    effective_timeout_ms = timeout_ms if timeout_ms is not None else DEFAULT_EXEC_COMMAND_TIMEOUT_MS
    if isinstance(effective_timeout_ms, bool) or not isinstance(effective_timeout_ms, int):
        raise TypeError('timeout_ms must be an integer or None')
    if effective_timeout_ms < 0:
        raise ValueError('timeout_ms must be non-negative')
    return ShellZshForkExecParams(command=parsed.script, workdir=Path(cwd).as_posix(), timeout_ms=effective_timeout_ms, login=parsed.login)

def shell_zsh_fork_cancellation_plan(stopwatch_token: CancellationToken, network_denial_cancellation_token: CancellationToken | None=None) -> ShellZshForkCancellationPlan:
    if not isinstance(stopwatch_token, CancellationToken):
        raise TypeError('stopwatch_token must be CancellationToken')
    if network_denial_cancellation_token is None:
        cancel_token = stopwatch_token
    else:
        if not isinstance(network_denial_cancellation_token, CancellationToken):
            raise TypeError('network_denial_cancellation_token must be CancellationToken or None')
        cancel_token = cancel_when_either(stopwatch_token, network_denial_cancellation_token)
    return ShellZshForkCancellationPlan(stopwatch_token=stopwatch_token, cancel_token=cancel_token, network_denial_cancellation_token=network_denial_cancellation_token)

def shell_escalation_decision_for_approved_review(needs_escalation: bool, escalation_execution: ShellEscalationExecution) -> ShellEscalationDecision:
    if not isinstance(needs_escalation, bool):
        raise TypeError('needs_escalation must be a bool')
    if not isinstance(escalation_execution, ShellEscalationExecution):
        raise TypeError('escalation_execution must be ShellEscalationExecution')
    if needs_escalation:
        return ShellEscalationDecision.escalate(escalation_execution)
    return ShellEscalationDecision.run()

def shell_escalation_decision_for_policy_decision(decision: Any, needs_escalation: bool, escalation_execution: ShellEscalationExecution, *, prompt_rejection_reason: str | None=None) -> ShellEscalationDecision:
    decision_value = getattr(decision, 'value', decision)
    if decision_value == 'forbidden':
        return ShellEscalationDecision.deny('Execution forbidden by policy')
    if decision_value == 'allow':
        return shell_escalation_decision_for_approved_review(needs_escalation, escalation_execution)
    if decision_value == 'prompt':
        if prompt_rejection_reason is not None:
            return ShellEscalationDecision.deny('Execution forbidden by policy')
        return ShellEscalationDecision.prompt()
    raise ValueError(f'unknown policy decision: {decision!r}')

def shell_prepare_escalated_exec(program: str | Path, argv: tuple[str, ...] | list[str], workdir: str | Path, env: Mapping[str, str], execution: ShellEscalationExecution, *, permission_profile: PermissionProfile, prepare_sandboxed_exec: Any) -> ShellPreparedExec:
    if not isinstance(execution, ShellEscalationExecution):
        raise TypeError('execution must be ShellEscalationExecution')
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError('permission_profile must be PermissionProfile')
    if not callable(prepare_sandboxed_exec):
        raise TypeError('prepare_sandboxed_exec must be callable')
    argv_tuple = _string_tuple(argv, 'argv')
    if not argv_tuple:
        raise ValueError('intercepted exec request must contain argv[0]')
    command = join_program_and_argv(program, argv_tuple)
    workdir_path = Path(workdir)
    env_dict = _env_dict(env)
    if execution.type == 'unsandboxed':
        return ShellPreparedExec(command, workdir_path, env_dict, arg0=argv_tuple[0])
    params = shell_prepare_escalated_exec_params(command, workdir_path, env_dict, execution, permission_profile=permission_profile)
    prepared = prepare_sandboxed_exec(params)
    if not isinstance(prepared, ShellPreparedExec):
        raise TypeError('prepare_sandboxed_exec must return ShellPreparedExec')
    return prepared

def shell_prepare_escalated_exec_params(command: tuple[str, ...] | list[str], workdir: str | Path, env: Mapping[str, str], execution: ShellEscalationExecution, *, permission_profile: PermissionProfile) -> ShellPrepareSandboxedExecParams:
    if not isinstance(execution, ShellEscalationExecution):
        raise TypeError('execution must be ShellEscalationExecution')
    if execution.type == 'turn_default':
        return ShellPrepareSandboxedExecParams(command, Path(workdir), _env_dict(env), permission_profile, None)
    if execution.type != 'permissions':
        raise ValueError(f'{execution.type} execution does not use sandboxed parameters')
    permissions = execution.permission_profile
    if isinstance(permissions, AdditionalPermissionProfile):
        return ShellPrepareSandboxedExecParams(command, Path(workdir), _env_dict(env), permission_profile, permissions)
    if isinstance(permissions, PermissionProfile):
        return ShellPrepareSandboxedExecParams(command, Path(workdir), _env_dict(env), permissions, None)
    raise TypeError('permissions execution must carry PermissionProfile or AdditionalPermissionProfile')

def shell_prepare_sandboxed_exec(params: ShellPrepareSandboxedExecParams, context: ShellPrepareSandboxedExecContext, *, sandbox_manager: Any, sandboxable_preference: Any='auto') -> ShellPreparedExec:
    from pycodex.core.sandboxing import ExecOptions, from_sandbox_exec_request
    if not isinstance(params, ShellPrepareSandboxedExecParams):
        raise TypeError('params must be ShellPrepareSandboxedExecParams')
    if not isinstance(context, ShellPrepareSandboxedExecContext):
        raise TypeError('context must be ShellPrepareSandboxedExecContext')
    if not params.command:
        raise ValueError('prepared command must not be empty')
    select_initial = getattr(sandbox_manager, 'select_initial', None)
    transform = getattr(sandbox_manager, 'transform', None)
    if not callable(select_initial) or not callable(transform):
        raise TypeError('sandbox_manager must expose select_initial and transform')
    file_system_sandbox_policy, network_sandbox_policy = params.permission_profile.to_runtime_permissions()
    sandbox = select_initial(file_system_sandbox_policy, network_sandbox_policy, sandboxable_preference, context.windows_sandbox_level, context.network is not None)
    program, *args = params.command
    request = ShellSandboxTransformRequest(command=SandboxCommand(program, tuple(args), params.workdir, params.env, params.additional_permissions), permissions=params.permission_profile, sandbox=sandbox, enforce_managed_network=context.network is not None, network=context.network, sandbox_policy_cwd=context.sandbox_policy_cwd, codex_linux_sandbox_exe=context.codex_linux_sandbox_exe, use_legacy_landlock=context.use_legacy_landlock, windows_sandbox_level=context.windows_sandbox_level, windows_sandbox_private_desktop=context.windows_sandbox_private_desktop)
    exec_request = from_sandbox_exec_request(transform(request), ExecOptions(ExecExpiration.default_timeout(), ExecCapturePolicy.SHELL_TOOL), context.sandbox_policy_cwd)
    apply_to_env = getattr(exec_request.network, 'apply_to_env', None)
    if callable(apply_to_env):
        apply_to_env(exec_request.env)
    return ShellPreparedExec(exec_request.command, exec_request.cwd, exec_request.env, arg0=exec_request.arg0)

def shell_command_executor_exec_request(context: ShellCommandExecutorRunContext, env_overlay: Mapping[str, str], cancel_rx: CancellationToken) -> Any:
    from pycodex.core.exec import ExecRequest
    if not isinstance(context, ShellCommandExecutorRunContext):
        raise TypeError('context must be ShellCommandExecutorRunContext')
    if not isinstance(cancel_rx, CancellationToken):
        raise TypeError('cancel_rx must be CancellationToken')
    return ExecRequest(command=context.command, cwd=context.cwd, env=shell_escalation_merge_env_overlay(context.env, env_overlay), exec_server_env_config=None, network=context.network, expiration=ExecExpiration.cancellation(cancel_rx), capture_policy=ExecCapturePolicy.SHELL_TOOL, sandbox=context.sandbox, windows_sandbox_policy_cwd=context.sandbox_policy_cwd, windows_sandbox_level=context.windows_sandbox_level, windows_sandbox_private_desktop=False, permission_profile=context.permission_profile, file_system_sandbox_policy=context.file_system_sandbox_policy, network_sandbox_policy=context.network_sandbox_policy, windows_sandbox_filesystem_overrides=None, arg0=context.arg0)

async def shell_command_executor_run(context: ShellCommandExecutorRunContext, env_overlay: Mapping[str, str], cancel_rx: CancellationToken, *, execute_exec_request_with_after_spawn: Any, after_spawn: Any | None=None) -> ExecResult:
    if not callable(execute_exec_request_with_after_spawn):
        raise TypeError('execute_exec_request_with_after_spawn must be callable')
    request = shell_command_executor_exec_request(context, env_overlay, cancel_rx)
    result = await _maybe_await(execute_exec_request_with_after_spawn(request, None, after_spawn))
    return exec_result_from_tool_output(result)

def shell_escalate_action_from_decision(decision: ShellEscalationDecision) -> ShellEscalateAction:
    if not isinstance(decision, ShellEscalationDecision):
        raise TypeError('decision must be ShellEscalationDecision')
    if decision.type == 'run':
        return ShellEscalateAction.run()
    if decision.type == 'escalate':
        return ShellEscalateAction.escalate()
    if decision.type == 'deny':
        return ShellEscalateAction.deny(decision.reason)
    raise ValueError('prompt decisions must be resolved before producing an escalation action')

def shell_escalate_response_from_decision(decision: ShellEscalationDecision) -> ShellEscalateResponse:
    return ShellEscalateResponse(shell_escalate_action_from_decision(decision))

@dataclass(frozen=True)
class ShellEscalateServerPlan:
    response: ShellEscalateResponse
    execution: ShellEscalationExecution | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.response, ShellEscalateResponse):
            object.__setattr__(self, 'response', ShellEscalateResponse.from_mapping(self.response))
        action_type = self.response.action.type
        if action_type == 'escalate':
            if not isinstance(self.execution, ShellEscalationExecution):
                raise TypeError('escalate server plan must include execution')
        elif self.execution is not None:
            raise ValueError(f'{action_type} server plan must not include execution')

def shell_escalate_server_plan_from_decision(decision: ShellEscalationDecision) -> ShellEscalateServerPlan:
    if not isinstance(decision, ShellEscalationDecision):
        raise TypeError('decision must be ShellEscalationDecision')
    response = shell_escalate_response_from_decision(decision)
    if decision.type == 'escalate':
        return ShellEscalateServerPlan(response, execution=decision.execution)
    return ShellEscalateServerPlan(response)

def shell_escalate_server_plan_send_response(plan: ShellEscalateServerPlan, send_response: Any) -> ShellEscalationExecution | None:
    if not isinstance(plan, ShellEscalateServerPlan):
        raise TypeError('plan must be ShellEscalateServerPlan')
    send_response(plan.response)
    return plan.execution

def shell_escalate_server_decision_send_response(decision: ShellEscalationDecision, send_response: Any) -> ShellEscalationExecution | None:
    plan = shell_escalate_server_plan_from_decision(decision)
    return shell_escalate_server_plan_send_response(plan, send_response)

def shell_escalate_server_continue_after_response(execution: ShellEscalationExecution | None, *, receive_super_exec: Any, prepare_exec: Any, send_result: Any, cancellation_tokens: Iterable[CancellationToken]=(), popen_factory: Any=subprocess.Popen, poll_interval: float=0.05) -> ShellSuperExecResult | None:
    if execution is None:
        return None
    if not isinstance(execution, ShellEscalationExecution):
        raise TypeError('execution must be ShellEscalationExecution or None')
    message, transferred_fds = receive_super_exec()
    prepared = prepare_exec(execution)
    result = shell_super_exec_run_prepared(prepared, message, transferred_fds, cancellation_tokens=cancellation_tokens, popen_factory=popen_factory, poll_interval=poll_interval)
    send_result(result)
    return result

def shell_escalate_server_decision_run(decision: ShellEscalationDecision, *, send_response: Any, receive_super_exec: Any, prepare_exec: Any, send_result: Any, cancellation_tokens: Iterable[CancellationToken]=(), popen_factory: Any=subprocess.Popen, poll_interval: float=0.05) -> ShellSuperExecResult | None:
    execution = shell_escalate_server_decision_send_response(decision, send_response)
    return shell_escalate_server_continue_after_response(execution, receive_super_exec=receive_super_exec, prepare_exec=prepare_exec, send_result=send_result, cancellation_tokens=cancellation_tokens, popen_factory=popen_factory, poll_interval=poll_interval)

def shell_escalate_server_request_run(request: ShellEscalateRequest | Mapping[str, Any], *, determine_action: Any, send_response: Any, receive_super_exec: Any, prepare_exec: Any, send_result: Any, cancellation_tokens: Iterable[CancellationToken]=(), popen_factory: Any=subprocess.Popen, poll_interval: float=0.05) -> ShellSuperExecResult | None:
    if not isinstance(request, ShellEscalateRequest):
        request = ShellEscalateRequest.from_mapping(request)
    policy_input = shell_escalate_policy_input_from_request(request)
    decision = shell_escalate_decision_for_request(request, determine_action)

    def prepare_with_request(execution: ShellEscalationExecution) -> ShellPreparedExec:
        prepared = prepare_exec(policy_input.program, policy_input.argv, policy_input.workdir, dict(request.env), execution)
        if not isinstance(prepared, ShellPreparedExec):
            raise TypeError('prepare_exec must return ShellPreparedExec')
        return prepared
    return shell_escalate_server_decision_run(decision, send_response=send_response, receive_super_exec=receive_super_exec, prepare_exec=prepare_with_request, send_result=send_result, cancellation_tokens=cancellation_tokens, popen_factory=popen_factory, poll_interval=poll_interval)

def shell_escalation_decision_after_review(review_decision: ReviewDecision | str, needs_escalation: bool, escalation_execution: ShellEscalationExecution, *, rejection_message: str | None=None, guardian_rejection_message: str | None=None, guardian_timeout_message: str='Timed out waiting for approval.') -> ShellEscalationDecision:
    review_decision = ReviewDecision.from_mapping(review_decision)
    if review_decision.type in {'approved', 'approved_for_session', 'approved_execpolicy_amendment'}:
        return shell_escalation_decision_for_approved_review(needs_escalation, escalation_execution)
    if review_decision.type == 'network_policy_amendment':
        amendment = review_decision.network_policy_amendment
        if amendment is not None and amendment.action is NetworkPolicyRuleAction.ALLOW:
            return shell_escalation_decision_for_approved_review(needs_escalation, escalation_execution)
        return ShellEscalationDecision.deny('User denied execution')
    if review_decision.type == 'denied':
        return ShellEscalationDecision.deny(rejection_message or guardian_rejection_message or 'User denied execution')
    if review_decision.type == 'timed_out':
        return ShellEscalationDecision.deny(guardian_timeout_message)
    if review_decision.type == 'abort':
        return ShellEscalationDecision.deny('User cancelled execution')
    raise ValueError(f'unknown review decision type: {review_decision.type}')

def shell_escalation_policy_plan(evaluation: InterceptedExecPolicyEvaluation, *, sandbox_permissions: SandboxPermissions, permission_profile: PermissionProfile, prompt_permissions: AdditionalPermissionProfile | None=None) -> ShellEscalationPolicyPlan:
    if not isinstance(evaluation, InterceptedExecPolicyEvaluation):
        raise TypeError('evaluation must be InterceptedExecPolicyEvaluation')
    sandbox_permissions = SandboxPermissions(sandbox_permissions)
    if not isinstance(permission_profile, PermissionProfile):
        raise TypeError('permission_profile must be PermissionProfile')
    if prompt_permissions is not None and (not isinstance(prompt_permissions, AdditionalPermissionProfile)):
        raise TypeError('prompt_permissions must be AdditionalPermissionProfile or None')
    driven_by_policy = decision_driven_by_policy(evaluation.matched_rules, evaluation.decision)
    needs_escalation = sandbox_permissions.requires_escalated_permissions() or driven_by_policy
    decision_source = DecisionSource.PREFIX_RULE if driven_by_policy else DecisionSource.UNMATCHED_COMMAND_FALLBACK
    escalation_execution = ShellEscalationExecution.unsandboxed() if decision_source is DecisionSource.PREFIX_RULE else shell_request_escalation_execution(sandbox_permissions, permission_profile, prompt_permissions)
    return ShellEscalationPolicyPlan(decision=evaluation.decision, decision_source=decision_source, needs_escalation=needs_escalation, escalation_execution=escalation_execution, prompt_permissions=prompt_permissions)

def _intercepted_exec_policy_rules(policy: Any) -> tuple[Any, ...]:
    if policy is None:
        return ()
    if isinstance(policy, Mapping):
        rules = policy.get('rules', policy.get('prefix_rules', policy.get('prefixRules', ())))
        return tuple(rules or ())
    rules = getattr(policy, 'rules', None)
    if rules is not None:
        return tuple(rules)
    prefix_rules = getattr(policy, 'prefix_rules', None)
    if prefix_rules is not None:
        return tuple(prefix_rules)
    if isinstance(policy, (tuple, list)):
        return tuple(policy)
    return ()

def _intercepted_exec_policy_host_executables(policy: Any) -> Mapping[str, tuple[str, ...]]:
    if policy is None:
        return {}
    if isinstance(policy, Mapping):
        raw = policy.get('host_executables', policy.get('hostExecutables', {}))
    else:
        raw = getattr(policy, 'host_executables', {})
    if not isinstance(raw, Mapping):
        return {}
    result: dict[str, tuple[str, ...]] = {}
    for name, paths in raw.items():
        if isinstance(paths, (str, bytes)):
            result[str(name)] = (str(paths),)
        elif isinstance(paths, Iterable):
            result[str(name)] = tuple((str(path) for path in paths))
    return result

def _match_intercepted_exec_prefix_rules(command: tuple[str, ...], rules: tuple[Any, ...]) -> tuple[Mapping[str, Any], ...]:
    matches: list[Mapping[str, Any]] = []
    for rule in rules:
        parsed = _runtime_prefix_rule_from_object(rule)
        if parsed is None:
            continue
        pattern, decision, justification = parsed
        prefix = _runtime_prefix_rule_matched_prefix(pattern, command)
        if prefix is None:
            continue
        data: dict[str, Any] = {'matchedPrefix': list(prefix), 'decision': getattr(decision, 'value', decision)}
        if justification:
            data['justification'] = justification
        matches.append({'prefixRuleMatch': data})
    return tuple(matches)

def _runtime_prefix_rule_from_object(rule: Any) -> tuple[tuple[str | tuple[str, ...], ...], Any, str | None] | None:
    from pycodex.execpolicy import Decision, ExecPolicyPrefixRule
    if isinstance(rule, ExecPolicyPrefixRule):
        return (rule.pattern, rule.decision, rule.justification)
    if isinstance(rule, Mapping):
        pattern = rule.get('pattern')
        decision = rule.get('decision')
        justification = rule.get('justification')
    else:
        pattern = getattr(rule, 'pattern', None)
        decision = getattr(rule, 'decision', None)
        justification = getattr(rule, 'justification', None)
    if pattern is None or decision is None:
        return None
    try:
        parsed_pattern = tuple((tuple((str(choice) for choice in token)) if isinstance(token, (tuple, list)) else str(token) for token in pattern))
        parsed_decision = Decision(str(getattr(decision, 'value', decision)))
    except (TypeError, ValueError):
        return None
    parsed_justification = justification if isinstance(justification, str) and justification else None
    return (parsed_pattern, parsed_decision, parsed_justification)

def _runtime_prefix_rule_matched_prefix(pattern: tuple[str | tuple[str, ...], ...], command: tuple[str, ...]) -> tuple[str, ...] | None:
    if len(command) < len(pattern):
        return None
    matched: list[str] = []
    for pattern_token, command_token in zip(pattern, command, strict=False):
        if isinstance(pattern_token, tuple):
            if command_token not in pattern_token:
                return None
            matched.append(command_token)
            continue
        if command_token != pattern_token:
            return None
        matched.append(command_token)
    return tuple(matched)

def _resolved_host_executable_for_command(command: tuple[str, ...], host_executables: Mapping[str, tuple[str, ...]]) -> str | None:
    if not command or not _is_unix_absolute_path(command[0]):
        return None
    basename = Path(command[0]).name
    allowed_paths = host_executables.get(basename)
    if allowed_paths is None:
        return None
    return command[0] if command[0] in allowed_paths else None

def _intercepted_exec_heuristic_command(command: tuple[str, ...]) -> tuple[str, ...]:
    if command and _is_unix_absolute_path(command[0]):
        return (Path(command[0]).name, *command[1:])
    return command

def _is_unix_absolute_path(path: str) -> bool:
    return path.startswith('/') or os.path.isabs(path)

def _render_unix_intercepted_exec_fallback_decision(command: tuple[str, ...], context: InterceptedExecPolicyContext, *, used_complex_parsing: bool) -> Any:
    from pycodex.execpolicy import Decision
    from pycodex.shell_command import command_might_be_dangerous, is_known_safe_command
    if is_known_safe_command(command) and (not used_complex_parsing) and (context.approval_policy is AskForApproval.UNLESS_TRUSTED):
        return Decision.ALLOW
    if command_might_be_dangerous(command):
        if context.approval_policy is AskForApproval.NEVER:
            if context.permission_profile.type in {'disabled', 'external'}:
                return Decision.ALLOW
            return Decision.FORBIDDEN
        return Decision.PROMPT
    if context.approval_policy in {AskForApproval.NEVER, AskForApproval.ON_FAILURE}:
        return Decision.ALLOW
    if context.approval_policy is AskForApproval.UNLESS_TRUSTED:
        return Decision.PROMPT
    if context.file_system_sandbox_policy.kind in {FileSystemSandboxKind.UNRESTRICTED, FileSystemSandboxKind.EXTERNAL_SANDBOX}:
        return Decision.ALLOW
    if context.sandbox_permissions.requests_sandbox_override():
        return Decision.PROMPT
    return Decision.ALLOW

def _prefix_rule_match_with_resolved_program(match: Mapping[str, Any], program: str) -> Mapping[str, Any]:
    if 'prefixRuleMatch' not in match:
        return match
    data = dict(match['prefixRuleMatch'])
    data['resolvedProgram'] = str(program)
    return {'prefixRuleMatch': data}

def _runtime_policy_match_decision(match: Mapping[str, Any]) -> Any | None:
    from pycodex.execpolicy import Decision
    data = match.get('prefixRuleMatch', match)
    if not isinstance(data, Mapping):
        return None
    decision = data.get('decision')
    try:
        return Decision(str(getattr(decision, 'value', decision)))
    except ValueError:
        return None

def shell_approval_keys(req: ShellRequest) -> tuple[ShellApprovalKey, ...]:
    if not isinstance(req, ShellRequest):
        raise TypeError('req must be ShellRequest')
    return (ShellApprovalKey(canonicalize_command_for_approval(req.command), req.cwd, req.sandbox_permissions, req.additional_permissions),)

def shell_permission_request_payload(req: ShellRequest) -> PermissionRequestPayload:
    if not isinstance(req, ShellRequest):
        raise TypeError('req must be ShellRequest')
    return PermissionRequestPayload.bash(req.hook_command, req.justification)

def shell_network_approval_spec(req: ShellRequest, *, call_id: str, tool_name: ToolName | str) -> NetworkApprovalSpec | None:
    if not isinstance(req, ShellRequest):
        raise TypeError('req must be ShellRequest')
    network = managed_network_for_runtime(req.network, req.sandbox_permissions)
    if network is None:
        return None
    return NetworkApprovalSpec(network, NetworkApprovalMode.IMMEDIATE, GuardianNetworkAccessTrigger(call_id, flat_tool_name(tool_name), req.command, req.cwd, req.sandbox_permissions, req.additional_permissions, req.justification, None), req.hook_command)

def disable_powershell_profile_for_elevated_windows_sandbox(command: tuple[str, ...] | list[str], shell_type: ShellType | None, sandbox: SandboxType, windows_sandbox_level: WindowsSandboxLevel) -> tuple[str, ...]:
    command_tuple = _string_tuple(command, 'command')
    if shell_type is not None and (not isinstance(shell_type, ShellType)):
        shell_type = ShellType(str(shell_type))
    if not isinstance(sandbox, SandboxType):
        sandbox = SandboxType(sandbox)
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))
    if shell_type is not ShellType.POWERSHELL or sandbox is not SandboxType.WINDOWS_RESTRICTED_TOKEN or windows_sandbox_level is not WindowsSandboxLevel.ELEVATED or (not command_tuple):
        return command_tuple
    if any((arg.lower() == '-noprofile' for arg in command_tuple[1:])):
        return command_tuple
    return (command_tuple[0], '-NoProfile', *command_tuple[1:])

def maybe_wrap_shell_lc_with_snapshot(command: tuple[str, ...] | list[str], session_shell: Shell, cwd: str | Path, explicit_env_overrides: Mapping[str, str], env: Mapping[str, str], *, is_windows: bool=False) -> tuple[str, ...]:
    command_tuple = _string_tuple(command, 'command')
    if not isinstance(session_shell, Shell):
        raise TypeError('session_shell must be Shell')
    if not isinstance(is_windows, bool):
        raise TypeError('is_windows must be a bool')
    if is_windows:
        return command_tuple
    snapshot = session_shell.shell_snapshot
    if snapshot is None:
        return command_tuple
    snapshot_path = getattr(snapshot, 'path', None)
    snapshot_cwd = getattr(snapshot, 'cwd', None)
    if not isinstance(snapshot_path, Path) or not isinstance(snapshot_cwd, Path):
        raise TypeError('shell snapshot must expose Path path and cwd')
    if not snapshot_path.exists():
        return command_tuple
    cwd_path = Path(cwd)
    if not paths_match_after_normalization(snapshot_cwd, cwd_path):
        return command_tuple
    if len(command_tuple) < 3 or command_tuple[1] != '-lc':
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
    trailing_args = ''.join((f" '{shell_single_quote(arg)}'" for arg in command_tuple[3:]))
    if exports:
        rewritten_script = f"{captures}\n\nif . '{quoted_snapshot_path}' >/dev/null 2>&1; then :; fi\n\n{exports}\n\nexec '{original_shell}' -c '{original_script}'{trailing_args}"
    else:
        rewritten_script = f"if . '{quoted_snapshot_path}' >/dev/null 2>&1; then :; fi\n\nexec '{original_shell}' -c '{original_script}'{trailing_args}"
    return (str(session_shell.shell_path), '-c', rewritten_script)

def join_shell_blocks(blocks: tuple[str, ...] | list[str]) -> str:
    if not isinstance(blocks, (tuple, list)):
        raise TypeError('blocks must be a tuple or list')
    for block in blocks:
        if not isinstance(block, str):
            raise TypeError('blocks must contain strings')
    return '\n'.join((block for block in blocks if block))

def is_valid_shell_variable_name(name: str) -> bool:
    if not isinstance(name, str):
        raise TypeError('name must be a string')
    if not name:
        return False
    first = name[0]
    if first != '_' and (not (first.isascii() and first.isalpha())):
        return False
    return all((character == '_' or (character.isascii() and character.isalnum()) for character in name[1:]))

def shell_single_quote(input: str) -> str:
    if not isinstance(input, str):
        raise TypeError('input must be a string')
    return input.replace("'", '\'"\'"\'')

from .unix_escalation import (
    CandidateCommands,
    CoreShellActionProvider,
    DecisionSource,
    ParsedShellCommand,
    PreparedUnifiedExecZshFork,
    commands_for_intercepted_exec_policy,
    evaluate_intercepted_exec_policy,
    extract_shell_script,
    prepare_unified_exec_zsh_fork,
    shell_request_escalation_execution,
    try_run_zsh_fork,
)
from . import zsh_fork_backend
