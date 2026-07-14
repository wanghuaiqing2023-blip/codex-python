"""Core exec helpers ported from ``codex-rs/core/src/exec.rs``.

The full Rust file owns process spawning and sandbox integration.  Python's
runtime-facing pieces are still being assembled elsewhere, so this module ports
the reusable exec boundary: constants, capture/expiration policy, output
aggregation, timeout finalization, and sandbox-denial heuristics.
"""

from __future__ import annotations

import asyncio
import fnmatch
import os
import sys
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path, PureWindowsPath
from typing import Any, Awaitable, Callable, Mapping, MutableMapping, Sequence

from pycodex.protocol import (
    ExecToolCallOutput,
    FileSystemSandboxKind,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
    SandboxPolicy,
    StreamOutput,
    WindowsSandboxLevel,
)

from .sandbox_tags import SandboxType, get_platform_sandbox, should_require_platform_sandbox
from .spawn import CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR


DEFAULT_EXEC_COMMAND_TIMEOUT_MS = 10_000
SIGKILL_CODE = 9
TIMEOUT_CODE = 64
EXIT_CODE_SIGNAL_BASE = 128
EXEC_TIMEOUT_EXIT_CODE = 124
CANCELLATION_TERMINATION_GRACE_PERIOD_MS = 50
READ_CHUNK_SIZE = 8192
AGGREGATE_BUFFER_INITIAL_CAPACITY = 8 * 1024
EXEC_OUTPUT_MAX_BYTES = 1024 * 1024
MAX_EXEC_OUTPUT_DELTAS_PER_CALL = 10_000
IO_DRAIN_TIMEOUT_MS = 2_000

SANDBOX_DENIED_KEYWORDS = (
    "operation not permitted",
    "permission denied",
    "read-only file system",
    "seccomp",
    "sandbox",
    "landlock",
    "failed to write file",
)
QUICK_REJECT_EXIT_CODES = (2, 126, 127)


def windows_sandbox_uses_elevated_backend(
    windows_sandbox_level: WindowsSandboxLevel | str,
    proxy_enforced: bool,
) -> bool:
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))
    if not isinstance(proxy_enforced, bool):
        raise TypeError("proxy_enforced must be a bool")
    return proxy_enforced or windows_sandbox_level is WindowsSandboxLevel.ELEVATED


def select_process_exec_tool_sandbox_type(
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    network_sandbox_policy: NetworkSandboxPolicy,
    windows_sandbox_level: WindowsSandboxLevel | str,
    enforce_managed_network: bool,
) -> SandboxType:
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    if not isinstance(network_sandbox_policy, NetworkSandboxPolicy):
        network_sandbox_policy = NetworkSandboxPolicy.parse(str(network_sandbox_policy))
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))
    if not isinstance(enforce_managed_network, bool):
        raise TypeError("enforce_managed_network must be a bool")
    if not should_require_platform_sandbox(
        file_system_sandbox_policy,
        network_sandbox_policy,
        enforce_managed_network,
    ):
        return SandboxType.NONE
    sandbox = get_platform_sandbox(windows_sandbox_level is not WindowsSandboxLevel.DISABLED)
    return sandbox or SandboxType.NONE


def should_use_windows_restricted_token_sandbox(
    sandbox_type: str,
    sandbox_policy: SandboxPolicy,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
) -> bool:
    if not isinstance(sandbox_policy, SandboxPolicy):
        raise TypeError("sandbox_policy must be a SandboxPolicy")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    return (
        _is_windows_restricted_token_sandbox(sandbox_type)
        and file_system_sandbox_policy.kind is FileSystemSandboxKind.RESTRICTED
        and sandbox_policy.type not in {"danger-full-access", "external-sandbox"}
    )


def unsupported_windows_restricted_token_sandbox_reason(
    sandbox_type: str,
    sandbox_policy: SandboxPolicy,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    network_sandbox_policy: NetworkSandboxPolicy,
    sandbox_policy_cwd: Path | str,
    windows_sandbox_level: WindowsSandboxLevel | str,
) -> str | None:
    try:
        if (
            windows_sandbox_level is WindowsSandboxLevel.ELEVATED
            or str(windows_sandbox_level).lower() == WindowsSandboxLevel.ELEVATED.value
        ):
            resolve_windows_elevated_filesystem_overrides(
                sandbox_type,
                sandbox_policy,
                file_system_sandbox_policy,
                network_sandbox_policy,
                sandbox_policy_cwd,
                True,
            )
        else:
            resolve_windows_restricted_token_filesystem_overrides(
                sandbox_type,
                sandbox_policy,
                file_system_sandbox_policy,
                network_sandbox_policy,
                sandbox_policy_cwd,
                windows_sandbox_level,
            )
    except ValueError as exc:
        return str(exc)
    return None


def resolve_windows_elevated_filesystem_overrides(
    sandbox_type: str,
    sandbox_policy: SandboxPolicy,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    network_sandbox_policy: NetworkSandboxPolicy,
    sandbox_policy_cwd: Path | str,
    use_windows_elevated_backend: bool,
) -> WindowsSandboxFilesystemOverrides | None:
    if not isinstance(sandbox_policy, SandboxPolicy):
        raise TypeError("sandbox_policy must be a SandboxPolicy")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    if not isinstance(network_sandbox_policy, NetworkSandboxPolicy):
        network_sandbox_policy = NetworkSandboxPolicy.parse(str(network_sandbox_policy))
    if not isinstance(use_windows_elevated_backend, bool):
        raise TypeError("use_windows_elevated_backend must be a bool")
    if not _is_windows_restricted_token_sandbox(sandbox_type) or not use_windows_elevated_backend:
        return None
    if not should_use_windows_restricted_token_sandbox(
        sandbox_type,
        sandbox_policy,
        file_system_sandbox_policy,
    ):
        raise ValueError(
            "windows sandbox backend cannot enforce "
            f"file_system={_filesystem_kind_debug(file_system_sandbox_policy.kind)}, "
            f"network={_network_policy_debug(network_sandbox_policy)}, "
            f"legacy_policy={_sandbox_policy_debug(sandbox_policy)}; refusing to run unsandboxed"
        )

    cwd = Path(sandbox_policy_cwd)
    read_roots_override = (
        None
        if _windows_policy_has_root_read_access(file_system_sandbox_policy)
        else tuple(_normalize_windows_override_path(path) for path in file_system_sandbox_policy.get_readable_roots_with_cwd(cwd))
    )
    legacy_writable_roots = sandbox_policy.get_writable_roots_with_cwd(cwd)
    split_writable_roots = file_system_sandbox_policy.get_writable_roots_with_cwd(cwd)
    if _has_reopened_writable_descendant(split_writable_roots):
        raise ValueError(
            "windows elevated sandbox cannot reopen writable descendants under read-only carveouts directly; "
            "refusing to run unsandboxed"
        )
    additional_deny_read_paths = _additional_deny_read_paths(file_system_sandbox_policy, cwd)
    additional_deny_write_paths = (
        _additional_deny_write_paths(legacy_writable_roots, split_writable_roots)
        if file_system_sandbox_policy.needs_direct_runtime_enforcement(network_sandbox_policy, cwd)
        else ()
    )
    if read_roots_override is None and not additional_deny_read_paths and not additional_deny_write_paths:
        return None
    return WindowsSandboxFilesystemOverrides(
        read_roots_override=read_roots_override,
        additional_deny_read_paths=additional_deny_read_paths,
        additional_deny_write_paths=additional_deny_write_paths,
    )


