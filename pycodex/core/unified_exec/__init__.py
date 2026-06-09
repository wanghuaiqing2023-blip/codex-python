"""Small unified-exec helpers ported from ``core/src/unified_exec``."""

from __future__ import annotations

import os
import queue
import random
import subprocess
import threading
import time
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from dataclasses import field
from typing import Any, TypeVar

from pycodex.protocol import ExecToolCallOutput


MIN_YIELD_TIME_MS = 250
MIN_EMPTY_YIELD_TIME_MS = 5_000
MAX_YIELD_TIME_MS = 30_000
DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS = 300_000
DEFAULT_MAX_OUTPUT_TOKENS = 10_000
EARLY_EXIT_GRACE_PERIOD_MS = 150
TRAILING_OUTPUT_GRACE_MS = 100
UNIFIED_EXEC_OUTPUT_MAX_BYTES = 1024 * 1024
UNIFIED_EXEC_OUTPUT_MAX_TOKENS = UNIFIED_EXEC_OUTPUT_MAX_BYTES // 4
UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES = 8192
MAX_EXEC_OUTPUT_DELTAS_PER_CALL = 10_000
MAX_UNIFIED_EXEC_PROCESSES = 64
NETWORK_ACCESS_DENIED_MESSAGE = "Network access was denied by the Codex sandbox network proxy."
LATE_NETWORK_DENIAL_GRACE_PERIOD_MS = 100
UNIFIED_EXEC_ENV = (
    ("NO_COLOR", "1"),
    ("TERM", "dumb"),
    ("LANG", "C.UTF-8"),
    ("LC_CTYPE", "C.UTF-8"),
    ("LC_ALL", "C.UTF-8"),
    ("COLORTERM", ""),
    ("PAGER", "cat"),
    ("GIT_PAGER", "cat"),
    ("GH_PAGER", "cat"),
    ("CODEX_CI", "1"),
)
_T = TypeVar("_T")
_DETERMINISTIC_PROCESS_IDS_FOR_TESTS = True


def set_deterministic_process_ids_for_tests(enabled: bool) -> None:
    """Set the default process-id mode used by test-created managers."""

    global _DETERMINISTIC_PROCESS_IDS_FOR_TESTS
    _DETERMINISTIC_PROCESS_IDS_FOR_TESTS = bool(enabled)


def deterministic_process_ids_for_tests() -> bool:
    """Return the current test default for process-id allocation."""

    return _DETERMINISTIC_PROCESS_IDS_FOR_TESTS


@dataclass(frozen=True)
class UnifiedExecContext:
    session: Any
    turn: Any
    call_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")


@dataclass(frozen=True)
class ExecCommandRequest:
    command: tuple[str, ...]
    shell_type: Any = None
    hook_command: str = ""
    process_id: int = 0
    yield_time_ms: int = MIN_YIELD_TIME_MS
    max_output_tokens: int | None = None
    cwd: Any = None
    sandbox_cwd: Any = None
    environment: Any = None
    network: Any = None
    tty: bool = True
    sandbox_permissions: Any = None
    additional_permissions: Any = None
    additional_permissions_preapproved: bool = False
    justification: str | None = None
    prefix_rule: tuple[str, ...] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "command", tuple(str(part) for part in self.command))
        if not isinstance(self.hook_command, str):
            raise TypeError("hook_command must be a string")
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an integer")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer or None")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if not isinstance(self.additional_permissions_preapproved, bool):
            raise TypeError("additional_permissions_preapproved must be a bool")
        if self.justification is not None and not isinstance(self.justification, str):
            raise TypeError("justification must be a string or None")
        if self.prefix_rule is not None:
            object.__setattr__(self, "prefix_rule", tuple(str(part) for part in self.prefix_rule))


@dataclass(frozen=True)
class WriteStdinRequest:
    process_id: int
    input: str
    yield_time_ms: int = MIN_YIELD_TIME_MS
    max_output_tokens: int | None = None
    truncation_policy: Any = None

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an integer")
        if not isinstance(self.input, str):
            raise TypeError("input must be a string")
        if isinstance(self.yield_time_ms, bool) or not isinstance(self.yield_time_ms, int):
            raise TypeError("yield_time_ms must be an integer")
        if self.max_output_tokens is not None and (
            isinstance(self.max_output_tokens, bool)
            or not isinstance(self.max_output_tokens, int)
        ):
            raise TypeError("max_output_tokens must be an integer or None")


@dataclass
class ProcessStore:
    processes: dict[int, Any] = field(default_factory=dict)
    reserved_process_ids: set[int] = field(default_factory=set)

    def remove(self, process_id: int) -> Any | None:
        self.reserved_process_ids.discard(process_id)
        return self.processes.pop(process_id, None)


def clamp_yield_time(yield_time_ms: int) -> int:
    return min(max(yield_time_ms, MIN_YIELD_TIME_MS), MAX_YIELD_TIME_MS)


def resolve_write_stdin_yield_time(chars: str, yield_time_ms: int) -> int:
    if chars == "":
        return min(
            max(yield_time_ms, MIN_EMPTY_YIELD_TIME_MS),
            DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
        )
    return clamp_yield_time(yield_time_ms)


def split_valid_utf8_prefix(buffer: bytearray) -> bytes | None:
    return split_valid_utf8_prefix_with_max(buffer, UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES)


def split_valid_utf8_prefix_with_max(buffer: bytearray, max_bytes: int) -> bytes | None:
    if not isinstance(buffer, bytearray):
        raise TypeError("buffer must be a bytearray")
    if not buffer:
        return None

    max_len = min(len(buffer), max(0, int(max_bytes)))
    split = max_len
    while split > 0:
        try:
            bytes(buffer[:split]).decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            if max_len - split > 4:
                break
            split -= 1
            continue
        prefix = bytes(buffer[:split])
        del buffer[:split]
        return prefix

    prefix = bytes(buffer[:1])
    del buffer[:1]
    return prefix


def should_emit_exec_output_delta(emitted_deltas: int) -> bool:
    if isinstance(emitted_deltas, bool) or not isinstance(emitted_deltas, int):
        raise TypeError("emitted_deltas must be an integer")
    return emitted_deltas < MAX_EXEC_OUTPUT_DELTAS_PER_CALL


