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
    UNIFIED_EXEC_OUTPUT_MAX_BYTES,
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

