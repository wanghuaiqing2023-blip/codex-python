"""Core exec helpers ported from ``codex-rs/core/src/exec.rs``.

The full Rust file owns process spawning and sandbox integration.  Python's
runtime-facing pieces are still being assembled elsewhere, so this module ports
the reusable exec boundary: constants, capture/expiration policy, output
aggregation, timeout finalization, and sandbox-denial heuristics.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, MutableMapping, Sequence

from pycodex.protocol import ExecToolCallOutput, StreamOutput


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
        done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        for task in done:
            await task
        self.cancel()


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
        done, pending = await asyncio.wait((cancel_task, sleep_task), return_when=asyncio.FIRST_COMPLETED)
        for task in pending:
            task.cancel()
        return ExecExpirationOutcome.CANCELLED if cancel_task in done else ExecExpirationOutcome.TIMED_OUT


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


def append_capped(dst: bytearray, src: bytes | bytearray | memoryview, max_bytes: int) -> None:
    if len(dst) >= max_bytes:
        return
    remaining = max_bytes - len(dst)
    dst.extend(bytes(src)[:remaining])


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
        from pycodex.core.tool_context import formatted_truncate_text
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
    "ExecSandboxDenied",
    "ExecSandboxError",
    "ExecSandboxSignal",
    "ExecSandboxTimeout",
    "RawExecToolCallOutput",
    "WindowsSandboxFilesystemOverrides",
    "aggregate_output",
    "append_capped",
    "apply_network_to_env",
    "cancel_when_either",
    "finalize_exec_result",
    "is_likely_sandbox_denied",
    "unified_exec_sandbox_denial_message",
]