def resolve_aggregated_output(buffer: "HeadTailBuffer", fallback: str) -> str:
    if not isinstance(buffer, HeadTailBuffer):
        raise TypeError("buffer must be HeadTailBuffer")
    if not isinstance(fallback, str):
        raise TypeError("fallback must be a string")
    if buffer.retained_bytes() == 0:
        return fallback
    return buffer.to_bytes().decode("utf-8", errors="replace")


def resolve_failed_aggregated_output(stdout: str, message: str) -> str:
    if not isinstance(stdout, str):
        raise TypeError("stdout must be a string")
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    if stdout == "":
        return message
    return f"{stdout}\n{message}"


@dataclass(frozen=True)
class UnifiedExecEndEventPlan:
    call_id: str
    command: tuple[str, ...]
    cwd: Any
    process_id: str | None
    source: str
    status: str
    exit_code: int
    stdout: str
    stderr: str
    aggregated_output: str
    duration_ms: int
    timed_out: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.command, tuple):
            raise TypeError("command must be a tuple")
        if self.process_id is not None and not isinstance(self.process_id, str):
            raise TypeError("process_id must be a string or None")
        if not isinstance(self.source, str):
            raise TypeError("source must be a string")
        if not isinstance(self.status, str):
            raise TypeError("status must be a string")
        if isinstance(self.exit_code, bool) or not isinstance(self.exit_code, int):
            raise TypeError("exit_code must be an integer")
        if not isinstance(self.stdout, str):
            raise TypeError("stdout must be a string")
        if not isinstance(self.stderr, str):
            raise TypeError("stderr must be a string")
        if not isinstance(self.aggregated_output, str):
            raise TypeError("aggregated_output must be a string")
        if isinstance(self.duration_ms, bool) or not isinstance(self.duration_ms, int):
            raise TypeError("duration_ms must be an integer")
        if not isinstance(self.timed_out, bool):
            raise TypeError("timed_out must be a bool")


def _unified_exec_end_event_common(
    *,
    call_id: str,
    command: Iterable[str],
    cwd: Any,
    process_id: str | int | None,
    status: str,
    exit_code: int,
    stdout: str,
    stderr: str,
    aggregated_output: str,
    duration_ms: int = 0,
) -> UnifiedExecEndEventPlan:
    return UnifiedExecEndEventPlan(
        call_id=call_id,
        command=tuple(str(part) for part in command),
        cwd=cwd,
        process_id=None if process_id is None else str(process_id),
        source="unified_exec_startup",
        status=status,
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        aggregated_output=aggregated_output,
        duration_ms=duration_ms,
        timed_out=False,
    )


def unified_exec_success_end_event_plan(
    *,
    call_id: str,
    command: Iterable[str],
    cwd: Any,
    process_id: str | int | None,
    transcript: "HeadTailBuffer",
    fallback_output: str,
    exit_code: int,
    duration_ms: int = 0,
) -> UnifiedExecEndEventPlan:
    aggregated_output = resolve_aggregated_output(transcript, fallback_output)
    return _unified_exec_end_event_common(
        call_id=call_id,
        command=command,
        cwd=cwd,
        process_id=process_id,
        status="success",
        exit_code=exit_code,
        stdout=aggregated_output,
        stderr="",
        aggregated_output=aggregated_output,
        duration_ms=duration_ms,
    )


def unified_exec_failed_end_event_plan(
    *,
    call_id: str,
    command: Iterable[str],
    cwd: Any,
    process_id: str | int | None,
    transcript: "HeadTailBuffer",
    fallback_output: str,
    message: str,
    duration_ms: int = 0,
) -> UnifiedExecEndEventPlan:
    if not isinstance(message, str):
        raise TypeError("message must be a string")
    stdout = (
        fallback_output
        if fallback_output
        else resolve_aggregated_output(transcript, fallback_output)
    )
    aggregated_output = resolve_failed_aggregated_output(stdout, message)
    return _unified_exec_end_event_common(
        call_id=call_id,
        command=command,
        cwd=cwd,
        process_id=process_id,
        status="failed",
        exit_code=-1,
        stdout=stdout,
        stderr=message,
        aggregated_output=aggregated_output,
        duration_ms=duration_ms,
    )


def should_emit_terminal_interaction(stdin: str, response_process_id: int | None) -> bool:
    if not isinstance(stdin, str):
        raise TypeError("stdin must be a string")
    if response_process_id is not None and (isinstance(response_process_id, bool) or not isinstance(response_process_id, int)):
        raise TypeError("response_process_id must be an integer or None")
    return stdin != "" or response_process_id is not None


def terminal_interaction_process_id(response_process_id: int | None, request_process_id: int) -> int:
    if response_process_id is not None and (isinstance(response_process_id, bool) or not isinstance(response_process_id, int)):
        raise TypeError("response_process_id must be an integer or None")
    if isinstance(request_process_id, bool) or not isinstance(request_process_id, int):
        raise TypeError("request_process_id must be an integer")
    return request_process_id if response_process_id is None else response_process_id


def exec_server_after_seq(next_seq: int | None) -> int | None:
    if next_seq is None:
        return None
    if isinstance(next_seq, bool) or not isinstance(next_seq, int):
        raise TypeError("next_seq must be an integer or None")
    if next_seq <= 0:
        return None
    return next_seq - 1


def exec_server_write_status_accepted(status: str) -> bool:
    if not isinstance(status, str):
        raise TypeError("status must be a string")
    return status == "Accepted"


def exec_server_write_status_marks_exited(status: str) -> bool:
    if not isinstance(status, str):
        raise TypeError("status must be a string")
    return status in {"UnknownProcess", "StdinClosed"}


def resolve_max_tokens(max_tokens: int | None) -> int:
    return DEFAULT_MAX_OUTPUT_TOKENS if max_tokens is None else max_tokens


def generate_chunk_id() -> str:
    return "".join(f"{random.randrange(16):x}" for _ in range(6))


def apply_unified_exec_env(env: dict[str, str]) -> dict[str, str]:
    merged = dict(env)
    merged.update(UNIFIED_EXEC_ENV)
    return merged


@dataclass(frozen=True)
class ExecServerEnvConfig:
    policy: Any | None
    local_policy_env: dict[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.local_policy_env, dict):
            raise TypeError("local_policy_env must be a dict")


