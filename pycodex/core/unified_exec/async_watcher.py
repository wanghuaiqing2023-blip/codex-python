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



from . import (
    MAX_EXEC_OUTPUT_DELTAS_PER_CALL,
    TRAILING_OUTPUT_GRACE_MS,
    UnifiedExecContext,
    UnifiedExecEndEventPlan,
    unified_exec_failed_end_event_plan,
    unified_exec_success_end_event_plan,
)

from .head_tail_buffer import (
    HeadTailBuffer,
)

from .process_manager import (
    _sync_callable_bool,
)

UNIFIED_EXEC_OUTPUT_DELTA_MAX_BYTES = 8192

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
    saw_cancellation_attr = False
    for name in ("is_cancelled", "is_set", "cancelled"):
        value = getattr(token, name, None)
        if callable(value):
            saw_cancellation_attr = True
            result = _sync_callable_bool(value)
            if result is not None:
                return result
            continue
        if value is not None and not callable(value):
            saw_cancellation_attr = True
            return bool(value)
    if saw_cancellation_attr:
        return False
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

