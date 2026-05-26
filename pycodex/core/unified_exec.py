"""Small unified-exec helpers ported from ``core/src/unified_exec``."""

from __future__ import annotations

import random
from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from typing import TypeVar

from pycodex.protocol import ExecToolCallOutput


MIN_YIELD_TIME_MS = 250
MIN_EMPTY_YIELD_TIME_MS = 5_000
MAX_YIELD_TIME_MS = 30_000
DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS = 300_000
DEFAULT_MAX_OUTPUT_TOKENS = 10_000
UNIFIED_EXEC_OUTPUT_MAX_BYTES = 1024 * 1024
UNIFIED_EXEC_OUTPUT_MAX_TOKENS = UNIFIED_EXEC_OUTPUT_MAX_BYTES // 4
MAX_UNIFIED_EXEC_PROCESSES = 64
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


def clamp_yield_time(yield_time_ms: int) -> int:
    return min(max(yield_time_ms, MIN_YIELD_TIME_MS), MAX_YIELD_TIME_MS)


def resolve_max_tokens(max_tokens: int | None) -> int:
    return DEFAULT_MAX_OUTPUT_TOKENS if max_tokens is None else max_tokens


def generate_chunk_id() -> str:
    return "".join(f"{random.randrange(16):x}" for _ in range(6))


def apply_unified_exec_env(env: dict[str, str]) -> dict[str, str]:
    merged = dict(env)
    merged.update(UNIFIED_EXEC_ENV)
    return merged


def env_overlay_for_exec_server(
    request_env: dict[str, str],
    local_policy_env: dict[str, str],
) -> dict[str, str]:
    return {
        key: value
        for key, value in request_env.items()
        if local_policy_env.get(key) != value
    }


def exec_server_process_id(process_id: int) -> str:
    return str(process_id)


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
    "HeadTailBuffer",
    "MAX_UNIFIED_EXEC_PROCESSES",
    "MAX_YIELD_TIME_MS",
    "MIN_EMPTY_YIELD_TIME_MS",
    "MIN_YIELD_TIME_MS",
    "ProcessState",
    "UNIFIED_EXEC_OUTPUT_MAX_BYTES",
    "UNIFIED_EXEC_OUTPUT_MAX_TOKENS",
    "UNIFIED_EXEC_ENV",
    "UnifiedExecError",
    "apply_unified_exec_env",
    "clamp_yield_time",
    "env_overlay_for_exec_server",
    "exec_server_process_id",
    "generate_chunk_id",
    "process_id_to_prune_from_meta",
    "resolve_max_tokens",
]