@dataclass(frozen=True)
class ExecServerParams:
    process_id: str
    argv: tuple[str, ...]
    cwd: Any
    env_policy: Any | None
    env: dict[str, str]
    tty: bool
    pipe_stdin: bool = False
    arg0: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.process_id, str):
            raise TypeError("process_id must be a string")
        if not isinstance(self.argv, tuple):
            raise TypeError("argv must be a tuple")
        if not isinstance(self.env, dict):
            raise TypeError("env must be a dict")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if not isinstance(self.pipe_stdin, bool):
            raise TypeError("pipe_stdin must be a bool")


def env_overlay_for_exec_server(
    request_env: dict[str, str],
    local_policy_env: dict[str, str],
) -> dict[str, str]:
    return {
        key: value
        for key, value in request_env.items()
        if local_policy_env.get(key) != value
    }


def _request_env_mapping(request: Any) -> dict[str, str]:
    env = getattr(request, "env", None)
    if env is None:
        env = getattr(request, "environment", None)
    if env is None:
        return {}
    if not isinstance(env, dict):
        raise TypeError("request env must be a dict")
    return {str(key): str(value) for key, value in env.items()}


def _exec_server_env_config_fields(config: Any) -> tuple[Any | None, dict[str, str]]:
    if isinstance(config, dict):
        policy = config.get("policy")
        local_policy_env = config.get("local_policy_env", {})
    else:
        policy = getattr(config, "policy", None)
        local_policy_env = getattr(config, "local_policy_env", {})
    if not isinstance(local_policy_env, dict):
        raise TypeError("exec_server_env_config.local_policy_env must be a dict")
    return policy, {str(key): str(value) for key, value in local_policy_env.items()}


def exec_server_env_for_request(request: Any) -> tuple[Any | None, dict[str, str]]:
    request_env = _request_env_mapping(request)
    config = getattr(request, "exec_server_env_config", None)
    if config is None:
        return None, request_env
    policy, local_policy_env = _exec_server_env_config_fields(config)
    return policy, env_overlay_for_exec_server(request_env, local_policy_env)


def exec_server_process_id(process_id: int) -> str:
    return str(process_id)


def exec_server_params_for_request(
    process_id: int,
    request: Any,
    tty: bool,
) -> ExecServerParams:
    if isinstance(process_id, bool) or not isinstance(process_id, int):
        raise TypeError("process_id must be an integer")
    command = tuple(str(part) for part in (getattr(request, "command", ()) or ()))
    env_policy, env = exec_server_env_for_request(request)
    return ExecServerParams(
        process_id=exec_server_process_id(process_id),
        argv=command,
        cwd=getattr(request, "cwd", None),
        env_policy=env_policy,
        env=env,
        tty=bool(tty),
        pipe_stdin=False,
        arg0=getattr(request, "arg0", None),
    )


def _cancellation_token_is_cancelled(token: Any) -> bool:
    if token is None:
        return False
    for name in ("is_cancelled", "is_set"):
        value = getattr(token, name, None)
        if callable(value):
            return bool(value())
    value = getattr(token, "cancelled", None)
    if callable(value):
        return bool(value())
    if value is not None:
        return bool(value)
    return bool(token)


def wait_for_late_network_denial(
    network_cancelled: Any,
    *,
    grace_period_ms: int = LATE_NETWORK_DENIAL_GRACE_PERIOD_MS,
) -> bool:
    if network_cancelled is None:
        return False
    if _cancellation_token_is_cancelled(network_cancelled):
        return True
    if isinstance(grace_period_ms, bool) or not isinstance(grace_period_ms, int):
        raise TypeError("grace_period_ms must be an integer")
    if grace_period_ms <= 0:
        return _cancellation_token_is_cancelled(network_cancelled)

    deadline = time.monotonic() + (grace_period_ms / 1000.0)
    while time.monotonic() < deadline:
        if _cancellation_token_is_cancelled(network_cancelled):
            return True
        remaining = deadline - time.monotonic()
        time.sleep(min(0.01, max(remaining, 0.0)))
    return _cancellation_token_is_cancelled(network_cancelled)


def network_denial_message_for_session(
    session: Any | None = None,
    deferred: Any | None = None,
) -> str:
    if session is None:
        return NETWORK_ACCESS_DENIED_MESSAGE
    finish = getattr(session, "finish_deferred_network_approval", None)
    if not callable(finish):
        return NETWORK_ACCESS_DENIED_MESSAGE
    try:
        result = finish(deferred)
    except Exception as err:
        return str(err)
    if isinstance(result, str) and result:
        return result
    return NETWORK_ACCESS_DENIED_MESSAGE


def process_id_to_prune_from_meta(meta: Iterable[tuple[int, _T, bool]]) -> int | None:
    entries = list(meta)
    if not entries:
        return None

    protected = {
        process_id
        for process_id, _, _ in sorted(entries, key=lambda entry: entry[1], reverse=True)[:8]
    }
    least_recent = sorted(entries, key=lambda entry: entry[1])
    for process_id, _, has_exited in least_recent:
        if process_id not in protected and has_exited:
            return process_id
    for process_id, _, _ in least_recent:
        if process_id not in protected:
            return process_id
    return None


class UnifiedExecError(Exception):
    CREATE_PROCESS = "CreateProcess"
    PROCESS_FAILED = "ProcessFailed"
    UNKNOWN_PROCESS_ID = "UnknownProcessId"
    WRITE_TO_STDIN = "WriteToStdin"
    STDIN_CLOSED = "StdinClosed"
    MISSING_COMMAND_LINE = "MissingCommandLine"
    SANDBOX_DENIED = "SandboxDenied"

    def __init__(
        self,
        kind: str,
        *,
        message: str | None = None,
        process_id: int | None = None,
        output: ExecToolCallOutput | None = None,
    ) -> None:
        self.kind = kind
        self.message = message
        self.process_id = process_id
        self.output = output
        super().__init__(self._render_message())

    @classmethod
    def create_process(cls, message: str) -> "UnifiedExecError":
        return cls(cls.CREATE_PROCESS, message=message)

    @classmethod
    def process_failed(cls, message: str) -> "UnifiedExecError":
        return cls(cls.PROCESS_FAILED, message=message)

    @classmethod
    def unknown_process_id(cls, process_id: int) -> "UnifiedExecError":
        return cls(cls.UNKNOWN_PROCESS_ID, process_id=process_id)

    @classmethod
    def write_to_stdin(cls) -> "UnifiedExecError":
        return cls(cls.WRITE_TO_STDIN)

    @classmethod
    def stdin_closed(cls) -> "UnifiedExecError":
        return cls(cls.STDIN_CLOSED)

    @classmethod
    def missing_command_line(cls) -> "UnifiedExecError":
        return cls(cls.MISSING_COMMAND_LINE)

    @classmethod
    def sandbox_denied(
        cls,
        message: str,
        output: ExecToolCallOutput,
    ) -> "UnifiedExecError":
        return cls(cls.SANDBOX_DENIED, message=message, output=output)

    def _render_message(self) -> str:
        if self.kind == self.CREATE_PROCESS:
            return f"Failed to create unified exec process: {self.message or ''}"
        if self.kind == self.PROCESS_FAILED:
            return f"Unified exec process failed: {self.message or ''}"
        if self.kind == self.UNKNOWN_PROCESS_ID:
            return f"Unknown process id {self.process_id}"
        if self.kind == self.WRITE_TO_STDIN:
            return "failed to write to stdin"
        if self.kind == self.STDIN_CLOSED:
            return "stdin is closed for this session; rerun exec_command with tty=true to keep stdin open"
        if self.kind == self.MISSING_COMMAND_LINE:
            return "missing command line for unified exec request"
        if self.kind == self.SANDBOX_DENIED:
            return f"Command denied by sandbox: {self.message or ''}"
        return self.kind