def resolve_windows_restricted_token_filesystem_overrides(
    sandbox_type: str,
    sandbox_policy: SandboxPolicy,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
    network_sandbox_policy: NetworkSandboxPolicy,
    sandbox_policy_cwd: Path | str,
    windows_sandbox_level: WindowsSandboxLevel | str,
) -> WindowsSandboxFilesystemOverrides | None:
    if not isinstance(sandbox_policy, SandboxPolicy):
        raise TypeError("sandbox_policy must be a SandboxPolicy")
    if not isinstance(file_system_sandbox_policy, FileSystemSandboxPolicy):
        raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy")
    if not isinstance(network_sandbox_policy, NetworkSandboxPolicy):
        network_sandbox_policy = NetworkSandboxPolicy.parse(str(network_sandbox_policy))
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))
    if not _is_windows_restricted_token_sandbox(sandbox_type) or windows_sandbox_level is WindowsSandboxLevel.ELEVATED:
        return None

    needs_direct_runtime_enforcement = (
        False
        if _matches_legacy_file_system_policy(sandbox_policy, file_system_sandbox_policy)
        else file_system_sandbox_policy.needs_direct_runtime_enforcement(
            network_sandbox_policy,
            sandbox_policy_cwd,
        )
    )
    should_use_restricted_token = should_use_windows_restricted_token_sandbox(
        sandbox_type,
        sandbox_policy,
        file_system_sandbox_policy,
    )
    if should_use_restricted_token and not needs_direct_runtime_enforcement:
        return None
    if not should_use_restricted_token:
        raise ValueError(
            "windows sandbox backend cannot enforce "
            f"file_system={_filesystem_kind_debug(file_system_sandbox_policy.kind)}, "
            f"network={_network_policy_debug(network_sandbox_policy)}, "
            f"legacy_policy={_sandbox_policy_debug(sandbox_policy)}; refusing to run unsandboxed"
        )
    if not _windows_policy_has_root_read_access(file_system_sandbox_policy):
        raise ValueError(
            "windows unelevated restricted-token sandbox cannot enforce split filesystem read restrictions directly; "
            "refusing to run unsandboxed"
        )
    if _has_deny_read_entry(file_system_sandbox_policy):
        raise ValueError(
            "windows unelevated restricted-token sandbox cannot enforce deny-read restrictions directly; "
            "refusing to run unsandboxed"
        )
    if _windows_policy_has_root_write_access(file_system_sandbox_policy) and _has_explicit_read_carveout(file_system_sandbox_policy):
        raise ValueError(
            "windows unelevated restricted-token sandbox cannot enforce split writable root sets directly; "
            "refusing to run unsandboxed"
        )

    cwd = Path(sandbox_policy_cwd)
    legacy_writable_roots = sandbox_policy.get_writable_roots_with_cwd(cwd)
    split_writable_roots = file_system_sandbox_policy.get_writable_roots_with_cwd(cwd)
    legacy_roots_by_path = {_normalize_windows_override_path(root.root): root for root in legacy_writable_roots}
    split_roots_by_path = {_normalize_windows_override_path(root.root): root for root in split_writable_roots}
    if set(legacy_roots_by_path) != set(split_roots_by_path):
        raise ValueError(
            "windows unelevated restricted-token sandbox cannot enforce split writable root sets directly; "
            "refusing to run unsandboxed"
        )

    additional_deny_write_paths = _additional_deny_write_paths(legacy_writable_roots, split_writable_roots)

    if not additional_deny_write_paths:
        return None
    return WindowsSandboxFilesystemOverrides(
        additional_deny_write_paths=tuple(dict.fromkeys(additional_deny_write_paths)),
    )


class ExecCapturePolicy(str, Enum):
    SHELL_TOOL = "shell_tool"
    FULL_BUFFER = "full_buffer"

    @classmethod
    def default(cls) -> "ExecCapturePolicy":
        return cls.SHELL_TOOL

    def retained_bytes_cap(self) -> int | None:
        if self is ExecCapturePolicy.SHELL_TOOL:
            return EXEC_OUTPUT_MAX_BYTES
        return None

    def io_drain_timeout(self) -> timedelta:
        return timedelta(milliseconds=IO_DRAIN_TIMEOUT_MS)

    def uses_expiration(self) -> bool:
        return self is ExecCapturePolicy.SHELL_TOOL


class ExecExpirationKind(str, Enum):
    TIMEOUT = "timeout"
    DEFAULT_TIMEOUT = "default_timeout"
    CANCELLATION = "cancellation"
    TIMEOUT_OR_CANCELLATION = "timeout_or_cancellation"


class ExecExpirationOutcome(str, Enum):
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


async def _cancel_and_drain_tasks(tasks: Sequence[asyncio.Task[Any]]) -> None:
    """Cancel task-race losers and wait until their coroutines have exited."""

    for task in tasks:
        if not task.done():
            task.cancel()
    if tasks:
        await asyncio.gather(*tasks, return_exceptions=True)


@dataclass(slots=True)
class CancellationToken:
    """Minimal asyncio cancellation token for exec expiration wiring."""

    _event: asyncio.Event = field(default_factory=asyncio.Event)
    _parents: tuple["CancellationToken", ...] = ()

    def cancel(self) -> None:
        self._event.set()

    def is_cancelled(self) -> bool:
        return self._event.is_set() or any(parent.is_cancelled() for parent in self._parents)

    async def cancelled(self) -> None:
        if self.is_cancelled():
            self.cancel()
            return
        if not self._parents:
            await self._event.wait()
            return
        tasks = [asyncio.create_task(self._event.wait())]
        tasks.extend(asyncio.create_task(parent.cancelled()) for parent in self._parents)
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            for task in done:
                await task
            self.cancel()
        finally:
            await _cancel_and_drain_tasks(tasks)


