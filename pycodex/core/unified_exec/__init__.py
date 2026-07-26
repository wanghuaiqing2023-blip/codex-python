"""Small unified-exec helpers ported from ``core/src/unified_exec``."""

from __future__ import annotations

import inspect
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
from pathlib import Path
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
MAX_EXEC_OUTPUT_DELTAS_PER_CALL = 10_000
MAX_UNIFIED_EXEC_PROCESSES = 64
LATE_NETWORK_DENIAL_GRACE_PERIOD_MS = 100
_T = TypeVar("_T")
def set_deterministic_process_ids_for_tests(enabled: bool) -> None:
    """Delegate the Rust parent-module test hook to ``process_manager``."""

    from .process_manager import set_deterministic_process_ids_for_tests as set_for_manager

    set_for_manager(enabled)


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
    environment_is_complete: bool = False
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
        if not isinstance(self.environment_is_complete, bool):
            raise TypeError("environment_is_complete must be a bool")
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






























from .errors import UnifiedExecError




























































from .head_tail_buffer import (
    HeadTailBuffer,
)

from .process_state import (
    ProcessState,
    UnifiedExecRemoteProcessModel,
)

from .async_watcher import (
    ProcessOutputChunk,
    UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES,
    _notify_output_drained,
    _process_cancellation_token,
    _process_exit_code,
    _process_failure_message,
    _process_output_drained_notify,
    _process_output_receiver,
    _receiver_closed,
    _recv_output_chunk,
    _send_exec_output_delta,
    _send_session_event,
    _send_unified_exec_end_event,
    _token_cancelled,
    _wait_for_output_drained,
    _wait_for_token_cancelled,
    emit_exec_end_for_unified_exec,
    emit_failed_exec_end_for_unified_exec,
    process_output_chunk,
    resolve_aggregated_output,
    resolve_failed_aggregated_output,
    should_emit_exec_output_delta,
    spawn_exit_watcher,
    split_valid_utf8_prefix,
    split_valid_utf8_prefix_with_max,
    start_streaming_output,
)

from .process_manager import (
    ExecServerEnvConfig,
    ExecServerParams,
    NETWORK_ACCESS_DENIED_MESSAGE,
    ProcessEntry,
    UNIFIED_EXEC_ENV,
    UnifiedExecProcessManager,
    _cancellation_token_is_cancelled,
    _command_for_spawn,
    _exec_server_env_config_fields,
    _request_env_mapping,
    _spawn_unified_exec_process,
    _sync_callable_bool,
    _windows_profile_deny_overrides,
    apply_unified_exec_env,
    env_overlay_for_exec_server,
    exec_server_env_for_request,
    exec_server_params_for_request,
    exec_server_process_id,
    network_denial_message_for_session,
    process_id_to_prune_from_meta,
    wait_for_late_network_denial,
)
from .process import UnifiedExecProcess

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
    "UnifiedExecProcess",
    "UnifiedExecRemoteProcessModel",
    "WriteStdinRequest",
    "apply_unified_exec_env",
    "clamp_yield_time",
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