class _ManagedUnifiedExecSession:
    """Small subprocess-backed session used by the Python core manager."""

    def __init__(
        self,
        process: subprocess.Popen[bytes],
        *,
        process_id: int,
        hook_command: str,
        tty: bool,
        truncation_policy: Any,
    ) -> None:
        self.process = process
        self.process_id = process_id
        self.hook_command = hook_command
        self.tty = tty
        self.truncation_policy = truncation_policy
        self._buffer = HeadTailBuffer()
        self._condition = threading.Condition()
        self._output_closed = False
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        stream = self.process.stdout
        if stream is None:
            with self._condition:
                self._output_closed = True
                self._condition.notify_all()
            return
        try:
            while True:
                chunk = stream.read(1)
                if not chunk:
                    break
                with self._condition:
                    self._buffer.push_chunk(chunk)
                    self._condition.notify_all()
        finally:
            with self._condition:
                self._output_closed = True
                self._condition.notify_all()

    def has_exited(self) -> bool:
        return self.process.poll() is not None

    def exit_code(self) -> int | None:
        return self.process.poll()

    def terminate(self) -> None:
        if self.has_exited():
            return
        self.process.terminate()

    def close(self) -> None:
        if not self.has_exited():
            return
        for stream in (self.process.stdin, self.process.stdout):
            if stream is not None and not stream.closed:
                try:
                    stream.close()
                except OSError:
                    pass

    def write(self, chars: str) -> None:
        if not self.tty:
            raise UnifiedExecError.stdin_closed()
        stdin = self.process.stdin
        if stdin is None or stdin.closed:
            raise UnifiedExecError.stdin_closed()
        if chars == "\x04":
            stdin.close()
            return
        try:
            stdin.write(chars.encode("utf-8"))
            stdin.flush()
        except BrokenPipeError as err:
            raise UnifiedExecError.stdin_closed() from err
        except OSError as err:
            raise UnifiedExecError.write_to_stdin() from err

    def snapshot(
        self,
        *,
        yield_time_ms: int,
        max_output_tokens: int | None,
        event_call_id: str,
    ) -> Any:
        start = time.monotonic()
        deadline = start + (yield_time_ms / 1000.0)
        post_exit_deadline: float | None = None
        exit_signal_received = self.has_exited()
        collected: list[bytes] = []
        with self._condition:
            while True:
                chunks = self._buffer.drain_chunks()
                if chunks:
                    collected.extend(chunks)
                    exit_signal_received = self.has_exited()
                    if self.tty and not exit_signal_received:
                        break
                    if time.monotonic() >= deadline:
                        break
                    continue

                exit_signal_received = exit_signal_received or self.has_exited()
                if exit_signal_received and self._output_closed:
                    break

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break

                if exit_signal_received:
                    now = time.monotonic()
                    if post_exit_deadline is None:
                        post_exit_deadline = now + min(
                            remaining,
                            TRAILING_OUTPUT_GRACE_MS / 1000.0,
                        )
                    wait_time = post_exit_deadline - now
                    if wait_time <= 0:
                        break
                    self._condition.wait(wait_time)
                    continue

                self._condition.wait(remaining)

            raw_output = b"".join(collected)
        wall_time_seconds = time.monotonic() - start
        exited = self.has_exited()
        exit_code = self.exit_code() if exited else None
        output_process_id = None if exited else self.process_id

        from pycodex.utils.string import approx_token_count
        from pycodex.core.tools.context import ExecCommandToolOutput

        text = raw_output.decode("utf-8", errors="replace")
        return ExecCommandToolOutput(
            event_call_id=event_call_id,
            chunk_id=generate_chunk_id(),
            wall_time_seconds=wall_time_seconds,
            raw_output=raw_output,
            truncation_policy=self.truncation_policy,
            max_output_tokens=max_output_tokens,
            process_id=output_process_id,
            exit_code=exit_code,
            original_token_count=approx_token_count(text),
            hook_command=self.hook_command,
        )


@dataclass(frozen=True)
class ProcessEntry:
    process_id: int
    process: Any
    call_id: str = ""
    hook_command: str = ""
    tty: bool = False
    last_used: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.process_id, bool) or not isinstance(self.process_id, int):
            raise TypeError("process_id must be an integer")
        if not isinstance(self.call_id, str):
            raise TypeError("call_id must be a string")
        if not isinstance(self.hook_command, str):
            raise TypeError("hook_command must be a string")
        if not isinstance(self.tty, bool):
            raise TypeError("tty must be a bool")
        if isinstance(self.last_used, bool) or not isinstance(self.last_used, (int, float)):
            raise TypeError("last_used must be a number")

    def has_exited(self) -> bool:
        value = getattr(self.process, "has_exited", None)
        if callable(value):
            value = value()
        if value is not None:
            return bool(value)
        poll = getattr(self.process, "poll", None)
        if callable(poll):
            return poll() is not None
        return bool(getattr(self.process, "exited", False))