@dataclass(frozen=True, slots=True)
class ExecExpiration:
    kind: ExecExpirationKind
    timeout: timedelta | None = None
    _cancellation: CancellationToken | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ExecExpirationKind):
            object.__setattr__(self, "kind", ExecExpirationKind(self.kind))
        if self.timeout is not None:
            _validate_non_negative_timeout(self.timeout)
        if self._cancellation is not None and not isinstance(self._cancellation, CancellationToken):
            raise TypeError("cancellation must be a CancellationToken")

    @classmethod
    def from_timeout_ms(cls, timeout_ms: int | None) -> "ExecExpiration":
        if timeout_ms is None:
            return cls.default_timeout()
        if isinstance(timeout_ms, bool) or timeout_ms < 0:
            raise ValueError("timeout_ms must be a non-negative integer or None")
        return cls.timeout_after(timedelta(milliseconds=timeout_ms))

    @classmethod
    def timeout_after(cls, timeout: timedelta) -> "ExecExpiration":
        _validate_non_negative_timeout(timeout)
        return cls(ExecExpirationKind.TIMEOUT, timeout=timeout)

    @classmethod
    def default_timeout(cls) -> "ExecExpiration":
        return cls(ExecExpirationKind.DEFAULT_TIMEOUT, _cancellation=None)

    @classmethod
    def timeout_or_cancellation(
        cls,
        timeout: timedelta,
        cancellation: CancellationToken,
    ) -> "ExecExpiration":
        _validate_non_negative_timeout(timeout)
        if not isinstance(cancellation, CancellationToken):
            raise TypeError("cancellation must be a CancellationToken")
        return cls(ExecExpirationKind.TIMEOUT_OR_CANCELLATION, timeout=timeout, _cancellation=cancellation)

    def timeout_ms(self) -> int | None:
        if self.kind is ExecExpirationKind.TIMEOUT and self.timeout is not None:
            return _timedelta_to_millis(self.timeout)
        if self.kind is ExecExpirationKind.DEFAULT_TIMEOUT:
            return DEFAULT_EXEC_COMMAND_TIMEOUT_MS
        if self.kind is ExecExpirationKind.TIMEOUT_OR_CANCELLATION and self.timeout is not None:
            return _timedelta_to_millis(self.timeout)
        return None

    def with_cancellation(self, cancellation: CancellationToken) -> "ExecExpiration":
        if not isinstance(cancellation, CancellationToken):
            raise TypeError("cancellation must be a CancellationToken")
        if self.kind is ExecExpirationKind.TIMEOUT and self.timeout is not None:
            return ExecExpiration.timeout_or_cancellation(self.timeout, cancellation)
        if self.kind is ExecExpirationKind.DEFAULT_TIMEOUT:
            return ExecExpiration.timeout_or_cancellation(
                timedelta(milliseconds=DEFAULT_EXEC_COMMAND_TIMEOUT_MS),
                cancellation,
            )
        if self.kind is ExecExpirationKind.CANCELLATION and self.cancellation is not None:
            return ExecExpiration.cancellation(cancel_when_either(self.cancellation, cancellation))
        if self.kind is ExecExpirationKind.TIMEOUT_OR_CANCELLATION and self.timeout is not None and self.cancellation is not None:
            return ExecExpiration.timeout_or_cancellation(
                self.timeout,
                cancel_when_either(self.cancellation, cancellation),
            )
        return ExecExpiration.cancellation(cancellation)

    async def wait_with_outcome(self) -> ExecExpirationOutcome:
        if self.kind is ExecExpirationKind.TIMEOUT:
            await asyncio.sleep((self.timeout or timedelta()).total_seconds())
            return ExecExpirationOutcome.TIMED_OUT
        if self.kind is ExecExpirationKind.DEFAULT_TIMEOUT:
            await asyncio.sleep(DEFAULT_EXEC_COMMAND_TIMEOUT_MS / 1000)
            return ExecExpirationOutcome.TIMED_OUT
        if self.kind is ExecExpirationKind.CANCELLATION:
            await _required_cancellation(self).cancelled()
            return ExecExpirationOutcome.CANCELLED

        cancellation = _required_cancellation(self)
        sleep_task = asyncio.create_task(asyncio.sleep((self.timeout or timedelta()).total_seconds()))
        cancel_task = asyncio.create_task(cancellation.cancelled())
        tasks = (cancel_task, sleep_task)
        try:
            done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
            return ExecExpirationOutcome.CANCELLED if cancel_task in done else ExecExpirationOutcome.TIMED_OUT
        finally:
            await _cancel_and_drain_tasks(tasks)


class _ExecExpirationCancellationAccessor:
    def __get__(self, instance: ExecExpiration | None, owner: type[ExecExpiration]):
        if instance is not None:
            return instance._cancellation

        def factory(cancellation: CancellationToken) -> ExecExpiration:
            if not isinstance(cancellation, CancellationToken):
                raise TypeError("cancellation must be a CancellationToken")
            return owner(ExecExpirationKind.CANCELLATION, _cancellation=cancellation)

        return factory


ExecExpiration.cancellation = _ExecExpirationCancellationAccessor()  # type: ignore[assignment]


@dataclass(frozen=True, slots=True)
class ExecParams:
    command: tuple[str, ...]
    cwd: Path
    expiration: ExecExpiration = field(default_factory=ExecExpiration.default_timeout)
    capture_policy: ExecCapturePolicy = ExecCapturePolicy.SHELL_TOOL
    env: Mapping[str, str] = field(default_factory=dict)
    network: Any = None
    sandbox_permissions: Any = None
    windows_sandbox_level: Any = None
    windows_sandbox_private_desktop: bool = False
    justification: str | None = None
    arg0: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.command, (str, bytes)) or not isinstance(self.command, Sequence):
            raise TypeError("command must be a sequence of strings")
        command = tuple(self.command)
        if not all(isinstance(part, str) for part in command):
            raise TypeError("command must contain strings")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "cwd", Path(self.cwd))
        if not isinstance(self.capture_policy, ExecCapturePolicy):
            object.__setattr__(self, "capture_policy", ExecCapturePolicy(self.capture_policy))
        if not isinstance(self.expiration, ExecExpiration):
            raise TypeError("expiration must be an ExecExpiration")
        object.__setattr__(self, "env", dict(self.env))
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError("windows_sandbox_private_desktop must be a bool")


