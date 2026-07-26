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
    UnifiedExecError,
    exec_server_write_status_accepted,
    exec_server_write_status_marks_exited,
)

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