class UnifiedExecProcessManager:
    """Small stdlib manager for unified exec process ids, sessions, and pruning."""

    def __init__(
        self,
        *,
        max_processes: int = MAX_UNIFIED_EXEC_PROCESSES,
        deterministic_process_ids: bool | None = None,
    ) -> None:
        if isinstance(max_processes, bool) or not isinstance(max_processes, int):
            raise TypeError("max_processes must be an integer")
        if max_processes <= 0:
            raise ValueError("max_processes must be positive")
        if deterministic_process_ids is None:
            deterministic_process_ids = _DETERMINISTIC_PROCESS_IDS_FOR_TESTS
        if not isinstance(deterministic_process_ids, bool):
            raise TypeError("deterministic_process_ids must be a bool")
        self.max_processes = max_processes
        self.deterministic_process_ids = deterministic_process_ids
        self._processes: dict[int, ProcessEntry] = {}
        self._reserved_process_ids: set[int] = set()

    def exec_command(self, request: Any) -> Any:
        command = tuple(getattr(request, "command", ()) or ())
        process_id = getattr(request, "process_id", None)
        if not command:
            if process_id is not None:
                self.release_process_id(process_id)
            raise UnifiedExecError.missing_command_line()
        if isinstance(process_id, bool) or not isinstance(process_id, int):
            raise TypeError("request.process_id must be an integer")

        env = apply_unified_exec_env(os.environ)
        request_env = getattr(request, "environment", None)
        if isinstance(request_env, dict):
            env.update({str(key): str(value) for key, value in request_env.items()})

        cwd = getattr(request, "cwd", None) or None
        call_id = str(getattr(request, "call_id", ""))
        tty = bool(getattr(request, "tty", False))
        hook_command = str(getattr(request, "hook_command", ""))
        truncation_policy = getattr(request, "truncation_policy", None)
        max_output_tokens = getattr(request, "max_output_tokens", None)
        yield_time_ms = clamp_yield_time(int(getattr(request, "yield_time_ms", MIN_YIELD_TIME_MS)))

        try:
            process = subprocess.Popen(
                command,
                cwd=str(cwd) if cwd is not None else None,
                env=env,
                stdin=subprocess.PIPE if tty else subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                shell=False,
            )
        except OSError as err:
            self.release_process_id(process_id)
            raise UnifiedExecError.create_process(str(err)) from err

        session = _ManagedUnifiedExecSession(
            process,
            process_id=process_id,
            hook_command=hook_command,
            tty=tty,
            truncation_policy=truncation_policy,
        )
        self.store_process(
            process_id,
            session,
            call_id=call_id,
            hook_command=hook_command,
            tty=tty,
        )
        output = session.snapshot(
            yield_time_ms=yield_time_ms,
            max_output_tokens=max_output_tokens,
            event_call_id=call_id,
        )
        if output.process_id is None and tty:
            from pycodex.core.tools.context import ExecCommandToolOutput

            output = ExecCommandToolOutput(
                event_call_id=output.event_call_id,
                chunk_id=output.chunk_id,
                wall_time_seconds=output.wall_time_seconds,
                raw_output=output.raw_output,
                truncation_policy=output.truncation_policy,
                max_output_tokens=output.max_output_tokens,
                process_id=process_id,
                exit_code=output.exit_code,
                original_token_count=output.original_token_count,
                hook_command=output.hook_command,
            )
            return output
        if output.process_id is None:
            self.release_process_id(process_id)
        return output

    def write_stdin(self, request: Any) -> Any:
        process_id = getattr(request, "process_id", None)
        if isinstance(process_id, bool) or not isinstance(process_id, int):
            raise TypeError("request.process_id must be an integer")
        entry = self.touch_process(process_id)
        if entry is None:
            raise UnifiedExecError.unknown_process_id(process_id)

        session = entry.process
        chars = str(getattr(request, "input", ""))
        if chars:
            try:
                session.write(chars)
            except UnifiedExecError:
                if not session.has_exited():
                    raise
            else:
                time.sleep(0.1)
        yield_time_ms = resolve_write_stdin_yield_time(
            chars,
            int(getattr(request, "yield_time_ms", MIN_YIELD_TIME_MS)),
        )
        output = session.snapshot(
            yield_time_ms=yield_time_ms,
            max_output_tokens=getattr(request, "max_output_tokens", None),
            event_call_id=entry.call_id,
        )
        if output.process_id is None:
            self.release_process_id(process_id)
        return output

    def allocate_process_id(self) -> int:
        while True:
            if self.deterministic_process_ids:
                process_id = max(self._reserved_process_ids, default=999) + 1
                process_id = max(process_id, 1000)
            else:
                process_id = random.randrange(1_000, 100_000)
            if process_id in self._reserved_process_ids:
                continue
            self._reserved_process_ids.add(process_id)
            return process_id

    def release_process_id(self, process_id: int) -> ProcessEntry | None:
        self._reserved_process_ids.discard(process_id)
        entry = self._processes.pop(process_id, None)
        if entry is not None:
            close = getattr(entry.process, "close", None)
            if callable(close):
                close()
        return entry

    def store_process(
        self,
        process_id: int,
        process: Any,
        *,
        call_id: str = "",
        hook_command: str = "",
        tty: bool = False,
        last_used: float | None = None,
    ) -> ProcessEntry | None:
        if last_used is None:
            last_used = time.monotonic()
        entry = ProcessEntry(
            process_id=process_id,
            process=process,
            call_id=call_id,
            hook_command=hook_command,
            tty=tty,
            last_used=last_used,
        )
        self._reserved_process_ids.add(process_id)
        self._processes[process_id] = entry
        return self.prune_processes_if_needed()

    def get_process(self, process_id: int) -> ProcessEntry | None:
        return self._processes.get(process_id)

    def touch_process(self, process_id: int, *, last_used: float | None = None) -> ProcessEntry | None:
        entry = self._processes.get(process_id)
        if entry is None:
            return None
        if last_used is None:
            last_used = time.monotonic()
        updated = ProcessEntry(
            process_id=entry.process_id,
            process=entry.process,
            call_id=entry.call_id,
            hook_command=entry.hook_command,
            tty=entry.tty,
            last_used=last_used,
        )
        self._processes[process_id] = updated
        return updated

    def prune_processes_if_needed(self) -> ProcessEntry | None:
        if len(self._processes) < self.max_processes:
            return None
        meta = [
            (process_id, entry.last_used, entry.has_exited())
            for process_id, entry in self._processes.items()
        ]
        process_id = process_id_to_prune_from_meta(meta)
        if process_id is None:
            return None
        return self.release_process_id(process_id)

    def terminate_all_processes(self) -> tuple[ProcessEntry, ...]:
        entries = tuple(self._processes.values())
        self._processes.clear()
        self._reserved_process_ids.clear()
        for entry in entries:
            terminate = getattr(entry.process, "terminate", None)
            if callable(terminate):
                terminate()
        return entries

    def process_count(self) -> int:
        return len(self._processes)

    def reserved_process_ids(self) -> frozenset[int]:
        return frozenset(self._reserved_process_ids)