@dataclass(frozen=True, slots=True)
class ExecRequest:
    """Portable exec request after sandbox transformation.

    Rust source: ``codex-rs/core/src/sandboxing/mod.rs::ExecRequest``.
    """

    command: tuple[str, ...]
    cwd: Path
    env: Mapping[str, str] = field(default_factory=dict)
    network: Any = None
    expiration: ExecExpiration = field(default_factory=ExecExpiration.default_timeout)
    capture_policy: ExecCapturePolicy = ExecCapturePolicy.SHELL_TOOL
    sandbox: SandboxType = SandboxType.NONE
    windows_sandbox_policy_cwd: Path | None = None
    windows_sandbox_level: WindowsSandboxLevel | str = WindowsSandboxLevel.DISABLED
    windows_sandbox_private_desktop: bool = False
    permission_profile: Any = None
    file_system_sandbox_policy: FileSystemSandboxPolicy | None = None
    network_sandbox_policy: NetworkSandboxPolicy = NetworkSandboxPolicy.ENABLED
    windows_sandbox_filesystem_overrides: WindowsSandboxFilesystemOverrides | None = None
    arg0: str | None = None
    exec_server_env_config: Any = None

    def __post_init__(self) -> None:
        if isinstance(self.command, (str, bytes)) or not isinstance(self.command, Sequence):
            raise TypeError("command must be a sequence of strings")
        command = tuple(self.command)
        if not all(isinstance(part, str) for part in command):
            raise TypeError("command must contain strings")
        object.__setattr__(self, "command", command)
        object.__setattr__(self, "cwd", Path(self.cwd))
        object.__setattr__(self, "env", dict(self.env))
        if not isinstance(self.expiration, ExecExpiration):
            raise TypeError("expiration must be an ExecExpiration")
        if not isinstance(self.capture_policy, ExecCapturePolicy):
            object.__setattr__(self, "capture_policy", ExecCapturePolicy(self.capture_policy))
        if not isinstance(self.sandbox, SandboxType):
            object.__setattr__(self, "sandbox", SandboxType(str(self.sandbox)))
        policy_cwd = self.windows_sandbox_policy_cwd
        object.__setattr__(self, "windows_sandbox_policy_cwd", Path(policy_cwd) if policy_cwd is not None else Path(self.cwd))
        if not isinstance(self.windows_sandbox_level, WindowsSandboxLevel):
            object.__setattr__(self, "windows_sandbox_level", WindowsSandboxLevel.parse(str(self.windows_sandbox_level)))
        if not isinstance(self.windows_sandbox_private_desktop, bool):
            raise TypeError("windows_sandbox_private_desktop must be a bool")
        if self.file_system_sandbox_policy is not None and not isinstance(self.file_system_sandbox_policy, FileSystemSandboxPolicy):
            raise TypeError("file_system_sandbox_policy must be a FileSystemSandboxPolicy or None")
        if not isinstance(self.network_sandbox_policy, NetworkSandboxPolicy):
            object.__setattr__(self, "network_sandbox_policy", NetworkSandboxPolicy.parse(str(self.network_sandbox_policy)))
        if self.windows_sandbox_filesystem_overrides is not None and not isinstance(
            self.windows_sandbox_filesystem_overrides,
            WindowsSandboxFilesystemOverrides,
        ):
            raise TypeError("windows_sandbox_filesystem_overrides must be WindowsSandboxFilesystemOverrides or None")
        if self.arg0 is not None and not isinstance(self.arg0, str):
            raise TypeError("arg0 must be a string or None")


@dataclass(frozen=True, slots=True)
class WindowsSandboxFilesystemOverrides:
    read_roots_override: tuple[Path, ...] | None = None
    read_roots_include_platform_defaults: bool = False
    write_roots_override: tuple[Path, ...] | None = None
    additional_deny_read_paths: tuple[Path, ...] = ()
    additional_deny_write_paths: tuple[Path, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "read_roots_override", _path_tuple_or_none(self.read_roots_override))
        object.__setattr__(self, "write_roots_override", _path_tuple_or_none(self.write_roots_override))
        object.__setattr__(self, "additional_deny_read_paths", _path_tuple(self.additional_deny_read_paths))
        object.__setattr__(self, "additional_deny_write_paths", _path_tuple(self.additional_deny_write_paths))
        if not isinstance(self.read_roots_include_platform_defaults, bool):
            raise TypeError("read_roots_include_platform_defaults must be a bool")


@dataclass(frozen=True, slots=True)
class RawExecToolCallOutput:
    exit_code: int | None
    stdout: StreamOutput[bytes]
    stderr: StreamOutput[bytes]
    aggregated_output: StreamOutput[bytes]
    timed_out: bool = False
    signal: int | None = None


@dataclass(frozen=True, slots=True)
class RawOutputExecutionPlan:
    """Pure dispatch plan for ``get_raw_output_result``.

    Rust source: ``codex-rs/core/src/exec.rs::get_raw_output_result``.
    """

    backend: str
    timeout_ms: int | None = None
    use_windows_elevated_backend: bool = False
    proxy_enforced: bool = False
    windows_sandbox_policy_cwd: Path | None = None
    windows_sandbox_filesystem_overrides: WindowsSandboxFilesystemOverrides | None = None

    def __post_init__(self) -> None:
        if self.backend not in {"exec", "windows_sandbox"}:
            raise ValueError("backend must be exec or windows_sandbox")
        if self.timeout_ms is not None:
            if isinstance(self.timeout_ms, bool) or not isinstance(self.timeout_ms, int):
                raise TypeError("timeout_ms must be an int or None")
            if self.timeout_ms < 0:
                raise ValueError("timeout_ms must be non-negative")
        if not isinstance(self.use_windows_elevated_backend, bool):
            raise TypeError("use_windows_elevated_backend must be a bool")
        if not isinstance(self.proxy_enforced, bool):
            raise TypeError("proxy_enforced must be a bool")
        if self.windows_sandbox_policy_cwd is not None:
            object.__setattr__(self, "windows_sandbox_policy_cwd", Path(self.windows_sandbox_policy_cwd))
        if self.windows_sandbox_filesystem_overrides is not None and not isinstance(
            self.windows_sandbox_filesystem_overrides,
            WindowsSandboxFilesystemOverrides,
        ):
            raise TypeError("windows_sandbox_filesystem_overrides must be WindowsSandboxFilesystemOverrides or None")


class ExecSandboxError(Exception):
    def __init__(self, kind: str, output: ExecToolCallOutput | None = None, signal: int | None = None) -> None:
        self.kind = kind
        self.output = output
        self.signal = signal
        super().__init__(kind if signal is None else f"{kind}: {signal}")


class ExecSandboxTimeout(ExecSandboxError):
    def __init__(self, output: ExecToolCallOutput) -> None:
        super().__init__("timeout", output=output)


class ExecSandboxDenied(ExecSandboxError):
    def __init__(self, output: ExecToolCallOutput) -> None:
        super().__init__("denied", output=output)


class ExecSandboxSignal(ExecSandboxError):
    def __init__(self, signal: int) -> None:
        super().__init__("signal", signal=signal)