@dataclass(frozen=True)
class ProcessState:
    has_exited: bool = False
    exit_code: int | None = None
    failure_message: str | None = None

    def exited(self, exit_code: int | None) -> "ProcessState":
        return ProcessState(
            has_exited=True,
            exit_code=exit_code,
            failure_message=self.failure_message,
        )

    def failed(self, message: str) -> "ProcessState":
        return ProcessState(
            has_exited=True,
            exit_code=self.exit_code,
            failure_message=message,
        )


class UnifiedExecRemoteProcessModel:
    """Pure state model for Rust ``unified_exec/process.rs`` remote process edges."""

    def __init__(
        self,
        *,
        state: ProcessState | None = None,
    ) -> None:
        if state is not None and not isinstance(state, ProcessState):
            raise TypeError("state must be ProcessState or None")
        self.state = state or ProcessState()
        self.cancelled = False
        self.terminated = False

    def has_exited(self) -> bool:
        return self.state.has_exited

    def exit_code(self) -> int | None:
        return self.state.exit_code

    def failure_message(self) -> str | None:
        return self.state.failure_message

    def signal_exit(self, exit_code: int | None) -> None:
        self.state = self.state.exited(exit_code)
        self.cancelled = True

    def terminate(self) -> None:
        self.terminated = True
        self.cancelled = True

    def fail_and_terminate(self, message: str) -> None:
        if self.state.failure_message is None:
            self.state = self.state.failed(message)
        self.terminate()

    def apply_write_status(self, status: str) -> None:
        if not isinstance(status, str):
            raise TypeError("status must be a string")
        if exec_server_write_status_accepted(status):
            return
        if exec_server_write_status_marks_exited(status):
            self.state = self.state.exited(self.state.exit_code)
            self.cancelled = True
            raise UnifiedExecError.write_to_stdin()
        if status == "Starting":
            raise UnifiedExecError.write_to_stdin()
        raise UnifiedExecError.write_to_stdin()

    def apply_read_response(
        self,
        *,
        exited: bool,
        exit_code: int | None = None,
        failure: str | None = None,
        closed: bool = False,
    ) -> None:
        if failure is not None:
            self.state = self.state.failed(failure)
            self.cancelled = True
            return
        if exited:
            self.state = self.state.exited(exit_code)
        if closed:
            self.cancelled = True


@dataclass(frozen=True)
class ProcessOutputChunk:
    transcript_chunk: bytes
    delta_chunk: str | None


def process_output_chunk(
    pending: bytearray,
    transcript: "HeadTailBuffer",
    emitted_deltas: int,
    chunk: bytes | bytearray | memoryview | Iterable[int],
) -> tuple[list[ProcessOutputChunk], int]:
    if not isinstance(pending, bytearray):
        raise TypeError("pending must be a bytearray")
    if not isinstance(transcript, HeadTailBuffer):
        raise TypeError("transcript must be HeadTailBuffer")
    if isinstance(emitted_deltas, bool) or not isinstance(emitted_deltas, int):
        raise TypeError("emitted_deltas must be an integer")
    if emitted_deltas < 0:
        raise ValueError("emitted_deltas must be non-negative")

    pending.extend(bytes(chunk))
    processed: list[ProcessOutputChunk] = []
    while True:
        prefix = split_valid_utf8_prefix(pending)
        if prefix is None:
            break
        transcript.push_chunk(prefix)
        delta_chunk = None
        if should_emit_exec_output_delta(emitted_deltas):
            delta_chunk = prefix.decode("utf-8", errors="replace")
            emitted_deltas += 1
        processed.append(ProcessOutputChunk(prefix, delta_chunk))
    return processed, emitted_deltas


def start_streaming_output(
    process: Any,
    context: UnifiedExecContext,
    transcript: "HeadTailBuffer",
) -> threading.Thread:
    """Start the background unified-exec output watcher.

    Rust source: ``codex-rs/core/src/unified_exec/async_watcher.rs::start_streaming_output``.
    The Python runtime uses a daemon thread instead of Tokio, but preserves the
    module contract: read chunks continuously, append them to the shared
    transcript, emit UTF-8-safe output deltas up to the per-call cap, and notify
    output-drained after process cancellation plus the trailing-output grace.
    """

    if not isinstance(context, UnifiedExecContext):
        raise TypeError("context must be UnifiedExecContext")
    if not isinstance(transcript, HeadTailBuffer):
        raise TypeError("transcript must be HeadTailBuffer")

    receiver = _process_output_receiver(process)
    cancellation_token = _process_cancellation_token(process)
    output_drained = _process_output_drained_notify(process)

    def run() -> None:
        pending = bytearray()
        emitted_deltas = 0
        grace_started_at: float | None = None
        while True:
            if _token_cancelled(cancellation_token):
                if grace_started_at is None:
                    grace_started_at = time.monotonic()
                elif (time.monotonic() - grace_started_at) * 1000 >= TRAILING_OUTPUT_GRACE_MS:
                    _notify_output_drained(output_drained)
                    break

            chunk = _recv_output_chunk(receiver, timeout=0.01)
            if chunk is None:
                if grace_started_at is not None:
                    continue
                if _receiver_closed(receiver):
                    _notify_output_drained(output_drained)
                    break
                continue

            processed, emitted_deltas = process_output_chunk(
                pending,
                transcript,
                emitted_deltas,
                chunk,
            )
            for output in processed:
                if output.delta_chunk is not None:
                    _send_exec_output_delta(context, output.delta_chunk)

    thread = threading.Thread(target=run, name=f"unified-exec-output-{context.call_id}", daemon=True)
    thread.start()
    return thread