def cancel_when_either(first: CancellationToken, second: CancellationToken) -> CancellationToken:
    if not isinstance(first, CancellationToken):
        raise TypeError("first must be a CancellationToken")
    if not isinstance(second, CancellationToken):
        raise TypeError("second must be a CancellationToken")
    combined = CancellationToken(_parents=(first, second))
    if first.is_cancelled() or second.is_cancelled():
        combined.cancel()
    return combined


def exec_params_from_request(request: ExecRequest) -> ExecParams:
    """Project an ``ExecRequest`` back to ``ExecParams`` for execution.

    Rust source: ``codex-rs/core/src/exec.rs::execute_exec_request``.
    """

    if not isinstance(request, ExecRequest):
        raise TypeError("request must be an ExecRequest")
    return ExecParams(
        command=request.command,
        cwd=request.cwd,
        expiration=request.expiration,
        capture_policy=request.capture_policy,
        env=request.env,
        network=request.network,
        sandbox_permissions=None,
        windows_sandbox_level=request.windows_sandbox_level,
        windows_sandbox_private_desktop=request.windows_sandbox_private_desktop,
        justification=None,
        arg0=request.arg0,
    )


def raw_output_execution_plan(
    params: ExecParams,
    sandbox: SandboxType | str,
    windows_sandbox_policy_cwd: Path | str,
    windows_sandbox_filesystem_overrides: WindowsSandboxFilesystemOverrides | None = None,
    *,
    target_os: str | None = None,
) -> RawOutputExecutionPlan:
    """Plan the Rust ``get_raw_output_result`` backend selection.

    The real subprocess implementation remains a separate runtime slice.
    """

    if not isinstance(params, ExecParams):
        raise TypeError("params must be an ExecParams")
    if not isinstance(sandbox, SandboxType):
        sandbox = SandboxType(str(sandbox))
    if windows_sandbox_filesystem_overrides is not None and not isinstance(
        windows_sandbox_filesystem_overrides,
        WindowsSandboxFilesystemOverrides,
    ):
        raise TypeError("windows_sandbox_filesystem_overrides must be WindowsSandboxFilesystemOverrides or None")
    platform_name = sys.platform if target_os is None else target_os
    if platform_name == "win32" and sandbox is SandboxType.WINDOWS_RESTRICTED_TOKEN:
        proxy_enforced = params.network is not None
        return RawOutputExecutionPlan(
            backend="windows_sandbox",
            timeout_ms=params.expiration.timeout_ms() if params.capture_policy.uses_expiration() else None,
            use_windows_elevated_backend=windows_sandbox_uses_elevated_backend(
                params.windows_sandbox_level,
                proxy_enforced,
            ),
            proxy_enforced=proxy_enforced,
            windows_sandbox_policy_cwd=Path(windows_sandbox_policy_cwd),
            windows_sandbox_filesystem_overrides=windows_sandbox_filesystem_overrides,
        )
    return RawOutputExecutionPlan(backend="exec")


def raw_output_from_windows_sandbox_capture(
    *,
    exit_code: int,
    stdout: bytes | bytearray | memoryview,
    stderr: bytes | bytearray | memoryview,
    timed_out: bool,
    capture_policy: ExecCapturePolicy = ExecCapturePolicy.SHELL_TOOL,
) -> RawExecToolCallOutput:
    """Convert a Windows sandbox capture into raw exec output.

    Rust source: ``codex-rs/core/src/exec.rs::exec_windows_sandbox``.
    """

    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        raise TypeError("exit_code must be an int")
    if not isinstance(timed_out, bool):
        raise TypeError("timed_out must be a bool")
    if not isinstance(capture_policy, ExecCapturePolicy):
        capture_policy = ExecCapturePolicy(capture_policy)
    stdout_text = bytes(stdout)
    stderr_text = bytes(stderr)
    max_bytes = capture_policy.retained_bytes_cap()
    if max_bytes is not None:
        stdout_text = stdout_text[:max_bytes]
        stderr_text = stderr_text[:max_bytes]
    stdout_output = StreamOutput(stdout_text)
    stderr_output = StreamOutput(stderr_text)
    return RawExecToolCallOutput(
        exit_code=exit_code,
        stdout=stdout_output,
        stderr=stderr_output,
        aggregated_output=aggregate_output(stdout_output, stderr_output, max_bytes),
        timed_out=timed_out,
    )


async def run_raw_exec_subprocess(
    params: ExecParams,
    network_sandbox_policy: NetworkSandboxPolicy = NetworkSandboxPolicy.ENABLED,
    after_spawn: Callable[[], None] | None = None,
    stdout_stream: Callable[[bytes, bool], Awaitable[None] | None] | None = None,
) -> RawExecToolCallOutput:
    """Run the non-sandbox subprocess path for Rust ``exec``.

    Rust source: ``codex-rs/core/src/exec.rs::exec``.
    """

    if not isinstance(params, ExecParams):
        raise TypeError("params must be an ExecParams")
    if not isinstance(network_sandbox_policy, NetworkSandboxPolicy):
        network_sandbox_policy = NetworkSandboxPolicy.parse(str(network_sandbox_policy))
    if after_spawn is not None and not callable(after_spawn):
        raise TypeError("after_spawn must be callable or None")
    if stdout_stream is not None and not callable(stdout_stream):
        raise TypeError("stdout_stream must be callable or None")
    if not params.command:
        raise OSError("command args are empty")

    env = os.environ.copy()
    env.update(params.env)
    apply_to_env = getattr(params.network, "apply_to_env", None)
    if callable(apply_to_env):
        apply_to_env(env)
    if not network_sandbox_policy.is_enabled():
        env[CODEX_SANDBOX_NETWORK_DISABLED_ENV_VAR] = "1"

    process = await asyncio.create_subprocess_exec(
        *params.command,
        cwd=params.cwd,
        env=env,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    if after_spawn is not None:
        after_spawn()
    return await consume_subprocess_output(process, params.expiration, params.capture_policy, stdout_stream)


async def consume_subprocess_output(
    process: asyncio.subprocess.Process,
    expiration: ExecExpiration,
    capture_policy: ExecCapturePolicy,
    stdout_stream: Callable[[bytes, bool], Awaitable[None] | None] | None = None,
) -> RawExecToolCallOutput:
    """Consume subprocess output according to the configured capture policy.

    Rust source: ``codex-rs/core/src/exec.rs::consume_output``.
    """

    if not isinstance(expiration, ExecExpiration):
        raise TypeError("expiration must be an ExecExpiration")
    if not isinstance(capture_policy, ExecCapturePolicy):
        capture_policy = ExecCapturePolicy(capture_policy)
    if stdout_stream is not None and not callable(stdout_stream):
        raise TypeError("stdout_stream must be callable or None")
    if process.stdout is None:
        raise OSError("stdout pipe was unexpectedly not available")
    if process.stderr is None:
        raise OSError("stderr pipe was unexpectedly not available")

    retained_bytes_cap = capture_policy.retained_bytes_cap()
    stdout_task = asyncio.create_task(read_output(process.stdout, stdout_stream, False, retained_bytes_cap))
    stderr_task = asyncio.create_task(read_output(process.stderr, stdout_stream, True, retained_bytes_cap))
    timed_out = False
    cancelled = False
    try:
        if capture_policy.uses_expiration():
            outcome = await _wait_process_or_expiration(process, expiration)
            if outcome is ExecExpirationOutcome.TIMED_OUT:
                timed_out = True
                process.kill()
                await process.wait()
            elif outcome is ExecExpirationOutcome.CANCELLED:
                cancelled = True
                process.terminate()
                try:
                    await asyncio.wait_for(
                        process.wait(),
                        CANCELLATION_TERMINATION_GRACE_PERIOD_MS / 1000,
                    )
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()
        else:
            await process.wait()

        stdout_output = await _await_stream_output(stdout_task, capture_policy.io_drain_timeout())
        stderr_output = await _await_stream_output(stderr_task, capture_policy.io_drain_timeout())
    finally:
        await _cancel_and_drain_tasks((stdout_task, stderr_task))

    exit_code = 1 if cancelled else process.returncode
    if timed_out:
        exit_code = EXIT_CODE_SIGNAL_BASE + TIMEOUT_CODE
    return RawExecToolCallOutput(
        exit_code=exit_code,
        stdout=stdout_output,
        stderr=stderr_output,
        aggregated_output=aggregate_output(stdout_output, stderr_output, retained_bytes_cap),
        timed_out=timed_out,
    )


async def _wait_process_or_expiration(
    process: asyncio.subprocess.Process,
    expiration: ExecExpiration,
) -> ExecExpirationOutcome | None:
    wait_task = asyncio.create_task(process.wait())
    expiration_task = asyncio.create_task(expiration.wait_with_outcome())
    tasks = (wait_task, expiration_task)
    try:
        done, _pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        if wait_task in done:
            await wait_task
            return None
        return await expiration_task
    finally:
        await _cancel_and_drain_tasks(tasks)


async def _await_stream_output(
    task: asyncio.Task[StreamOutput[bytes]],
    timeout: timedelta,
) -> StreamOutput[bytes]:
    try:
        return await asyncio.wait_for(task, timeout.total_seconds())
    except asyncio.TimeoutError:
        task.cancel()
        return StreamOutput(b"")


def extract_create_process_as_user_error_code(err: str) -> str | None:
    """Extract the Windows sandbox CreateProcessAsUserW error code.

    Rust source: ``codex-rs/core/src/exec.rs::extract_create_process_as_user_error_code``.
    """

    if not isinstance(err, str):
        raise TypeError("err must be a string")
    marker = "CreateProcessAsUserW failed: "
    start = err.find(marker)
    if start < 0:
        return None
    tail = err[start + len(marker) :]
    digits = []
    for char in tail:
        if not char.isascii() or not char.isdigit():
            break
        digits.append(char)
    return "".join(digits) or None


def windowsapps_path_kind(path: str) -> str:
    """Classify WindowsApps command paths for sandbox spawn telemetry.

    Rust source: ``codex-rs/core/src/exec.rs::windowsapps_path_kind``.
    """

    if not isinstance(path, str):
        raise TypeError("path must be a string")
    lower = path.lower()
    if "\\program files\\windowsapps\\" in lower:
        return "windowsapps_package"
    if "\\appdata\\local\\microsoft\\windowsapps\\" in lower:
        return "windowsapps_alias"
    if "\\windowsapps\\" in lower:
        return "windowsapps_other"
    return "other"


def windows_sandbox_spawn_failure_metric_tags(
    command_path: str | None,
    windows_sandbox_level: WindowsSandboxLevel | str,
    err: str,
) -> tuple[tuple[str, str], ...] | None:
    """Build metric tags for Windows sandbox spawn failures.

    Rust source: ``codex-rs/core/src/exec.rs::record_windows_sandbox_spawn_failure``.
    """

    error_code = extract_create_process_as_user_error_code(err)
    if error_code is None:
        return None
    if command_path is not None and not isinstance(command_path, str):
        raise TypeError("command_path must be a string or None")
    if not isinstance(windows_sandbox_level, WindowsSandboxLevel):
        windows_sandbox_level = WindowsSandboxLevel.parse(str(windows_sandbox_level))
    path = command_path or "unknown"
    exe = PureWindowsPath(path).name or "unknown"
    level = "elevated" if windows_sandbox_level is WindowsSandboxLevel.ELEVATED else "legacy"
    return (
        ("error_code", error_code),
        ("path_kind", windowsapps_path_kind(path)),
        ("exe", exe.lower()),
        ("level", level),
    )


def append_capped(dst: bytearray, src: bytes | bytearray | memoryview, max_bytes: int) -> None:
    if len(dst) >= max_bytes:
        return
    remaining = max_bytes - len(dst)
    dst.extend(bytes(src)[:remaining])


async def read_output(
    reader: Any,
    stream: Callable[[bytes, bool], Awaitable[None] | None] | None = None,
    is_stderr: bool = False,
    max_bytes: int | None = EXEC_OUTPUT_MAX_BYTES,
) -> StreamOutput[bytes]:
    """Drain an async byte reader while retaining at most ``max_bytes`` bytes.

    Rust source: ``codex-rs/core/src/exec.rs::read_output``.
    """

    if max_bytes is not None:
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an int or None")
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")

    retained = bytearray()
    emitted_deltas = 0
    while True:
        chunk = await reader.read(READ_CHUNK_SIZE)
        if not chunk:
            break
        data = bytes(chunk)
        if stream is not None and emitted_deltas < MAX_EXEC_OUTPUT_DELTAS_PER_CALL:
            maybe_awaitable = stream(data, is_stderr)
            if maybe_awaitable is not None:
                await maybe_awaitable
            emitted_deltas += 1
        if max_bytes is None:
            retained.extend(data)
        else:
            append_capped(retained, data, max_bytes)
        # Keep draining to EOF even after the retained buffer is full. This
        # mirrors Rust and prevents producer back-pressure on bounded pipes.

    return StreamOutput(bytes(retained))


def aggregate_output(
    stdout: StreamOutput[bytes],
    stderr: StreamOutput[bytes],
    max_bytes: int | None,
) -> StreamOutput[bytes]:
    if max_bytes is None:
        return StreamOutput(bytes(stdout.text) + bytes(stderr.text))
    if max_bytes < 0:
        raise ValueError("max_bytes must be non-negative")

    stdout_text = bytes(stdout.text)
    stderr_text = bytes(stderr.text)
    total_len = len(stdout_text) + len(stderr_text)
    if total_len <= max_bytes:
        return StreamOutput(stdout_text + stderr_text)

    want_stdout = min(len(stdout_text), max_bytes // 3)
    stderr_take = min(len(stderr_text), max_bytes - want_stdout)
    remaining = max_bytes - want_stdout - stderr_take
    stdout_take = want_stdout + min(remaining, len(stdout_text) - want_stdout)
    return StreamOutput(stdout_text[:stdout_take] + stderr_text[:stderr_take])


def finalize_exec_result(
    raw_output: RawExecToolCallOutput,
    sandbox_type: str,
    duration: timedelta,
) -> ExecToolCallOutput:
    timed_out = raw_output.timed_out
    if raw_output.signal is not None:
        if raw_output.signal == TIMEOUT_CODE:
            timed_out = True
        else:
            raise ExecSandboxSignal(raw_output.signal)

    exit_code = raw_output.exit_code if raw_output.exit_code is not None else -1
    if timed_out:
        exit_code = EXEC_TIMEOUT_EXIT_CODE

    exec_output = ExecToolCallOutput(
        exit_code=exit_code,
        stdout=raw_output.stdout.from_utf8_lossy(),
        stderr=raw_output.stderr.from_utf8_lossy(),
        aggregated_output=raw_output.aggregated_output.from_utf8_lossy(),
        duration=duration,
        timed_out=timed_out,
    )
    if timed_out:
        raise ExecSandboxTimeout(exec_output)
    if is_likely_sandbox_denied(sandbox_type, exec_output):
        raise ExecSandboxDenied(exec_output)
    return exec_output


def is_likely_sandbox_denied(sandbox_type: str, exec_output: ExecToolCallOutput) -> bool:
    if str(sandbox_type).lower() in {"none", "sandbox_type.none"} or exec_output.exit_code == 0:
        return False

    sections = (
        exec_output.stderr.text,
        exec_output.stdout.text,
        exec_output.aggregated_output.text,
    )
    if any(keyword in section.lower() for section in sections for keyword in SANDBOX_DENIED_KEYWORDS):
        return True
    if exec_output.exit_code in QUICK_REJECT_EXIT_CODES:
        return False
    if str(sandbox_type).lower() in {"linuxseccomp", "linux_seccomp"} and exec_output.exit_code == EXIT_CODE_SIGNAL_BASE + 31:
        return True
    return False


def unified_exec_sandbox_denial_message(
    sandbox_type: str,
    has_exited: bool,
    exit_code: int | None,
    text: str,
) -> str | None:
    """Return the Rust unified-exec sandbox denial message, if detected."""
    if not isinstance(text, str):
        raise TypeError("text must be a string")
    if str(sandbox_type).lower() in {"none", "sandbox_type.none"} or not has_exited:
        return None
    resolved_exit_code = -1 if exit_code is None else exit_code
    exec_output = ExecToolCallOutput(
        exit_code=resolved_exit_code,
        stderr=StreamOutput.new(text),
        aggregated_output=StreamOutput.new(text),
    )
    if not is_likely_sandbox_denied(sandbox_type, exec_output):
        return None
    if text:
        from pycodex.core.tools.context import formatted_truncate_text
        from pycodex.core.unified_exec import UNIFIED_EXEC_OUTPUT_MAX_TOKENS
        from pycodex.protocol import TruncationPolicyConfig

        return formatted_truncate_text(text, TruncationPolicyConfig.tokens(UNIFIED_EXEC_OUTPUT_MAX_TOKENS))
    return f"Process exited with code {resolved_exit_code}"


def apply_network_to_env(env: Mapping[str, str], network: Any) -> dict[str, str]:
    merged: MutableMapping[str, str] = dict(env)
    apply_to_env = getattr(network, "apply_to_env", None)
    if callable(apply_to_env):
        apply_to_env(merged)
    return dict(merged)


def _required_cancellation(expiration: ExecExpiration) -> CancellationToken:
    if expiration.cancellation is None:
        raise ValueError("cancellation token is required")
    return expiration.cancellation


def _timedelta_to_millis(value: timedelta) -> int:
    _validate_non_negative_timeout(value)
    return int(value.total_seconds() * 1000)


def _validate_non_negative_timeout(value: timedelta) -> None:
    if not isinstance(value, timedelta):
        raise TypeError("timeout must be a timedelta")
    if value.total_seconds() < 0:
        raise ValueError("timeout must be non-negative")


def _is_windows_restricted_token_sandbox(sandbox_type: str) -> bool:
    value = getattr(sandbox_type, "value", sandbox_type)
    normalized = str(value).lower().replace("-", "_")
    return normalized in {
        "windows_sandbox",
        "windowsrestrictedtoken",
        "windows_restricted_token",
        "sandboxtype.windows_restricted_token",
    }


def _filesystem_kind_debug(kind: FileSystemSandboxKind) -> str:
    if kind is FileSystemSandboxKind.RESTRICTED:
        return "Restricted"
    if kind is FileSystemSandboxKind.UNRESTRICTED:
        return "Unrestricted"
    if kind is FileSystemSandboxKind.EXTERNAL_SANDBOX:
        return "ExternalSandbox"
    return str(kind)


def _network_policy_debug(policy: NetworkSandboxPolicy) -> str:
    return "Enabled" if policy is NetworkSandboxPolicy.ENABLED else "Restricted"


def _sandbox_policy_debug(policy: SandboxPolicy) -> str:
    if policy.type == "external-sandbox":
        return f"ExternalSandbox {{ network_access: {_network_policy_debug(policy.network_access)} }}"
    if policy.type == "danger-full-access":
        return "DangerFullAccess"
    if policy.type == "read-only":
        return f"ReadOnly {{ network_access: {str(bool(policy.network_access)).lower()} }}"
    if policy.type == "workspace-write":
        return (
            "WorkspaceWrite { "
            f"writable_roots: {list(policy.writable_roots)!r}, "
            f"network_access: {str(bool(policy.network_access)).lower()}, "
            f"exclude_tmpdir_env_var: {str(policy.exclude_tmpdir_env_var).lower()}, "
            f"exclude_slash_tmp: {str(policy.exclude_slash_tmp).lower()} "
            "}"
        )
    return repr(policy)


def _matches_legacy_file_system_policy(
    sandbox_policy: SandboxPolicy,
    file_system_sandbox_policy: FileSystemSandboxPolicy,
) -> bool:
    if sandbox_policy.type in {"danger-full-access", "external-sandbox"}:
        return False
    return file_system_sandbox_policy == FileSystemSandboxPolicy.from_legacy_sandbox_policy(sandbox_policy)


def _windows_policy_has_root_read_access(file_system_sandbox_policy: FileSystemSandboxPolicy) -> bool:
    for entry in file_system_sandbox_policy.entries:
        if (
            entry.path.type == "special"
            and entry.path.value is not None
            and entry.path.value.kind == "root"
            and entry.access.can_read()
        ):
            return True
    return False


def _windows_policy_has_root_write_access(file_system_sandbox_policy: FileSystemSandboxPolicy) -> bool:
    for entry in file_system_sandbox_policy.entries:
        if (
            entry.path.type == "special"
            and entry.path.value is not None
            and entry.path.value.kind == "root"
            and entry.access.can_write()
        ):
            return True
    return False


def _has_explicit_read_carveout(file_system_sandbox_policy: FileSystemSandboxPolicy) -> bool:
    return any(entry.path.type == "path" and entry.access.can_read() and not entry.access.can_write() for entry in file_system_sandbox_policy.entries)


def _has_deny_read_entry(file_system_sandbox_policy: FileSystemSandboxPolicy) -> bool:
    return any(not entry.access.can_read() for entry in file_system_sandbox_policy.entries)


def _additional_deny_read_paths(file_system_sandbox_policy: FileSystemSandboxPolicy, cwd: Path | str) -> tuple[Path, ...]:
    deny_paths = [
        _normalize_windows_override_path(entry.path.path)
        for entry in file_system_sandbox_policy.entries
        if entry.path.type == "path" and entry.path.path is not None and not entry.access.can_read()
    ]
    for pattern in file_system_sandbox_policy.get_unreadable_globs_with_cwd(cwd):
        deny_paths.extend(_existing_glob_matches(pattern))
    return tuple(dict.fromkeys(deny_paths))


def _additional_deny_write_paths(legacy_writable_roots: Sequence[Any], split_writable_roots: Sequence[Any]) -> tuple[Path, ...]:
    legacy_roots_by_path = {_normalize_windows_override_path(root.root): root for root in legacy_writable_roots}
    deny_paths: list[Path] = []
    for split_root in split_writable_roots:
        root_path = _normalize_windows_override_path(split_root.root)
        legacy_root = legacy_roots_by_path.get(root_path)
        legacy_read_only = (
            {_normalize_windows_override_path(path) for path in legacy_root.read_only_subpaths}
            if legacy_root is not None
            else set()
        )
        for read_only_subpath in split_root.read_only_subpaths:
            normalized = _normalize_windows_override_path(read_only_subpath)
            if normalized not in legacy_read_only:
                deny_paths.append(normalized)
    return tuple(dict.fromkeys(deny_paths))


def _has_reopened_writable_descendant(writable_roots: Sequence[Any]) -> bool:
    for writable_root in writable_roots:
        for read_only_subpath in writable_root.read_only_subpaths:
            normalized_read_only = _normalize_windows_override_path(read_only_subpath)
            for candidate in writable_roots:
                if candidate.root == writable_root.root:
                    continue
                if _path_starts_with(_normalize_windows_override_path(candidate.root), normalized_read_only):
                    return True
    return False


def _normalize_windows_override_path(path: Path | str) -> Path:
    return Path(path).resolve(strict=False)


def _path_starts_with(path: Path, prefix: Path) -> bool:
    try:
        path.relative_to(prefix)
        return True
    except ValueError:
        return False


def _existing_glob_matches(pattern: str) -> list[Path]:
    scan_root = _glob_scan_root(pattern)
    if not scan_root.exists():
        return []
    matches: list[Path] = []
    candidates = [scan_root]
    if scan_root.is_dir():
        candidates.extend(scan_root.rglob("*"))
    for candidate in candidates:
        if fnmatch.fnmatch(str(candidate), pattern):
            matches.append(_normalize_windows_override_path(candidate))
    return matches


def _glob_scan_root(pattern: str) -> Path:
    first_glob_index = next(
        (index for index, character in enumerate(pattern) if character in "*?["),
        len(pattern),
    )
    literal_prefix = pattern[:first_glob_index]
    separator_index = max(literal_prefix.rfind("/"), literal_prefix.rfind("\\"))
    if separator_index == -1:
        return Path(".")
    if separator_index == 0:
        return Path(literal_prefix[:1])
    if separator_index > 0 and literal_prefix[separator_index - 1] == ":":
        return Path(literal_prefix[: separator_index + 1])
    return Path(literal_prefix[:separator_index])


def _path_tuple(paths: Sequence[Path | str]) -> tuple[Path, ...]:
    if isinstance(paths, (str, bytes)):
        raise TypeError("paths must be a sequence of paths")
    return tuple(Path(path) for path in paths)


def _path_tuple_or_none(paths: Sequence[Path | str] | None) -> tuple[Path, ...] | None:
    if paths is None:
        return None
    return _path_tuple(paths)


__all__ = [
    "AGGREGATE_BUFFER_INITIAL_CAPACITY",
    "CANCELLATION_TERMINATION_GRACE_PERIOD_MS",
    "DEFAULT_EXEC_COMMAND_TIMEOUT_MS",
    "EXEC_OUTPUT_MAX_BYTES",
    "EXEC_TIMEOUT_EXIT_CODE",
    "EXIT_CODE_SIGNAL_BASE",
    "IO_DRAIN_TIMEOUT_MS",
    "MAX_EXEC_OUTPUT_DELTAS_PER_CALL",
    "QUICK_REJECT_EXIT_CODES",
    "READ_CHUNK_SIZE",
    "SANDBOX_DENIED_KEYWORDS",
    "SIGKILL_CODE",
    "TIMEOUT_CODE",
    "CancellationToken",
    "ExecCapturePolicy",
    "ExecExpiration",
    "ExecExpirationKind",
    "ExecExpirationOutcome",
    "ExecParams",
    "ExecRequest",
    "ExecSandboxDenied",
    "ExecSandboxError",
    "ExecSandboxSignal",
    "ExecSandboxTimeout",
    "RawExecToolCallOutput",
    "RawOutputExecutionPlan",
    "WindowsSandboxFilesystemOverrides",
    "aggregate_output",
    "append_capped",
    "apply_network_to_env",
    "cancel_when_either",
    "exec_params_from_request",
    "extract_create_process_as_user_error_code",
    "finalize_exec_result",
    "is_likely_sandbox_denied",
    "raw_output_execution_plan",
    "raw_output_from_windows_sandbox_capture",
    "read_output",
    "resolve_windows_elevated_filesystem_overrides",
    "resolve_windows_restricted_token_filesystem_overrides",
    "run_raw_exec_subprocess",
    "select_process_exec_tool_sandbox_type",
    "should_use_windows_restricted_token_sandbox",
    "unsupported_windows_restricted_token_sandbox_reason",
    "unified_exec_sandbox_denial_message",
    "windows_sandbox_uses_elevated_backend",
    "windows_sandbox_spawn_failure_metric_tags",
    "windowsapps_path_kind",
]