def spawn_exit_watcher(
    process: Any,
    session_ref: Any,
    turn_ref: Any,
    call_id: str,
    command: Iterable[str],
    cwd: Any,
    process_id: int,
    transcript: "HeadTailBuffer",
    started_at: float | None = None,
) -> threading.Thread:
    """Start the background unified-exec exit watcher.

    Rust source: ``codex-rs/core/src/unified_exec/async_watcher.rs::spawn_exit_watcher``.
    """

    if started_at is None:
        started_at = time.monotonic()
    cancellation_token = _process_cancellation_token(process)
    output_drained = _process_output_drained_notify(process)

    def run() -> None:
        _wait_for_token_cancelled(cancellation_token)
        _wait_for_output_drained(output_drained)
        duration_ms = int(max(time.monotonic() - started_at, 0.0) * 1000)
        failure_message = _process_failure_message(process)
        if failure_message is not None:
            emit_failed_exec_end_for_unified_exec(
                session_ref,
                turn_ref,
                call_id,
                command,
                cwd,
                str(process_id),
                transcript,
                "",
                failure_message,
                duration_ms,
            )
        else:
            emit_exec_end_for_unified_exec(
                session_ref,
                turn_ref,
                call_id,
                command,
                cwd,
                str(process_id),
                transcript,
                "",
                _process_exit_code(process),
                duration_ms,
            )

    thread = threading.Thread(target=run, name=f"unified-exec-exit-{call_id}", daemon=True)
    thread.start()
    return thread


def emit_exec_end_for_unified_exec(
    session_ref: Any,
    turn_ref: Any,
    call_id: str,
    command: Iterable[str],
    cwd: Any,
    process_id: str | int | None,
    transcript: "HeadTailBuffer",
    fallback_output: str,
    exit_code: int,
    duration_ms: int = 0,
) -> UnifiedExecEndEventPlan:
    plan = unified_exec_success_end_event_plan(
        call_id=call_id,
        command=command,
        cwd=cwd,
        process_id=process_id,
        transcript=transcript,
        fallback_output=fallback_output,
        exit_code=exit_code,
        duration_ms=duration_ms,
    )
    _send_unified_exec_end_event(session_ref, turn_ref, plan)
    return plan


def emit_failed_exec_end_for_unified_exec(
    session_ref: Any,
    turn_ref: Any,
    call_id: str,
    command: Iterable[str],
    cwd: Any,
    process_id: str | int | None,
    transcript: "HeadTailBuffer",
    fallback_output: str,
    message: str,
    duration_ms: int = 0,
) -> UnifiedExecEndEventPlan:
    plan = unified_exec_failed_end_event_plan(
        call_id=call_id,
        command=command,
        cwd=cwd,
        process_id=process_id,
        transcript=transcript,
        fallback_output=fallback_output,
        message=message,
        duration_ms=duration_ms,
    )
    _send_unified_exec_end_event(session_ref, turn_ref, plan)
    return plan


def _process_output_receiver(process: Any) -> Any:
    receiver = getattr(process, "output_receiver", None)
    return receiver() if callable(receiver) else getattr(process, "output", receiver)


def _process_cancellation_token(process: Any) -> Any:
    token = getattr(process, "cancellation_token", None)
    return token() if callable(token) else getattr(process, "cancelled", token)


def _process_output_drained_notify(process: Any) -> Any:
    notify = getattr(process, "output_drained_notify", None)
    return notify() if callable(notify) else getattr(process, "output_drained", notify)


def _recv_output_chunk(receiver: Any, *, timeout: float) -> bytes | None:
    if receiver is None:
        return None
    if isinstance(receiver, queue.Queue):
        try:
            value = receiver.get(timeout=timeout)
        except queue.Empty:
            return None
        return bytes(value) if value is not None else None
    recv = getattr(receiver, "recv", None) or getattr(receiver, "get", None)
    if callable(recv):
        try:
            value = recv(timeout=timeout)
        except (TimeoutError, queue.Empty):
            return None
        except TypeError:
            try:
                value = recv()
            except (TimeoutError, queue.Empty):
                return None
        return bytes(value) if value is not None else None
    try:
        value = next(receiver)
    except StopIteration:
        setattr(receiver, "_pycodex_closed", True)
        return None
    return bytes(value) if value is not None else None


def _receiver_closed(receiver: Any) -> bool:
    if receiver is None:
        return True
    return bool(getattr(receiver, "closed", False) or getattr(receiver, "_pycodex_closed", False))


def _token_cancelled(token: Any) -> bool:
    if token is None:
        return False
    for name in ("is_cancelled", "is_set", "cancelled"):
        value = getattr(token, name, None)
        if callable(value):
            return bool(value())
        if value is not None and not callable(value):
            return bool(value)
    return bool(token)


def _wait_for_token_cancelled(token: Any) -> None:
    wait = getattr(token, "wait", None)
    if callable(wait):
        wait()
        return
    while not _token_cancelled(token):
        time.sleep(0.01)


def _notify_output_drained(notify: Any) -> None:
    for name in ("notify_one", "notify", "set", "release"):
        value = getattr(notify, name, None)
        if callable(value):
            value()
            return
    if callable(notify):
        notify()


def _wait_for_output_drained(notify: Any) -> None:
    wait = getattr(notify, "wait", None)
    if callable(wait):
        wait()
        return
    if notify is None:
        return
    is_set = getattr(notify, "is_set", None)
    if not callable(is_set):
        return
    while not bool(is_set()):
        time.sleep(0.01)


def _process_failure_message(process: Any) -> str | None:
    failure = getattr(process, "failure_message", None)
    value = failure() if callable(failure) else failure
    return value if isinstance(value, str) and value else None


def _process_exit_code(process: Any) -> int:
    exit_code = getattr(process, "exit_code", None)
    value = exit_code() if callable(exit_code) else exit_code
    return int(value) if value is not None else -1


def _send_exec_output_delta(context: UnifiedExecContext, chunk: str) -> None:
    event = {
        "type": "exec_command_output_delta",
        "call_id": context.call_id,
        "stream": "stdout",
        "chunk": chunk,
    }
    _send_session_event(context.session, context.turn, event)


def _send_unified_exec_end_event(session_ref: Any, turn_ref: Any, plan: UnifiedExecEndEventPlan) -> None:
    _send_session_event(
        session_ref,
        turn_ref,
        {
            "type": "exec_command_end",
            "call_id": plan.call_id,
            "command": plan.command,
            "cwd": plan.cwd,
            "process_id": plan.process_id,
            "source": plan.source,
            "status": plan.status,
            "exit_code": plan.exit_code,
            "stdout": plan.stdout,
            "stderr": plan.stderr,
            "aggregated_output": plan.aggregated_output,
            "duration_ms": plan.duration_ms,
            "timed_out": plan.timed_out,
        },
    )


def _send_session_event(session_ref: Any, turn_ref: Any, event: dict[str, Any]) -> None:
    send = getattr(session_ref, "send_event", None)
    if callable(send):
        try:
            send(turn_ref, event)
        except TypeError:
            send(event)
        return
    send_raw = getattr(session_ref, "send_event_raw", None)
    if callable(send_raw):
        send_raw(event)


class HeadTailBuffer:
    """Capped byte buffer that keeps a stable prefix and suffix."""

    def __init__(self, max_bytes: int = UNIFIED_EXEC_OUTPUT_MAX_BYTES) -> None:
        if max_bytes < 0:
            raise ValueError("max_bytes must be non-negative")
        self.max_bytes = max_bytes
        self.head_budget = max_bytes // 2
        self.tail_budget = max_bytes - self.head_budget
        self._head: deque[bytes] = deque()
        self._tail: deque[bytes] = deque()
        self._head_bytes = 0
        self._tail_bytes = 0
        self._omitted_bytes = 0

    @classmethod
    def new(cls, max_bytes: int) -> "HeadTailBuffer":
        return cls(max_bytes)

    def retained_bytes(self) -> int:
        return self._head_bytes + self._tail_bytes

    def omitted_bytes(self) -> int:
        return self._omitted_bytes

    def push_chunk(self, chunk: bytes | bytearray | memoryview | Iterable[int]) -> None:
        data = bytes(chunk)
        if self.max_bytes == 0:
            self._omitted_bytes += len(data)
            return

        if self._head_bytes < self.head_budget:
            remaining_head = self.head_budget - self._head_bytes
            if len(data) <= remaining_head:
                self._head_bytes += len(data)
                self._head.append(data)
                return

            head_part = data[:remaining_head]
            tail_part = data[remaining_head:]
            if head_part:
                self._head_bytes += len(head_part)
                self._head.append(head_part)
            self._push_to_tail(tail_part)
            return

        self._push_to_tail(data)

    def snapshot_chunks(self) -> list[bytes]:
        return [*self._head, *self._tail]

    def to_bytes(self) -> bytes:
        return b"".join(self.snapshot_chunks())

    def drain_chunks(self) -> list[bytes]:
        chunks = self.snapshot_chunks()
        self._head.clear()
        self._tail.clear()
        self._head_bytes = 0
        self._tail_bytes = 0
        self._omitted_bytes = 0
        return chunks

    def _push_to_tail(self, chunk: bytes) -> None:
        if self.tail_budget == 0:
            self._omitted_bytes += len(chunk)
            return

        if len(chunk) >= self.tail_budget:
            kept = chunk[len(chunk) - self.tail_budget :]
            dropped = len(chunk) - len(kept)
            self._omitted_bytes += self._tail_bytes + dropped
            self._tail.clear()
            self._tail_bytes = len(kept)
            self._tail.append(kept)
            return

        self._tail_bytes += len(chunk)
        self._tail.append(chunk)
        self._trim_tail_to_budget()

    def _trim_tail_to_budget(self) -> None:
        excess = max(self._tail_bytes - self.tail_budget, 0)
        while excess > 0 and self._tail:
            front = self._tail[0]
            if excess >= len(front):
                excess -= len(front)
                self._tail_bytes -= len(front)
                self._omitted_bytes += len(front)
                self._tail.popleft()
            else:
                self._tail[0] = front[excess:]
                self._tail_bytes -= excess
                self._omitted_bytes += excess
                break


__all__ = [
    "DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS",
    "DEFAULT_MAX_OUTPUT_TOKENS",
    "EARLY_EXIT_GRACE_PERIOD_MS",
    "ExecCommandRequest",
    "ExecServerEnvConfig",
    "ExecServerParams",
    "HeadTailBuffer",
    "LATE_NETWORK_DENIAL_GRACE_PERIOD_MS",
    "MAX_EXEC_OUTPUT_DELTAS_PER_CALL",
    "MAX_UNIFIED_EXEC_PROCESSES",
    "MAX_YIELD_TIME_MS",
    "MIN_EMPTY_YIELD_TIME_MS",
    "MIN_YIELD_TIME_MS",
    "NETWORK_ACCESS_DENIED_MESSAGE",
    "ProcessState",
    "ProcessEntry",
    "ProcessOutputChunk",
    "ProcessStore",
    "UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES",
    "UNIFIED_EXEC_OUTPUT_MAX_BYTES",
    "UNIFIED_EXEC_OUTPUT_MAX_TOKENS",
    "UNIFIED_EXEC_ENV",
    "TRAILING_OUTPUT_GRACE_MS",
    "UnifiedExecError",
    "UnifiedExecEndEventPlan",
    "UnifiedExecContext",
    "UnifiedExecProcessManager",
    "UnifiedExecRemoteProcessModel",
    "WriteStdinRequest",
    "apply_unified_exec_env",
    "clamp_yield_time",
    "deterministic_process_ids_for_tests",
    "env_overlay_for_exec_server",
    "emit_exec_end_for_unified_exec",
    "emit_failed_exec_end_for_unified_exec",
    "exec_server_after_seq",
    "exec_server_env_for_request",
    "exec_server_params_for_request",
    "exec_server_process_id",
    "exec_server_write_status_accepted",
    "exec_server_write_status_marks_exited",
    "generate_chunk_id",
    "network_denial_message_for_session",
    "process_id_to_prune_from_meta",
    "process_output_chunk",
    "resolve_aggregated_output",
    "resolve_failed_aggregated_output",
    "resolve_max_tokens",
    "resolve_write_stdin_yield_time",
    "set_deterministic_process_ids_for_tests",
    "should_emit_exec_output_delta",
    "should_emit_terminal_interaction",
    "split_valid_utf8_prefix",
    "split_valid_utf8_prefix_with_max",
    "spawn_exit_watcher",
    "start_streaming_output",
    "terminal_interaction_process_id",
    "unified_exec_failed_end_event_plan",
    "unified_exec_success_end_event_plan",
    "wait_for_late_network_denial",
]
