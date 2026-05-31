"""Local in-process runtime bridge for ``codex exec`` user turns."""

from __future__ import annotations

import os
import json
import inspect
import secrets
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4

from pycodex.core.apply_patch import create_apply_patch_freeform_tool, parse_patch, verify_apply_patch_args
from pycodex.core.client import ModelClient
from pycodex.core.handler_utils import normalize_additional_permissions
from pycodex.core.http_transport import response_items_from_responses_payload, run_user_turn_http_sampling_from_session
from pycodex.core.rollout import (
    SessionMeta,
    ThreadSortKey,
    append_turn_to_latest_thread_rollout,
    append_turn_to_thread_rollout,
    append_turn_to_rollout,
    find_thread_meta_by_name_str,
    find_thread_path_by_id_str,
    get_threads,
    materialize_session_rollout,
    read_thread_item_from_rollout,
    read_session_meta_line,
    read_response_items_from_rollout,
)
from pycodex.core.session_runtime import InMemoryCodexSession
from pycodex.core.shell_spec import create_request_permissions_tool, request_permissions_tool_description
from pycodex.core.turn_runtime import UserTurnSamplingResult
from pycodex.core.unified_exec import (
    DEFAULT_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS as CORE_UNIFIED_EXEC_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS,
    DEFAULT_MAX_OUTPUT_TOKENS as CORE_UNIFIED_EXEC_DEFAULT_MAX_OUTPUT_TOKENS,
    EARLY_EXIT_GRACE_PERIOD_MS as CORE_UNIFIED_EXEC_EARLY_EXIT_GRACE_PERIOD_MS,
    MAX_UNIFIED_EXEC_PROCESSES as CORE_MAX_UNIFIED_EXEC_PROCESSES,
    MAX_YIELD_TIME_MS as CORE_UNIFIED_EXEC_MAX_YIELD_TIME_MS,
    MIN_EMPTY_YIELD_TIME_MS as CORE_UNIFIED_EXEC_MIN_EMPTY_YIELD_TIME_MS,
    MIN_YIELD_TIME_MS as CORE_UNIFIED_EXEC_MIN_YIELD_TIME_MS,
    TRAILING_OUTPUT_GRACE_MS as CORE_UNIFIED_EXEC_TRAILING_OUTPUT_GRACE_MS,
    UNIFIED_EXEC_OUTPUT_MAX_BYTES as CORE_UNIFIED_EXEC_OUTPUT_MAX_BYTES,
    UNIFIED_EXEC_OUTPUT_MAX_TOKENS as CORE_UNIFIED_EXEC_OUTPUT_MAX_TOKENS,
    clamp_yield_time,
    resolve_write_stdin_yield_time,
)
from pycodex.protocol import AskForApproval, BaseInstructions, ResponseInputItem, ResponseItem
from pycodex.protocol.models import AdditionalPermissionProfile, FunctionCallOutputPayload

from .event_processor import HumanEventProcessor, JsonEventProcessor, exec_turn_completed_notification
from .events import ExecThreadItem, ThreadErrorEvent, ThreadEvent, Usage, agent_message_item, reasoning_item
from .run import ExecRunPlan
from .session import ExecSessionConfig, cwds_match


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5"
LOCAL_HTTP_EXEC_ENV = "PYCODEX_EXEC_LOCAL_HTTP"
LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV = "PYCODEX_EXEC_LOCAL_HTTP_SHELL_TOOLS"
LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV = "PYCODEX_EXEC_LOCAL_HTTP_MAX_TOOL_ROUNDS"
LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV = "PYCODEX_EXEC_LOCAL_HTTP_TOOL_OUTPUT_MAX_CHARS"
DEFAULT_LOCAL_HTTP_EXEC_YIELD_TIME_MS = 10_000
DEFAULT_LOCAL_HTTP_WRITE_STDIN_YIELD_TIME_MS = 250
DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS = CORE_UNIFIED_EXEC_DEFAULT_MAX_OUTPUT_TOKENS
LOCAL_HTTP_APPROX_BYTES_PER_TOKEN = 4
LOCAL_HTTP_EXEC_MIN_YIELD_TIME_MS = CORE_UNIFIED_EXEC_MIN_YIELD_TIME_MS
LOCAL_HTTP_EXEC_MIN_EMPTY_STDIN_YIELD_TIME_MS = CORE_UNIFIED_EXEC_MIN_EMPTY_YIELD_TIME_MS
LOCAL_HTTP_EXEC_MAX_YIELD_TIME_MS = CORE_UNIFIED_EXEC_MAX_YIELD_TIME_MS
LOCAL_HTTP_EXEC_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS = CORE_UNIFIED_EXEC_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS
LOCAL_HTTP_EXEC_EARLY_EXIT_GRACE_PERIOD_MS = CORE_UNIFIED_EXEC_EARLY_EXIT_GRACE_PERIOD_MS
LOCAL_HTTP_EXEC_TRAILING_OUTPUT_GRACE_MS = CORE_UNIFIED_EXEC_TRAILING_OUTPUT_GRACE_MS
LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE = 124
LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES = CORE_UNIFIED_EXEC_OUTPUT_MAX_BYTES
LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS = CORE_UNIFIED_EXEC_OUTPUT_MAX_TOKENS
LOCAL_HTTP_MAX_UNIFIED_EXEC_PROCESSES = CORE_MAX_UNIFIED_EXEC_PROCESSES
LOCAL_HTTP_UNIFIED_EXEC_PROTECTED_RECENT_PROCESSES = 8


_SESSION_COUNTER = count(1)


@dataclass(frozen=True)
class LocalHttpModelInfo:
    """Minimal model metadata needed by the local exec HTTP path."""

    slug: str
    base_instructions: str = "You are Codex, a coding agent."
    supports_reasoning_summaries: bool = False
    support_verbosity: bool = False

    def service_tier_for_request(self, service_tier: str | None) -> str | None:
        return service_tier


@dataclass(frozen=True)
class LocalHttpProvider:
    """Small provider value compatible with the stdlib HTTP transport."""

    base_url: str = DEFAULT_OPENAI_BASE_URL
    auth: Any = None

    def is_azure_responses_endpoint(self) -> bool:
        return False


@dataclass(frozen=True)
class LocalHttpShellInvocation:
    """Shell tool invocation parsed from Responses function-call arguments."""

    command: str
    workdir: Path | None = None
    timeout: float | None = None
    login: bool | None = None
    shell: str | None = None
    tty: bool | None = None
    yield_time_ms: float | None = None
    max_output_tokens: int | None = None
    sandbox_permissions: str | None = None
    additional_permissions: Mapping[str, Any] | None = None
    additional_permissions_is_invalid: bool = False
    justification: str | None = None
    prefix_rule: tuple[str, ...] | None = None


@dataclass(frozen=True)
class LocalHttpWriteStdinInvocation:
    """write_stdin invocation parsed from Responses function-call arguments."""

    session_id: int
    chars: str = ""
    yield_time: float | None = None
    max_output_tokens: int | None = None


class LocalHttpHeadTailBuffer:
    """Small byte-oriented head/tail output buffer matching Rust unified exec."""

    def __init__(self, max_bytes: int = LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES) -> None:
        self.max_bytes = max(0, int(max_bytes))
        self.head_budget = self.max_bytes // 2
        self.tail_budget = self.max_bytes - self.head_budget
        self.head: deque[bytes] = deque()
        self.tail: deque[bytes] = deque()
        self.head_bytes = 0
        self.tail_bytes = 0
        self._omitted_bytes = 0

    def retained_bytes(self) -> int:
        return self.head_bytes + self.tail_bytes

    def omitted_bytes(self) -> int:
        return self._omitted_bytes

    def push_text(self, chunk: str) -> None:
        self.push_chunk(chunk.encode("utf-8"))

    def push_chunk(self, chunk: bytes) -> None:
        if self.max_bytes == 0:
            self._omitted_bytes += len(chunk)
            return
        if self.head_bytes < self.head_budget:
            remaining_head = self.head_budget - self.head_bytes
            if len(chunk) <= remaining_head:
                self.head_bytes += len(chunk)
                self.head.append(bytes(chunk))
                return
            head_part = chunk[:remaining_head]
            tail_part = chunk[remaining_head:]
            if head_part:
                self.head_bytes += len(head_part)
                self.head.append(bytes(head_part))
            self._push_to_tail(bytes(tail_part))
            return
        self._push_to_tail(bytes(chunk))

    def drain_text(self) -> str:
        chunks = self.drain_chunks()
        return b"".join(chunks).decode("utf-8", errors="replace")

    def to_bytes(self) -> bytes:
        return b"".join(self.snapshot_chunks())

    def snapshot_chunks(self) -> list[bytes]:
        chunks = list(self.head)
        chunks.extend(self.tail)
        return chunks

    def drain_chunks(self) -> list[bytes]:
        chunks = self.snapshot_chunks()
        self.head.clear()
        self.tail.clear()
        self.head_bytes = 0
        self.tail_bytes = 0
        self._omitted_bytes = 0
        return chunks

    def _push_to_tail(self, chunk: bytes) -> None:
        if self.tail_budget == 0:
            self._omitted_bytes += len(chunk)
            return
        if len(chunk) >= self.tail_budget:
            kept = chunk[-self.tail_budget:]
            dropped = len(chunk) - len(kept)
            self._omitted_bytes += self.tail_bytes + dropped
            self.tail.clear()
            self.tail_bytes = len(kept)
            self.tail.append(bytes(kept))
            return
        self.tail_bytes += len(chunk)
        self.tail.append(bytes(chunk))
        self._trim_tail_to_budget()

    def _trim_tail_to_budget(self) -> None:
        excess = self.tail_bytes - self.tail_budget
        while excess > 0 and self.tail:
            front = self.tail[0]
            if excess >= len(front):
                excess -= len(front)
                self.tail_bytes -= len(front)
                self._omitted_bytes += len(front)
                self.tail.popleft()
                continue
            self.tail[0] = front[excess:]
            self.tail_bytes -= excess
            self._omitted_bytes += excess
            break


class LocalHttpExecSession:
    """Small stdlib process session used by local HTTP ``exec_command``."""

    def __init__(
        self,
        session_id: int,
        process: subprocess.Popen[Any],
        timeout: float | None = None,
        *,
        tty_requested: bool = False,
    ) -> None:
        self.session_id = session_id
        self.process = process
        self.timeout_at = None if timeout is None else time.monotonic() + timeout
        self.tty_requested = tty_requested
        self._output = LocalHttpHeadTailBuffer()
        self._output_lock = threading.Lock()
        self._reader = threading.Thread(target=self._read_output, daemon=True)
        self._reader.start()

    def _read_output(self) -> None:
        stream = self.process.stdout
        if stream is None:
            return
        try:
            fileno = getattr(stream, "fileno", None)
            if callable(fileno):
                fd = fileno()
                while True:
                    chunk = os.read(fd, 8192)
                    if not chunk:
                        break
                    with self._output_lock:
                        self._output.push_chunk(chunk)
                return
            for chunk in iter(stream.readline, b""):
                if chunk in {"", b""}:
                    break
                with self._output_lock:
                    if isinstance(chunk, bytes):
                        self._output.push_chunk(chunk)
                    else:
                        self._output.push_text(chunk)
        finally:
            try:
                stream.close()
            except OSError:
                pass

    def write(self, chars: str) -> None:
        if self.process.stdin is None or self.process.poll() is not None:
            return
        try:
            self.process.stdin.write(chars.encode("utf-8"))
        except TypeError:
            self.process.stdin.write(chars)
        self.process.stdin.flush()

    def snapshot(self, *, yield_time: float | None = None, output_max_chars: int | None = None) -> tuple[dict[str, Any], bool]:
        started = time.monotonic()
        timed_out = False
        if yield_time:
            deadline = started + yield_time
            while time.monotonic() < deadline and self.process.poll() is None:
                timed_out = self._terminate_if_timed_out()
                if timed_out:
                    break
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                time.sleep(min(0.05, remaining))
        if not timed_out:
            timed_out = self._terminate_if_timed_out()
        output = self._drain_output()
        elapsed = time.monotonic() - started
        exit_code = self.process.poll()
        running = exit_code is None
        body = _exec_session_output_payload(
            output,
            wall_time_seconds=elapsed,
            chunk_id=local_http_generate_chunk_id(),
            session_id=self.session_id if running else None,
            exit_code=LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE if timed_out else exit_code,
            timed_out=timed_out,
            tty_requested=self.tty_requested,
            output_max_chars=output_max_chars,
        )
        return body, not running and exit_code == 0

    def _terminate_if_timed_out(self) -> bool:
        if self.timeout_at is None or self.process.poll() is not None:
            return False
        if time.monotonic() < self.timeout_at:
            return False
        _terminate_process_tree(self.process)
        return True

    def close(self) -> None:
        try:
            if self.process.stdin is not None:
                self.process.stdin.close()
        except OSError:
            pass
        try:
            if self.process.stdout is not None:
                self.process.stdout.close()
        except OSError:
            pass

    def _drain_output(self) -> str:
        with self._output_lock:
            return self._output.drain_text()


class LocalHttpExecSessionManager:
    """Manage local stdlib exec sessions for explicit local HTTP tool calls."""

    def __init__(self, *, max_sessions: int = LOCAL_HTTP_MAX_UNIFIED_EXEC_PROCESSES) -> None:
        self.max_sessions = max(0, int(max_sessions))
        self._sessions: dict[int, LocalHttpExecSession] = {}
        self._session_last_used: dict[int, float] = {}

    def start(
        self,
        command: str,
        *,
        cwd: Path,
        shell: str | None = None,
        tty_requested: bool = False,
        yield_time: float | None = None,
        timeout: float | None = None,
        output_max_chars: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        self._prune_sessions_if_needed()
        session_id = next(_SESSION_COUNTER)
        process_kwargs: dict[str, Any] = {}
        if os.name == "nt":
            process_kwargs["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        else:
            process_kwargs["start_new_session"] = True
        process = subprocess.Popen(
            command,
            shell=True,
            executable=shell,
            cwd=str(cwd),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=False,
            bufsize=0,
            **process_kwargs,
        )
        session = LocalHttpExecSession(session_id, process, timeout=timeout, tty_requested=tty_requested)
        self._sessions[session_id] = session
        self._session_last_used[session_id] = time.monotonic()
        output, success = session.snapshot(yield_time=yield_time, output_max_chars=output_max_chars)
        if process.poll() is not None:
            self._sessions.pop(session_id, None)
            self._session_last_used.pop(session_id, None)
            session.close()
        return output, success

    def write(
        self,
        session_id: int,
        chars: str,
        *,
        yield_time: float | None = None,
        output_max_chars: int | None = None,
    ) -> tuple[dict[str, Any], bool]:
        session = self._sessions.get(session_id)
        if session is None:
            raise KeyError(session_id)
        self._session_last_used[session_id] = time.monotonic()
        if chars:
            session.write(chars)
        output, success = session.snapshot(yield_time=yield_time, output_max_chars=output_max_chars)
        if session.process.poll() is not None:
            self._sessions.pop(session_id, None)
            self._session_last_used.pop(session_id, None)
            session.close()
        return output, success

    def _prune_sessions_if_needed(self) -> None:
        if self.max_sessions <= 0 or len(self._sessions) < self.max_sessions:
            return
        protected = set(
            session_id
            for session_id, _last_used in sorted(
                self._session_last_used.items(),
                key=lambda item: item[1],
                reverse=True,
            )[:LOCAL_HTTP_UNIFIED_EXEC_PROTECTED_RECENT_PROCESSES]
        )
        oldest = sorted(self._session_last_used.items(), key=lambda item: item[1])
        prune_id = next(
            (
                session_id
                for session_id, _last_used in oldest
                if session_id not in protected and self._sessions[session_id].process.poll() is not None
            ),
            None,
        )
        if prune_id is None:
            prune_id = next(
                (session_id for session_id, _last_used in oldest if session_id not in protected),
                None,
            )
        if prune_id is None:
            prune_id = oldest[0][0] if oldest else None
        if prune_id is None:
            return
        session = self._sessions.pop(prune_id, None)
        self._session_last_used.pop(prune_id, None)
        if session is None:
            return
        if session.process.poll() is None:
            _terminate_process_tree(session.process)
        session.close()


_DEFAULT_EXEC_SESSION_MANAGER = LocalHttpExecSessionManager()


class LocalHttpShellToolRouter:
    """Minimal model-visible shell tool router for the local HTTP exec path."""

    def __init__(self, base_router: Any = None) -> None:
        self._base_router = base_router

    def model_visible_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        if self._base_router is not None:
            base_specs = getattr(self._base_router, "model_visible_specs", None)
            if callable(base_specs):
                for spec in base_specs():
                    if isinstance(spec, Mapping):
                        specs.append(dict(spec))
        if not any(_local_http_shell_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_shell_tool_spec())
        if not any(_local_http_write_stdin_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_write_stdin_tool_spec())
        if not any(_local_http_request_permissions_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_request_permissions_tool_spec())
        if not any(_local_http_apply_patch_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_apply_patch_tool_spec())
        return specs


def local_http_shell_tool_spec() -> dict[str, Any]:
    """Return the Responses function tool spec used by local HTTP exec loop."""

    description = "Runs a command in a PTY, returning output or a session ID for ongoing interaction."
    if os.name == "nt":
        description = f"{description}\n\n{local_http_windows_shell_guidance()}"

    return {
        "type": "function",
        "name": "exec_command",
        "description": description,
        "strict": False,
        "defer_loading": None,
        "parameters": {
            "type": "object",
            "properties": {
                "cmd": {"type": "string", "description": "Shell command to execute."},
                "workdir": {
                    "type": "string",
                    "description": "Optional working directory to run the command in; defaults to the turn cwd.",
                },
                "cwd": {
                    "type": "string",
                    "description": "Compatibility alias for workdir.",
                },
                "shell": {
                    "type": "string",
                    "description": "Shell binary to launch. Defaults to the user's default shell.",
                },
                "tty": {
                    "type": "boolean",
                    "description": (
                        "Whether to allocate a TTY for the command. Defaults to false (plain pipes); "
                        "set to true to open a PTY and access TTY process."
                    ),
                },
                "yield_time_ms": {
                    "type": "number",
                    "description": "How long to wait (in milliseconds) for output before yielding.",
                },
                "max_output_tokens": {
                    "type": "number",
                    "description": "Maximum number of tokens to return. Excess output will be truncated.",
                },
                "timeout_ms": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Compatibility alias for command timeout in milliseconds.",
                },
                "timeout": {
                    "type": "integer",
                    "minimum": 0,
                    "description": "Compatibility alias for command timeout in milliseconds.",
                },
                "login": {
                    "type": "boolean",
                    "description": "Whether to run the shell with -l/-i semantics. Defaults to true.",
                },
                "sandbox_permissions": {
                    "type": "string",
                    "description": (
                        'Sandbox permissions for the command. Use "with_additional_permissions" to request '
                        'additional sandboxed filesystem or network permissions (preferred), or '
                        '"require_escalated" to request running without sandbox restrictions; defaults to '
                        '"use_default".'
                    ),
                },
                "additional_permissions": {
                    **local_http_permission_profile_schema(),
                    "description": "Optional additional permission profile requested for this command.",
                },
                "justification": {
                    "type": "string",
                    "description": (
                        'Only set if sandbox_permissions is "require_escalated".\n'
                        "Request approval from the user to run this command outside the sandbox.\n"
                        "Phrased as a simple question that summarizes the purpose of the\n"
                        "command as it relates to the task at hand - e.g. 'Do you want to\n"
                        "fetch and pull the latest version of this git branch?'"
                    ),
                },
                "prefix_rule": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "Only specify when sandbox_permissions is `require_escalated`.\n"
                        "Suggest a prefix command pattern that will allow you to fulfill similar requests from the user in the future.\n"
                        'Should be a short but reasonable prefix, e.g. ["git", "pull"] or ["uv", "run"] or ["pytest"].'
                    ),
                },
            },
            "required": ["cmd"],
            "additionalProperties": False,
        },
        "output_schema": local_http_exec_command_output_schema(),
    }


def local_http_windows_shell_guidance() -> str:
    """Return Rust Codex's Windows-specific exec_command safety guidance."""

    return (
        "Windows safety rules:\n"
        "- Do not compose destructive filesystem commands across shells. Do not enumerate paths in PowerShell and then pass them to `cmd /c`, batch builtins, or another shell for deletion or moving. Use one shell end-to-end, prefer native PowerShell cmdlets such as `Remove-Item` / `Move-Item` with `-LiteralPath`, and avoid string-built shell commands for file operations.\n"
        "- Before any recursive delete or move on Windows, verify the resolved absolute target paths stay within the intended workspace or explicitly named target directory. Never issue a recursive delete or move against a computed path if the final target has not been checked.\n"
        "- When using `Start-Process` to launch a background helper or service, pass `-WindowStyle Hidden` unless the user explicitly asked for a visible interactive window. Use visible windows only for interactive tools the user needs to see or control."
    )


def local_http_permission_profile_schema() -> dict[str, Any]:
    """Return Rust Codex's additional sandbox permission profile schema."""

    return {
        "type": "object",
        "properties": {
            "network": {
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "Set to true to request network access.",
                    },
                },
                "additionalProperties": False,
            },
            "file_system": {
                "type": "object",
                "properties": {
                    "read": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths to grant read access to.",
                    },
                    "write": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Absolute paths to grant write access to.",
                    },
                },
                "additionalProperties": False,
            },
        },
        "additionalProperties": False,
    }


def local_http_exec_command_output_schema() -> dict[str, Any]:
    """Return the Rust Codex ``exec_command`` output schema."""

    return {
        "type": "object",
        "properties": {
            "chunk_id": {
                "type": "string",
                "description": "Chunk identifier included when the response reports one.",
            },
            "wall_time_seconds": {
                "type": "number",
                "description": "Elapsed wall time spent waiting for output in seconds.",
            },
            "exit_code": {
                "type": "number",
                "description": "Process exit code when the command finished during this call.",
            },
            "session_id": {
                "type": "number",
                "description": "Session identifier to pass to write_stdin when the process is still running.",
            },
            "original_token_count": {
                "type": "number",
                "description": "Approximate token count before output truncation.",
            },
            "output": {
                "type": "string",
                "description": "Command output text, possibly truncated.",
            },
        },
        "required": ["wall_time_seconds", "output"],
        "additionalProperties": False,
    }


def local_http_write_stdin_tool_spec() -> dict[str, Any]:
    """Return the Rust Codex ``write_stdin`` companion tool spec."""

    return {
        "type": "function",
        "name": "write_stdin",
        "description": "Writes characters to an existing unified exec session and returns recent output.",
        "strict": False,
        "defer_loading": None,
        "parameters": {
            "type": "object",
            "properties": {
                "session_id": {
                    "type": "number",
                    "description": "Identifier of the running unified exec session.",
                },
                "chars": {
                    "type": "string",
                    "description": "Bytes to write to stdin (may be empty to poll).",
                },
                "yield_time_ms": {
                    "type": "number",
                    "description": "How long to wait (in milliseconds) for output before yielding.",
                },
                "max_output_tokens": {
                    "type": "number",
                    "description": "Maximum number of tokens to return. Excess output will be truncated.",
                },
            },
            "required": ["session_id"],
            "additionalProperties": False,
        },
        "output_schema": local_http_exec_command_output_schema(),
    }


def local_http_request_permissions_tool_spec() -> dict[str, Any]:
    """Return the Rust Codex ``request_permissions`` tool spec."""

    return create_request_permissions_tool(request_permissions_tool_description())


def local_http_apply_patch_tool_spec() -> dict[str, Any]:
    """Return the Responses custom tool spec for apply_patch."""

    return dict(create_apply_patch_freeform_tool(False).to_mapping())


def local_http_shell_tools_built_tools(base_built_tools: Any = None) -> Any:
    """Wrap an optional built-tools callback with the local shell tool spec."""

    def build(session: Any, turn_context: Any) -> Any:
        base_router = base_built_tools(session, turn_context) if callable(base_built_tools) else base_built_tools
        if inspect.isawaitable(base_router):
            async def resolve() -> LocalHttpShellToolRouter:
                return LocalHttpShellToolRouter(await base_router)

            return resolve()
        return LocalHttpShellToolRouter(base_router)

    return build


def _local_http_shell_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("type") == "function" and spec.get("name") in {
        "exec_command",
        "shell_command",
        "shell",
        "local_shell",
        "exec",
    }


def _local_http_write_stdin_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("type") == "function" and spec.get("name") == "write_stdin"


def _local_http_request_permissions_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("type") == "function" and spec.get("name") == "request_permissions"


def _local_http_apply_patch_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("name") == "apply_patch" and spec.get("type") in {"custom", "function"}


def local_http_exec_enabled(env: Any = None) -> bool:
    """Return true when the experimental local HTTP exec path is enabled."""

    source = os.environ if env is None else env
    explicit_state = str(source.get(LOCAL_HTTP_EXEC_ENV, "")).strip().lower()
    if explicit_state in {
        "1",
        "true",
        "yes",
        "on",
        "enable",
        "enabled",
    }:
        return True
    if explicit_state in {"0", "false", "no", "off", "disable", "disabled"}:
        return False
    return bool(str(source.get("OPENAI_API_KEY", "")).strip()) or bool(
        str(source.get("CODEX_API_KEY", "")).strip()
    )


def local_http_exec_shell_tools_enabled(env: Any = None) -> bool:
    """Return true when local HTTP exec should run the shell tool loop."""

    source = os.environ if env is None else env
    return str(source.get(LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV, "")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "enable",
        "enabled",
    }


def local_http_exec_max_tool_rounds(env: Any = None, default: int = 1) -> int:
    """Resolve the local HTTP exec shell tool loop round limit."""

    if isinstance(default, bool) or not isinstance(default, int):
        raise TypeError("default must be an integer")
    if default < 0:
        raise ValueError("default must be non-negative")
    source = os.environ if env is None else env
    raw = source.get(LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV)
    if raw is None or str(raw).strip() == "":
        return default
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV} must be a non-negative integer") from exc
    if value < 0:
        raise ValueError(f"{LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV} must be a non-negative integer")
    return value


def local_http_exec_tool_output_max_chars(env: Any = None) -> int | None:
    """Resolve the local HTTP exec shell tool output truncation limit."""

    source = os.environ if env is None else env
    raw = source.get(LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV)
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(str(raw).strip(), 10)
    except ValueError as exc:
        raise ValueError(f"{LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV} must be a positive integer") from exc
    if value <= 0:
        raise ValueError(f"{LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV} must be a positive integer")
    return value


def default_local_http_exec_auth(
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
    provider_id: str | None = None,
) -> Any:
    """Resolve auth for the default local HTTP exec runtime."""

    source = os.environ if env is None else env
    api_key = source.get("OPENAI_API_KEY")
    if isinstance(api_key, str) and api_key:
        return api_key
    codex_api_key = source.get("CODEX_API_KEY")
    if isinstance(codex_api_key, str) and codex_api_key:
        return codex_api_key
    provider_env_key = _config_provider_env_key(config_toml, provider_id)
    if provider_env_key is not None:
        provider_api_key = source.get(provider_env_key)
        if isinstance(provider_api_key, str) and provider_api_key:
            return provider_api_key
    auth_api_key = getattr(auth, "openai_api_key", None) or getattr(auth, "api_key", None)
    if isinstance(auth_api_key, str) and auth_api_key:
        return auth_api_key
    if isinstance(auth, str) and auth:
        return auth
    return None


def build_default_local_http_exec_runtime(
    config: ExecSessionConfig,
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
) -> tuple[ModelClient, LocalHttpProvider, LocalHttpModelInfo, Any]:
    """Build the default OpenAI Responses runtime for local ``codex exec``."""

    source = os.environ if env is None else env
    provider_id = config.model_provider_id or _config_model_provider(config_toml) or "openai"
    resolved_auth = default_local_http_exec_auth(
        auth=auth,
        env=source,
        config_toml=config_toml,
        provider_id=provider_id,
    )
    if resolved_auth is None or resolved_auth == "":
        raise ValueError("OPENAI_API_KEY or CODEX_API_KEY is required for PYCODEX_EXEC_LOCAL_HTTP=1")

    model = default_local_http_exec_model(config, env=source, config_toml=config_toml)
    base_url = default_local_http_exec_base_url(env=source, config_toml=config_toml, provider_id=provider_id)
    provider = LocalHttpProvider(base_url=base_url, auth=resolved_auth)
    model_info = LocalHttpModelInfo(slug=model)
    client = ModelClient(
        session_id=str(uuid4()),
        thread_id=str(uuid4()),
        installation_id=source.get("CODEX_INSTALLATION_ID") or "pycodex-local-exec",
        provider=provider,
    )
    return client, provider, model_info, resolved_auth


def default_local_http_exec_model(
    config: ExecSessionConfig,
    *,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
) -> str:
    """Resolve the default local HTTP exec model using CLI/config/env precedence."""

    source = os.environ if env is None else env
    return (
        config.model
        or source.get("PYCODEX_EXEC_MODEL")
        or source.get("OPENAI_MODEL")
        or _config_model(config_toml)
        or DEFAULT_OPENAI_MODEL
    )


def default_local_http_exec_base_url(
    *,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
    provider_id: str | None = None,
) -> str:
    """Resolve the default local HTTP exec provider base URL."""

    source = os.environ if env is None else env
    return source.get("OPENAI_BASE_URL") or _config_provider_base_url(config_toml, provider_id) or DEFAULT_OPENAI_BASE_URL


def _config_model(config_toml: Mapping[str, Any] | None) -> str | None:
    if config_toml is None:
        return None
    model = config_toml.get("model")
    return model if isinstance(model, str) and model else None


def _config_model_provider(config_toml: Mapping[str, Any] | None) -> str | None:
    if config_toml is None:
        return None
    provider = config_toml.get("model_provider")
    return provider if isinstance(provider, str) and provider else None


def _config_provider_base_url(config_toml: Mapping[str, Any] | None, provider_id: str | None) -> str | None:
    if config_toml is None or provider_id is None:
        return None
    providers = config_toml.get("model_providers")
    if not isinstance(providers, Mapping):
        return None
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return None
    base_url = provider.get("base_url")
    return base_url if isinstance(base_url, str) and base_url else None


def _config_provider_env_key(config_toml: Mapping[str, Any] | None, provider_id: str | None) -> str | None:
    if config_toml is None or provider_id is None:
        return None
    providers = config_toml.get("model_providers")
    if not isinstance(providers, Mapping):
        return None
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return None
    env_key = provider.get("env_key")
    return env_key if isinstance(env_key, str) and env_key else None


def local_http_exec_config_summary(
    config: ExecSessionConfig,
    *,
    model: str | None = None,
    provider_id: str | None = None,
    session_id: str = "local-http",
    thread_id: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build config/session-configured mappings for exec config summaries."""

    resolved_model = model or default_local_http_exec_model(config)
    resolved_provider = provider_id or config.model_provider_id or "openai"
    resolved_thread_id = thread_id or session_id
    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    permission_profile = config.permission_profile.to_mapping()
    config_mapping = {
        "cwd": str(config.cwd),
        "workspace_roots": [str(root) for root in config.workspace_roots],
        "model": resolved_model,
        "model_provider_id": resolved_provider,
        "approval_policy": approval,
        "permission_profile": permission_profile,
    }
    session_configured = {
        "session_id": session_id,
        "thread_id": resolved_thread_id,
        "model": resolved_model,
        "model_provider_id": resolved_provider,
        "cwd": str(config.cwd),
        "approval_policy": approval,
        "permission_profile": permission_profile,
    }
    return config_mapping, session_configured


async def run_exec_user_turn_default_local_http_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    *,
    auth: Any = None,
    env: Any = None,
    config_toml: Mapping[str, Any] | None = None,
    codex_home: Path | None = None,
    cli_version: str = "pycodex",
    opener: Any = None,
    built_tools: Any = None,
) -> UserTurnSamplingResult:
    """Run a prepared exec user turn through the default local HTTP runtime."""

    client, provider, model_info, resolved_auth = build_default_local_http_exec_runtime(
        config,
        auth=auth,
        env=env,
        config_toml=config_toml,
    )
    result = await run_exec_user_turn_http_sampling(
        config,
        plan,
        client,
        provider,
        model_info,
        auth=resolved_auth,
        opener=opener,
        built_tools=built_tools,
    )
    if codex_home is not None:
        persist_local_http_exec_rollout(
            codex_home,
            config,
            result,
            client,
            input_items=plan.initial_operation.items if plan.initial_operation.kind == "user_turn" else (),
            cli_version=cli_version,
        )
    return result


def persist_local_http_exec_rollout(
    codex_home: Path,
    config: ExecSessionConfig,
    result: UserTurnSamplingResult,
    model_client: ModelClient,
    *,
    input_items: tuple[Any, ...] | list[Any] = (),
    cli_version: str = "pycodex",
) -> Path | None:
    """Persist local HTTP exec session metadata and response items to rollout JSONL."""

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rollout_path = materialize_session_rollout(
        codex_home,
        SessionMeta(
            id=str(model_client.state.thread_id),
            timestamp=timestamp,
            cwd=str(config.cwd),
            originator="codex_exec",
            cli_version=cli_version,
            source="cli",
            model_provider=config.model_provider_id or "openai",
        ),
        ephemeral=config.ephemeral,
    )
    if rollout_path is None:
        return None
    input_payload = _local_http_input_rollout_payload(input_items)
    append_turn_to_rollout(
        rollout_path,
        input_payload,
        _local_http_response_rollout_payloads(result),
        timestamp=timestamp,
        cwd=config.cwd,
    )
    return rollout_path


def persist_local_http_exec_resume_rollout(
    codex_home: Path,
    config: ExecSessionConfig,
    result: UserTurnSamplingResult,
    *,
    input_items: tuple[Any, ...] | list[Any] = (),
    thread_id: str | None = None,
    resume_last: bool = False,
    include_all: bool = False,
) -> Path | None:
    """Append a completed local HTTP resumed turn to an existing rollout JSONL."""

    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    input_payload = _local_http_input_rollout_payload(input_items)
    response_payloads = _local_http_response_rollout_payloads(result)
    if thread_id is not None:
        return append_turn_to_thread_rollout(
            codex_home,
            thread_id,
            input_payload,
            response_payloads,
            timestamp=timestamp,
            cwd=config.cwd,
        )
    if resume_last:
        return append_turn_to_latest_thread_rollout(
            codex_home,
            input_payload,
            response_payloads,
            current_cwd=config.cwd,
            include_all=include_all,
            timestamp=timestamp,
        )
    return None


def resolve_local_http_exec_resume_rollout_path(
    codex_home: Path,
    config: ExecSessionConfig,
    *,
    thread_id: str | None = None,
    session_name: str | None = None,
    resume_last: bool = False,
    include_all: bool = False,
) -> Path | None:
    """Resolve the existing rollout JSONL used by a local HTTP resume turn."""

    if thread_id is not None:
        return find_thread_path_by_id_str(codex_home, thread_id)
    if session_name is not None:
        found = find_thread_meta_by_name_str(codex_home, session_name)
        if found is None:
            return None
        path, meta = found
        if include_all:
            return path
        item = read_thread_item_from_rollout(path)
        latest_cwd = item.cwd if item is not None else Path(meta.meta.cwd)
        return path if latest_cwd is not None and cwds_match(config.cwd, latest_cwd) else None
    if not resume_last:
        return None
    page = get_threads(
        codex_home,
        page_size=1,
        sort_key=ThreadSortKey.UPDATED_AT,
        cwd_filters=None if include_all else (Path(config.cwd),),
        allowed_sources=("cli",),
    )
    return page.items[0].path if page.items else None


def _align_local_http_model_client_to_rollout_session(model_client: ModelClient, rollout_path: Path) -> None:
    """Align local HTTP resume model identity to the persisted rollout session."""

    resumed_id = read_session_meta_line(rollout_path).meta.id
    model_client.state.session_id = resumed_id
    model_client.state.thread_id = resumed_id

def align_local_http_exec_resume_model_client(
    codex_home: Path,
    config: ExecSessionConfig,
    model_client: ModelClient,
    *,
    thread_id: str | None = None,
    session_name: str | None = None,
    resume_last: bool = False,
    include_all: bool = False,
) -> Path | None:
    """Align a local HTTP resume model client with the resolved rollout thread."""

    rollout_path = resolve_local_http_exec_resume_rollout_path(
        codex_home,
        config,
        thread_id=thread_id,
        session_name=session_name,
        resume_last=resume_last,
        include_all=include_all,
    )
    if rollout_path is None:
        return None
    _align_local_http_model_client_to_rollout_session(model_client, rollout_path)
    return rollout_path


async def run_exec_resume_user_turn_http_sampling(
    codex_home: Path,
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    thread_id: str | None = None,
    session_name: str | None = None,
    resume_last: bool = False,
    include_all: bool = False,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
    use_shell_tools: bool = False,
    max_tool_rounds: int = 1,
    tool_output_max_chars: int | None = None,
    runner: Any = None,
    resolved_rollout_path: Path | None = None,
) -> UserTurnSamplingResult:
    """Run a local HTTP resumed user turn using rollout history and append the result."""

    if resolved_rollout_path is None:
        rollout_path = align_local_http_exec_resume_model_client(
            codex_home,
            config,
            model_client,
            thread_id=thread_id,
            session_name=session_name,
            resume_last=resume_last,
            include_all=include_all,
        )
    else:
        rollout_path = Path(resolved_rollout_path)
        _align_local_http_model_client_to_rollout_session(model_client, rollout_path)
    if rollout_path is None:
        raise ValueError("no local rollout found for resume")
    history_items = read_response_items_from_rollout(rollout_path)
    if use_shell_tools:
        result = await run_exec_user_turn_with_shell_tools_http_sampling(
            config,
            plan,
            model_client,
            provider,
            model_info,
            auth=auth,
            endpoint=endpoint,
            timeout=timeout,
            opener=opener,
            built_tools=built_tools,
            history_items=history_items,
            max_tool_rounds=max_tool_rounds,
            tool_output_max_chars=tool_output_max_chars,
            runner=runner,
        )
    else:
        result = await run_exec_user_turn_http_sampling(
            config,
            plan,
            model_client,
            provider,
            model_info,
            auth=auth,
            endpoint=endpoint,
            timeout=timeout,
            opener=opener,
            built_tools=built_tools,
            history_items=history_items,
        )
    operation = plan.initial_operation
    input_items = operation.items if operation.kind == "user_turn" else ()
    append_turn_to_rollout(
        rollout_path,
        _local_http_input_rollout_payload(input_items),
        _local_http_response_rollout_payloads(result),
        timestamp=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        cwd=config.cwd,
    )
    return result


def _local_http_input_rollout_payload(input_items: tuple[Any, ...] | list[Any]) -> dict[str, Any] | None:
    if not input_items:
        return None
    return ResponseItem.from_response_input_item(ResponseInputItem.from_user_inputs(tuple(input_items))).to_mapping()


def _local_http_response_rollout_payloads(result: UserTurnSamplingResult) -> tuple[dict[str, Any], ...]:
    prompt_visible_items = _local_http_prompt_visible_rollout_items(result)
    return tuple(_response_item_rollout_payload(item) for item in prompt_visible_items)


def _local_http_prompt_visible_rollout_items(result: UserTurnSamplingResult) -> tuple[ResponseItem, ...]:
    tool_response_items = tuple(getattr(result, "tool_response_items", ()) or ())
    raw_payloads = _raw_responses_payloads(result)
    if len(raw_payloads) <= 1 or not tool_response_items:
        return tuple(result.response_items) + tool_response_items

    items: list[ResponseItem] = []
    tool_index = 0
    for index, payload in enumerate(raw_payloads):
        try:
            model_items = response_items_from_responses_payload(payload)
        except (KeyError, TypeError, ValueError):
            model_items = ()
        items.extend(model_items)
        if index >= len(raw_payloads) - 1:
            continue
        expected_tool_outputs = _tool_call_count(model_items)
        if expected_tool_outputs <= 0 and tool_index < len(tool_response_items):
            expected_tool_outputs = 1
        for _ in range(expected_tool_outputs):
            if tool_index >= len(tool_response_items):
                break
            items.append(tool_response_items[tool_index])
            tool_index += 1
    items.extend(tool_response_items[tool_index:])
    return tuple(items) if items else tuple(result.response_items) + tool_response_items


def _tool_call_count(items: tuple[ResponseItem, ...]) -> int:
    return sum(1 for item in items if str(getattr(item, "type", "")) in {"function_call", "custom_tool_call"})


def _response_item_rollout_payload(item: Any) -> dict[str, Any]:
    to_mapping = getattr(item, "to_mapping", None)
    if callable(to_mapping):
        return dict(to_mapping())
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError(f"response item is not serializable to rollout payload: {type(item).__name__}")


async def run_exec_user_turn_http_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
    history_items: tuple[ResponseItem, ...] | list[ResponseItem] = (),
) -> Any:
    """Run a prepared ``codex exec`` user turn through the HTTP core path."""

    operation = plan.initial_operation
    if operation.kind != "user_turn":
        raise ValueError("local exec HTTP runtime currently supports only user_turn operations")
    session = InMemoryCodexSession(
        cwd=config.cwd,
        model_info=model_info,
        user_instructions=config.user_instructions,
        base_instructions=_base_instructions_from_model_info(model_info),
    )
    if history_items:
        turn_context = await session.new_default_turn()
        await session.record_conversation_items(turn_context, tuple(history_items))
    return await run_user_turn_http_sampling_from_session(
        session,
        operation.items,
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=built_tools,
        effort=config.reasoning_effort,
        output_schema=operation.output_schema,
    )


async def run_exec_tool_output_http_sampling(
    config: ExecSessionConfig,
    previous_result: UserTurnSamplingResult,
    tool_outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
) -> Any:
    """Run a follow-up model turn with tool output items in history."""

    session = InMemoryCodexSession(
        cwd=config.cwd,
        model_info=model_info,
        user_instructions=config.user_instructions,
        base_instructions=_base_instructions_from_model_info(model_info),
    )
    turn_context = await session.new_default_turn()
    if previous_result.response_items:
        await session.record_conversation_items(turn_context, previous_result.response_items)
    previous_tool_response_items = tuple(getattr(previous_result, "tool_response_items", ()) or ())
    if previous_tool_response_items:
        await session.record_conversation_items(turn_context, previous_tool_response_items)
    tool_response_items = response_items_from_local_http_tool_outputs(tool_outputs)
    if tool_response_items:
        await session.record_conversation_items(turn_context, tool_response_items)
    return await run_user_turn_http_sampling_from_session(
        session,
        (),
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=built_tools,
        effort=config.reasoning_effort,
    )


async def run_exec_user_turn_with_shell_tools_http_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: Any = None,
    runner: Any = None,
    tool_timeout: float | None = 30.0,
    tool_output_max_chars: int | None = None,
    max_tool_rounds: int = 1,
    history_items: tuple[ResponseItem, ...] | list[ResponseItem] = (),
) -> Any:
    """Run a user turn and feed shell tool outputs back to the model."""

    if isinstance(max_tool_rounds, bool) or not isinstance(max_tool_rounds, int):
        raise TypeError("max_tool_rounds must be an integer")
    if max_tool_rounds < 0:
        raise ValueError("max_tool_rounds must be non-negative")
    shell_built_tools = local_http_shell_tools_built_tools(built_tools)
    result = await run_exec_user_turn_http_sampling(
        config,
        plan,
        model_client,
        provider,
        model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=shell_built_tools,
        history_items=history_items,
    )
    for _round in range(max_tool_rounds):
        tool_outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=runner,
            timeout=tool_timeout,
            output_max_chars=tool_output_max_chars,
        )
        if not tool_outputs:
            return result
        previous_result = result
        followup_result = await run_exec_tool_output_http_sampling(
            config,
            previous_result,
            tool_outputs,
            model_client,
            provider,
            model_info,
            auth=auth,
            endpoint=endpoint,
            timeout=timeout,
            opener=opener,
            built_tools=shell_built_tools,
        )
        result = _merge_local_http_sampling_result(previous_result, tool_outputs, followup_result)
    return result


def response_items_from_local_http_tool_outputs(
    tool_outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
) -> tuple[ResponseItem, ...]:
    """Convert Responses tool output mappings into prompt-visible items."""

    if isinstance(tool_outputs, (str, bytes)) or not isinstance(tool_outputs, (list, tuple)):
        raise TypeError("tool_outputs must be a list or tuple of mappings")
    items: list[ResponseItem] = []
    for output in tool_outputs:
        if not isinstance(output, Mapping):
            raise TypeError("tool output entries must be mappings")
        item_type = output.get("type")
        call_id = output.get("call_id")
        if not isinstance(item_type, str):
            raise TypeError("tool output type must be a string")
        if not isinstance(call_id, str):
            raise TypeError("tool output call_id must be a string")
        response_output = output.get("output")
        success = output.get("success")
        tool_name = output.get("name")
        if success is not None and not isinstance(success, bool):
            raise TypeError("tool output success must be a bool or None")
        if tool_name is not None and not isinstance(tool_name, str):
            raise TypeError("tool output name must be a string or None")
        if item_type in {"function_call_output", "custom_tool_call_output"} and success is not None:
            payload = FunctionCallOutputPayload.from_value(response_output)
            response_output = FunctionCallOutputPayload(payload.body, success=success)
        input_item = ResponseInputItem(
            type=item_type,
            call_id=call_id,
            name=tool_name if item_type == "custom_tool_call_output" else None,
            output=response_output,
        )
        items.append(ResponseItem.from_response_input_item(input_item))
    return tuple(items)


def _base_instructions_from_model_info(model_info: Any) -> BaseInstructions:
    value = getattr(model_info, "base_instructions", None)
    if value is None:
        get_model_instructions = getattr(model_info, "get_model_instructions", None)
        if callable(get_model_instructions):
            value = get_model_instructions(None)
    if value is None:
        return BaseInstructions.default()
    if isinstance(value, BaseInstructions):
        return value
    return BaseInstructions(str(value))


def final_text_from_response_items(items: tuple[ResponseItem, ...] | list[ResponseItem]) -> str:
    """Return the last assistant-visible text from Responses output items."""

    last_text = ""
    for item in items:
        content = getattr(item, "content", None)
        if not isinstance(content, (list, tuple)):
            continue
        parts: list[str] = []
        for part in content:
            text = getattr(part, "text", None)
            if isinstance(text, str) and text:
                parts.append(text)
        item_text = "".join(parts)
        if item_text:
            last_text = item_text
    return last_text


def emit_local_http_exec_result(
    processor: HumanEventProcessor | JsonEventProcessor,
    result: UserTurnSamplingResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdout_is_terminal: bool | None = None,
    stderr_is_terminal: bool | None = None,
) -> str:
    """Render a local HTTP exec result through the normal exec processors."""

    final_text = final_text_from_response_items(result.response_items)
    usage = usage_from_local_http_exec_result(result)
    if isinstance(processor, JsonEventProcessor):
        events = [ThreadEvent.turn_started()]
        for reasoning_text in reasoning_texts_from_local_http_exec_result(result):
            events.append(ThreadEvent.item_completed(reasoning_item(processor.next_item_id(), reasoning_text)))
        for tool_item in tool_timeline_items_from_local_http_exec_result(result, processor):
            events.append(ThreadEvent.item_completed(tool_item))
        if final_text:
            processor.final_message = final_text
            events.append(ThreadEvent.item_completed(agent_message_item(processor.next_item_id(), final_text)))
        processor.emit_final_message_on_shutdown = True
        events.append(ThreadEvent.turn_completed(usage))
        processor.emit_json_lines(events, stdout)
        processor.print_final_output(stderr=stderr)
        return final_text

    if final_text:
        processor.final_message = final_text
    processor.final_message_rendered = False
    processor.emit_final_message_on_shutdown = True
    processor.last_usage = usage
    processor.print_final_output(
        stdout=stdout,
        stderr=stderr,
        stdout_is_terminal=stdout_is_terminal,
        stderr_is_terminal=stderr_is_terminal,
    )
    return final_text


def tool_call_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
) -> tuple[ExecThreadItem, ...]:
    """Extract read-only tool/function call items from a local HTTP Responses payload."""

    items: list[ExecThreadItem] = []
    for payload in _raw_responses_payloads(result):
        for item in _response_output_mappings(payload):
            item_type = str(item.get("type") or "")
            if item_type not in {"function_call", "custom_tool_call", "mcp_tool_call"}:
                continue
            items.append(_tool_call_exec_thread_item(item, processor))
    return tuple(items)


def tool_output_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
) -> tuple[ExecThreadItem, ...]:
    """Extract read-only tool/function output items from a local HTTP Responses payload."""

    items: list[ExecThreadItem] = []
    output_items: list[Mapping[str, Any]] = []
    for payload in _raw_responses_payloads(result):
        output_items.extend(
            item
            for item in _response_output_mappings(payload)
            if str(item.get("type") or "") in {"function_call_output", "custom_tool_call_output", "mcp_tool_call_output"}
        )
    for response_item in getattr(result, "tool_response_items", ()) or ():
        mapping = _response_item_mapping(response_item)
        if mapping is not None:
            output_items.append(mapping)
    for item in output_items:
        items.append(_tool_output_exec_thread_item(item, processor))
    return tuple(items)


def tool_timeline_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
) -> tuple[ExecThreadItem, ...]:
    """Extract tool call/output items in user-turn order."""

    calls: list[Mapping[str, Any]] = []
    output_items: list[Mapping[str, Any]] = []
    for payload in _raw_responses_payloads(result):
        for item in _response_output_mappings(payload):
            item_type = str(item.get("type") or "")
            if item_type in {"function_call", "custom_tool_call", "mcp_tool_call"}:
                calls.append(item)
            elif item_type in {"function_call_output", "custom_tool_call_output", "mcp_tool_call_output"}:
                output_items.append(item)
    for response_item in getattr(result, "tool_response_items", ()) or ():
        mapping = _response_item_mapping(response_item)
        if mapping is not None:
            output_items.append(mapping)

    outputs_by_call_id: dict[str, list[Mapping[str, Any]]] = {}
    unkeyed_outputs: list[Mapping[str, Any]] = []
    for output in output_items:
        call_id = str(output.get("call_id") or output.get("id") or "")
        if call_id:
            outputs_by_call_id.setdefault(call_id, []).append(output)
        else:
            unkeyed_outputs.append(output)
    timeline: list[ExecThreadItem] = []
    for call in calls:
        timeline.append(_tool_call_exec_thread_item(call, processor))
        call_id = str(call.get("call_id") or call.get("id") or "")
        if call_id:
            timeline.extend(_tool_output_exec_thread_item(output, processor) for output in outputs_by_call_id.pop(call_id, ()))
    for remaining in outputs_by_call_id.values():
        timeline.extend(_tool_output_exec_thread_item(output, processor) for output in remaining)
    timeline.extend(_tool_output_exec_thread_item(output, processor) for output in unkeyed_outputs)
    return tuple(timeline)


def _tool_call_exec_thread_item(item: Mapping[str, Any], processor: JsonEventProcessor) -> ExecThreadItem:
    return ExecThreadItem(
        processor.next_item_id(),
        "mcp_tool_call",
        {
            "server": "responses",
            "tool": _tool_name_from_item(item),
            "call_id": str(item.get("call_id") or item.get("id") or ""),
            "arguments": _tool_arguments_from_item(item),
            "result": None,
            "error": None,
            "status": "in_progress",
        },
    )


def _tool_output_exec_thread_item(item: Mapping[str, Any], processor: JsonEventProcessor) -> ExecThreadItem:
    return ExecThreadItem(
        processor.next_item_id(),
        "mcp_tool_call",
        {
            "server": "responses",
            "tool": _tool_name_from_item(item),
            "call_id": str(item.get("call_id") or item.get("id") or ""),
            "arguments": {},
            "result": _tool_output_from_item(item),
            "error": None,
            "status": "completed",
        },
    )


def shell_tool_outputs_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    config: ExecSessionConfig,
    *,
    runner: Any = None,
    session_manager: LocalHttpExecSessionManager | None = None,
    timeout: float | None = 30.0,
    output_max_chars: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Execute shell function calls from a local HTTP Responses payload.

    This helper intentionally only returns Responses ``function_call_output``
    mappings. The caller decides whether and when to feed them into another
    model request so approval/sandbox policy can be inserted before automatic
    execution in the CLI path.
    """

    payload = _raw_responses_payload(result)
    if not isinstance(payload, Mapping):
        return ()
    output = payload.get("output")
    if isinstance(output, Mapping):
        output_items = (output,)
    elif isinstance(output, (list, tuple)):
        output_items = tuple(item for item in output if isinstance(item, Mapping))
    else:
        return ()

    run = subprocess.run if runner is None else runner
    sessions = _DEFAULT_EXEC_SESSION_MANAGER if session_manager is None else session_manager
    outputs: list[dict[str, Any]] = []
    for item in output_items:
        item_type = str(item.get("type") or "")
        if item_type not in {"function_call", "custom_tool_call"}:
            continue
        tool = _tool_name_from_item(item)
        call_id = item.get("call_id") or item.get("id") or ""
        if tool == "request_permissions":
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "name": "request_permissions",
                    "output": local_http_request_permissions_unavailable_output(),
                    "success": False,
                }
            )
            continue
        if tool == "apply_patch":
            patch_text = _apply_patch_text_from_arguments(_tool_arguments_from_item(item))
            if patch_text is None:
                continue
            if not local_http_shell_tool_auto_execute_allowed(config):
                outputs.append(
                    {
                        "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                        "call_id": str(call_id),
                        "name": "apply_patch",
                        "output": local_http_apply_patch_approval_required_output(config),
                        "success": False,
                    }
                )
                continue
            output_text, success = _apply_local_http_apply_patch(patch_text, config.cwd)
            outputs.append(
                {
                    "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                    "call_id": str(call_id),
                    "name": "apply_patch",
                    "output": output_text,
                    "success": success,
                }
            )
            continue
        if tool == "write_stdin":
            stdin_invocation = _write_stdin_invocation_from_arguments(_tool_arguments_from_item(item))
            if not local_http_shell_tool_auto_execute_allowed(config):
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "name": "write_stdin",
                        "output": local_http_write_stdin_approval_required_output(config),
                        "success": False,
                    }
                )
                continue
            if stdin_invocation is not None:
                try:
                    output_payload, success = sessions.write(
                        stdin_invocation.session_id,
                        stdin_invocation.chars,
                        yield_time=stdin_invocation.yield_time,
                        output_max_chars=_effective_shell_output_max_chars(
                            output_max_chars,
                            stdin_invocation.max_output_tokens,
                        ),
                    )
                except KeyError:
                    outputs.append(
                        {
                            "type": "function_call_output",
                            "call_id": str(call_id),
                            "name": "write_stdin",
                            "output": local_http_write_stdin_unknown_session_output(stdin_invocation.session_id),
                            "success": False,
                        }
                    )
                    continue
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "name": "write_stdin",
                        "output": local_http_exec_output_text(output_payload),
                        "structured_output": local_http_exec_schema_output_payload(output_payload),
                        "internal_output": output_payload,
                        "success": success,
                    }
                )
                continue
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "name": "write_stdin",
                    "output": local_http_write_stdin_unavailable_output(_tool_arguments_from_item(item)),
                    "success": False,
                }
            )
            continue
        if tool not in {"exec_command", "shell_command", "shell", "local_shell", "exec"}:
            continue
        invocation = _shell_invocation_from_arguments(
            _tool_arguments_from_item(item),
            default_cwd=config.cwd,
            default_timeout=timeout,
        )
        if invocation is None:
            continue
        sandbox_permissions_error = local_http_shell_tool_sandbox_permissions_error(invocation)
        if sandbox_permissions_error is not None:
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": sandbox_permissions_error,
                    "success": False,
                }
            )
            continue
        if not local_http_shell_tool_auto_execute_allowed(config):
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": local_http_shell_tool_approval_required_output(invocation, config),
                    "success": False,
                }
            )
            continue
        permission_error = local_http_shell_tool_permission_request_error(invocation)
        if permission_error is not None:
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": permission_error,
                    "success": False,
                }
            )
            continue
        effective_output_max_chars = _effective_shell_output_max_chars(output_max_chars, invocation.max_output_tokens)
        if runner is None and _should_start_local_http_exec_session(invocation):
            output_payload, success = sessions.start(
                invocation.command,
                cwd=invocation.workdir or config.cwd,
                shell=invocation.shell,
                tty_requested=bool(invocation.tty),
                yield_time=invocation.yield_time_ms,
                timeout=invocation.timeout,
                output_max_chars=effective_output_max_chars,
            )
            output_text = local_http_exec_output_text(output_payload)
            structured_output = local_http_exec_schema_output_payload(output_payload)
            internal_output = output_payload
        else:
            output_text, success = _run_shell_tool_command_result(
                invocation.command,
                cwd=invocation.workdir or config.cwd,
                runner=run,
                timeout=invocation.timeout,
                login=invocation.login,
                shell_binary=invocation.shell,
                output_max_chars=effective_output_max_chars,
            )
            structured_output = None
            internal_output = None
        outputs.append(
            {
                "type": "function_call_output",
                "call_id": str(call_id),
                "output": output_text,
                **({"structured_output": structured_output} if structured_output is not None else {}),
                **({"internal_output": internal_output} if internal_output is not None else {}),
                "success": success,
            }
        )
    return tuple(outputs)


def local_http_apply_patch_approval_required_output(config: ExecSessionConfig) -> str:
    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    return (
        "apply_patch: approval_required\n"
        f"approval_policy: {approval}\n"
        "stderr:\nPatch application requires approval and was not run by the local HTTP helper."
    )


def local_http_write_stdin_approval_required_output(config: ExecSessionConfig) -> str:
    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        "output:\nwrite_stdin requires approval and was not run by the local HTTP helper."
    )


def local_http_write_stdin_unavailable_output(arguments: Any) -> str:
    session_id = _write_stdin_session_id_from_arguments(arguments)
    session_text = "unknown" if session_id is None else str(session_id)
    return (
        "exit_code: unavailable\n"
        "wall_time_seconds: 0\n"
        f"session_id: {session_text}\n"
        "output:\nwrite_stdin is declared for protocol parity, but no local exec session runtime is active yet."
    )


def local_http_write_stdin_unknown_session_output(session_id: int) -> str:
    return f"write_stdin failed: Unknown process id {session_id}"


def local_http_request_permissions_unavailable_output() -> str:
    return (
        "request_permissions failed: request_permissions is declared for protocol parity, "
        "but local HTTP exec mode does not support interactive permission grants."
    )


def _write_stdin_invocation_from_arguments(arguments: Any) -> LocalHttpWriteStdinInvocation | None:
    session_id = _write_stdin_session_id_from_arguments(arguments)
    if session_id is None or not isinstance(arguments, Mapping):
        return None
    chars = arguments.get("chars")
    chars_text = chars if isinstance(chars, str) else ""
    return LocalHttpWriteStdinInvocation(
        session_id=session_id,
        chars=chars_text,
        yield_time=_shell_yield_time_from_arguments(
            arguments,
            default_ms=DEFAULT_LOCAL_HTTP_WRITE_STDIN_YIELD_TIME_MS,
            empty_stdin=chars_text == "",
        ),
        max_output_tokens=_shell_max_output_tokens_from_arguments(arguments),
    )


def _write_stdin_session_id_from_arguments(arguments: Any) -> int | None:
    if not isinstance(arguments, Mapping):
        return None
    value = arguments.get("session_id")
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _should_start_local_http_exec_session(invocation: LocalHttpShellInvocation) -> bool:
    return bool(invocation.tty) or invocation.yield_time_ms is not None


def local_http_generate_chunk_id() -> str:
    """Generate a Rust unified exec style six-hex-digit chunk id."""

    return secrets.token_hex(3)


def local_http_retain_head_tail_output(output: str, max_bytes: int) -> str:
    """Retain stable UTF-8 head and tail content within a hard byte cap."""

    buffer = LocalHttpHeadTailBuffer(max_bytes)
    buffer.push_text(output)
    return buffer.drain_text()


def local_http_exec_schema_output_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return only Rust schema-visible unified exec output fields."""

    allowed = {
        "chunk_id",
        "wall_time_seconds",
        "exit_code",
        "session_id",
        "original_token_count",
        "output",
    }
    return {key: value for key, value in payload.items() if key in allowed}


def _exec_session_output_payload(
    output: str,
    *,
    wall_time_seconds: float,
    chunk_id: str | None = None,
    session_id: int | None,
    exit_code: int | None,
    timed_out: bool = False,
    tty_requested: bool = False,
    output_max_chars: int | None,
) -> dict[str, Any]:
    rendered_output = _truncate_shell_tool_output(output.rstrip(), output_max_chars)
    payload: dict[str, Any] = {
        "wall_time_seconds": round(wall_time_seconds, 3),
        "original_token_count": _approx_token_count(output),
        "output": rendered_output,
    }
    if chunk_id is not None:
        payload["chunk_id"] = chunk_id
    if exit_code is not None:
        payload["exit_code"] = exit_code
    if timed_out:
        payload["timed_out"] = True
    if tty_requested:
        payload["tty_requested"] = True
    if session_id is not None:
        payload["session_id"] = session_id
    return payload


def _terminate_process_tree(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(process.pid)],
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
        return
    try:
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait(timeout=1.0)
    except (OSError, subprocess.TimeoutExpired):
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGKILL)
        except OSError:
            process.kill()
    finally:
        try:
            process.wait(timeout=1.0)
        except subprocess.TimeoutExpired:
            process.kill()


def local_http_exec_output_text(payload: Mapping[str, Any]) -> str:
    lines: list[str] = []
    if "chunk_id" in payload:
        lines.append(f"Chunk ID: {payload['chunk_id']}")
    lines.append(f"Wall time: {float(payload.get('wall_time_seconds', 0)):.4f} seconds")
    if "exit_code" in payload:
        lines.append(f"Process exited with code {payload['exit_code']}")
    if "session_id" in payload:
        lines.append(f"Process running with session ID {payload['session_id']}")
    if "original_token_count" in payload:
        lines.append(f"Original token count: {payload['original_token_count']}")
    lines.append("Output:")
    lines.append(str(payload.get("output", "")))
    return "\n".join(lines).rstrip()


def _approx_token_count(text: str) -> int:
    if not text:
        return 0
    return (len(text.encode("utf-8")) + LOCAL_HTTP_APPROX_BYTES_PER_TOKEN - 1) // LOCAL_HTTP_APPROX_BYTES_PER_TOKEN


def _approx_bytes_for_tokens(tokens: int) -> int:
    return max(0, int(tokens)) * LOCAL_HTTP_APPROX_BYTES_PER_TOKEN


def _apply_patch_text_from_arguments(arguments: Any) -> str | None:
    if isinstance(arguments, str):
        return arguments if arguments.strip() else None
    if not isinstance(arguments, Mapping):
        return None
    for key in ("patch", "input", "content"):
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _apply_local_http_apply_patch(patch_text: str, cwd: Path) -> tuple[str, bool]:
    try:
        verified = verify_apply_patch_args(parse_patch(patch_text), cwd)
    except Exception as exc:
        return f"apply_patch failed: {exc}", False
    if verified.type != "body" or verified.body is None:
        return f"apply_patch failed: {verified.error}", False
    try:
        changed_paths = _write_apply_patch_action(verified.body.changes)
    except OSError as exc:
        return f"apply_patch failed: {exc}", False
    changed = "\n".join(str(path) for path in changed_paths)
    return ("apply_patch succeeded" if not changed else f"apply_patch succeeded\nchanged files:\n{changed}"), True


def _write_apply_patch_action(changes: Mapping[Path, Any]) -> tuple[Path, ...]:
    changed: list[Path] = []
    for path, change in changes.items():
        target = Path(path)
        if change.type == "add":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content or change.new_content or "", encoding="utf-8")
            changed.append(target)
        elif change.type == "delete":
            target.unlink()
            changed.append(target)
        elif change.type == "update":
            new_content = change.new_content if change.new_content is not None else change.content
            if new_content is None:
                raise OSError(f"missing new content for {target}")
            if change.move_path is not None:
                move_target = Path(change.move_path)
                move_target.parent.mkdir(parents=True, exist_ok=True)
                move_target.write_text(new_content, encoding="utf-8")
                target.unlink()
                changed.append(move_target)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(new_content, encoding="utf-8")
                changed.append(target)
    return tuple(changed)


def local_http_shell_tool_auto_execute_allowed(config: ExecSessionConfig) -> bool:
    """Return true when the local helper may auto-run shell commands."""

    return config.approval_policy is AskForApproval.NEVER or config.approval_policy == AskForApproval.NEVER


def local_http_shell_tool_sandbox_permissions_error(invocation: LocalHttpShellInvocation) -> str | None:
    """Return a model-facing error when sandbox_permissions is not a Rust enum value."""

    sandbox_permissions = invocation.sandbox_permissions
    if sandbox_permissions is None:
        return None
    if sandbox_permissions in {"use_default", "require_escalated", "with_additional_permissions"}:
        return None
    return (
        "exit_code: permission_request_invalid\n"
        "stderr:\n"
        f"invalid sandbox_permissions `{sandbox_permissions}`; expected one of `use_default`, `require_escalated`, or `with_additional_permissions`"
    )


def local_http_shell_tool_permission_request_error(invocation: LocalHttpShellInvocation) -> str | None:
    """Return a Rust-style model-facing error for unsupported local permission requests."""

    if invocation.additional_permissions_is_invalid:
        return (
            "exit_code: permission_request_invalid\n"
            "stderr:\n"
            "`additional_permissions` must be an object mapping permissions"
        )
    if invocation.additional_permissions is not None:
        if invocation.sandbox_permissions != "with_additional_permissions":
            return (
                "exit_code: permission_request_invalid\n"
                "stderr:\n"
                "`additional_permissions` requires `sandbox_permissions` set to `with_additional_permissions`"
            )
        try:
            profile = AdditionalPermissionProfile.from_mapping(dict(invocation.additional_permissions))
            if normalize_additional_permissions(profile).is_empty():
                return (
                    "exit_code: permission_request_invalid\n"
                    "stderr:\n"
                    "`additional_permissions` must include at least one requested permission in `network` or `file_system`"
                )
        except (KeyError, TypeError, ValueError):
            return (
                "exit_code: permission_request_invalid\n"
                "stderr:\n"
                "invalid `additional_permissions`; expected a permission object with `network` and/or `file_system`"
            )
        return (
            "exit_code: permission_request_unsupported\n"
            "stderr:\n"
            "additional permissions are disabled; enable `features.exec_permission_approvals` before using `with_additional_permissions`"
        )
    if invocation.sandbox_permissions == "with_additional_permissions":
        return (
            "exit_code: permission_request_invalid\n"
            "stderr:\n"
            "missing `additional_permissions`; provide at least one of `network` or `file_system` when using `with_additional_permissions`"
        )
    if invocation.sandbox_permissions == "require_escalated":
        return (
            "exit_code: permission_request_rejected\n"
            "stderr:\n"
            "approval policy is never; reject command - you cannot ask for escalated permissions if the approval policy is never"
        )
    return None


def local_http_shell_tool_approval_required_output(
    invocation: LocalHttpShellInvocation | str,
    config: ExecSessionConfig,
) -> str:
    """Build a tool output explaining that approval is required."""

    approval = getattr(config.approval_policy, "value", str(config.approval_policy))
    if isinstance(invocation, LocalHttpShellInvocation):
        command = invocation.command
        sandbox_permissions = invocation.sandbox_permissions
        additional_permissions = invocation.additional_permissions
        justification = invocation.justification
        prefix_rule = invocation.prefix_rule
    else:
        command = invocation
        sandbox_permissions = None
        additional_permissions = None
        justification = None
        prefix_rule = None
    metadata = ""
    if sandbox_permissions:
        metadata += f"sandbox_permissions: {sandbox_permissions}\n"
    if additional_permissions:
        additional_permissions_mapping = _local_http_additional_permissions_output_mapping(additional_permissions)
        metadata += (
            "additional_permissions: "
            f"{json.dumps(additional_permissions_mapping, ensure_ascii=False, separators=(',', ':'))}\n"
        )
    if justification:
        metadata += f"justification: {justification}\n"
    if prefix_rule:
        metadata += f"prefix_rule: {json.dumps(list(prefix_rule), ensure_ascii=False, separators=(',', ':'))}\n"
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        f"{metadata}"
        f"command:\n{command}\n"
        "stderr:\nCommand execution requires approval and was not run by the local HTTP helper."
    )


def _local_http_additional_permissions_output_mapping(additional_permissions: Mapping[str, Any]) -> Mapping[str, Any]:
    """Return a normalized Rust-style additional permission profile mapping when possible."""

    try:
        profile = AdditionalPermissionProfile.from_mapping(dict(additional_permissions))
        return normalize_additional_permissions(profile).to_mapping()
    except (KeyError, TypeError, ValueError):
        return dict(additional_permissions)


def _shell_invocation_from_arguments(
    arguments: Any,
    *,
    default_cwd: Path,
    default_timeout: float | None,
) -> LocalHttpShellInvocation | None:
    command = _shell_command_from_arguments(arguments)
    if not command:
        return None
    if not isinstance(arguments, Mapping):
        return LocalHttpShellInvocation(command, timeout=default_timeout)
    raw_additional_permissions = arguments.get("additional_permissions")
    additional_permissions_is_invalid = False
    if "additional_permissions" in arguments and raw_additional_permissions is not None and not isinstance(
        raw_additional_permissions, Mapping
    ):
        additional_permissions_is_invalid = True
        additional_permissions_value: Mapping[str, Any] | None = None
    else:
        additional_permissions_value = _optional_mapping_argument(arguments, "additional_permissions")
    return LocalHttpShellInvocation(
        command,
        workdir=_shell_workdir_from_arguments(arguments, default_cwd=default_cwd),
        timeout=_shell_timeout_from_arguments(arguments, default_timeout=default_timeout),
        login=_shell_login_from_arguments(arguments),
        shell=_optional_str_argument(arguments, "shell"),
        tty=_optional_bool_argument(arguments, "tty"),
        yield_time_ms=_shell_yield_time_from_arguments(arguments, default_ms=DEFAULT_LOCAL_HTTP_EXEC_YIELD_TIME_MS),
        max_output_tokens=_shell_max_output_tokens_from_arguments(arguments),
        sandbox_permissions=_optional_str_argument(arguments, "sandbox_permissions"),
        additional_permissions=additional_permissions_value,
        additional_permissions_is_invalid=additional_permissions_is_invalid,
        justification=_optional_str_argument(arguments, "justification"),
        prefix_rule=_shell_prefix_rule_from_arguments(arguments),
    )


def _shell_command_from_arguments(arguments: Any) -> str | None:
    if isinstance(arguments, str):
        return arguments if arguments else None
    if not isinstance(arguments, Mapping):
        return None
    for key in ("command", "cmd", "script"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
    argv = arguments.get("argv")
    if isinstance(argv, (list, tuple)) and all(isinstance(item, str) for item in argv):
        return subprocess.list2cmdline(list(argv))
    return None


def _shell_workdir_from_arguments(arguments: Mapping[str, Any], *, default_cwd: Path) -> Path | None:
    value = arguments.get("workdir")
    if value is None:
        value = arguments.get("cwd")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else Path(default_cwd) / path


def _shell_timeout_from_arguments(arguments: Mapping[str, Any], *, default_timeout: float | None) -> float | None:
    value = arguments.get("timeout_ms")
    if value is None:
        value = arguments.get("timeout")
    if value is None:
        return default_timeout
    if isinstance(value, bool):
        return default_timeout
    if isinstance(value, int | float):
        if value < 0:
            return default_timeout
        return float(value) / 1000.0
    return default_timeout


def _shell_login_from_arguments(arguments: Mapping[str, Any]) -> bool | None:
    value = arguments.get("login")
    return value if isinstance(value, bool) else None


def _optional_bool_argument(arguments: Mapping[str, Any], key: str) -> bool | None:
    value = arguments.get(key)
    return value if isinstance(value, bool) else None


def _optional_str_argument(arguments: Mapping[str, Any], key: str) -> str | None:
    value = arguments.get(key)
    return value if isinstance(value, str) and value else None


def _optional_mapping_argument(arguments: Mapping[str, Any], key: str) -> Mapping[str, Any] | None:
    value = arguments.get(key)
    if value is None:
        return None
    if not isinstance(value, Mapping):
        return None
    return value


def _shell_yield_time_from_arguments(
    arguments: Mapping[str, Any],
    *,
    default_ms: int | None = None,
    empty_stdin: bool = False,
) -> float | None:
    value = arguments.get("yield_time_ms")
    if isinstance(value, bool):
        return None
    if value is None:
        if default_ms is None:
            return None
        return _clamp_local_http_yield_time_ms(default_ms, empty_stdin=empty_stdin) / 1000.0
    if isinstance(value, int | float) and value >= 0:
        return _clamp_local_http_yield_time_ms(value, empty_stdin=empty_stdin) / 1000.0
    return None


def _clamp_local_http_yield_time_ms(value: int | float, *, empty_stdin: bool = False) -> float:
    if empty_stdin:
        return float(resolve_write_stdin_yield_time("", value))
    return float(clamp_yield_time(value))


def _shell_max_output_tokens_from_arguments(arguments: Mapping[str, Any]) -> int | None:
    value = arguments.get("max_output_tokens")
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float) and value > 0:
        return int(value)
    return None


def _effective_shell_output_max_chars(global_max_chars: int | None, max_output_tokens: int | None) -> int | None:
    resolved_max_output_tokens = DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS if max_output_tokens is None else max_output_tokens
    token_max_chars = _approx_bytes_for_tokens(resolved_max_output_tokens)
    if global_max_chars is None:
        return token_max_chars
    return min(global_max_chars, token_max_chars)


def _shell_prefix_rule_from_arguments(arguments: Mapping[str, Any]) -> tuple[str, ...] | None:
    value = arguments.get("prefix_rule")
    if isinstance(value, str) or not isinstance(value, (list, tuple)):
        return None
    if not all(isinstance(item, str) for item in value):
        return None
    return tuple(value)


def _run_shell_tool_command(
    command: str,
    *,
    cwd: Any,
    runner: Any,
    timeout: float | None,
    login: bool | None = None,
    shell_binary: str | None = None,
    output_max_chars: int | None = None,
) -> str:
    output, _success = _run_shell_tool_command_result(
        command,
        cwd=cwd,
        runner=runner,
        timeout=timeout,
        login=login,
        shell_binary=shell_binary,
        output_max_chars=output_max_chars,
    )
    return output


def _run_shell_tool_command_result(
    command: str,
    *,
    cwd: Any,
    runner: Any,
    timeout: float | None,
    login: bool | None = None,
    shell_binary: str | None = None,
    output_max_chars: int | None = None,
) -> tuple[str, bool]:
    try:
        kwargs = {
            "shell": True,
            "cwd": str(cwd),
            "capture_output": True,
            "text": True,
            "timeout": timeout,
        }
        if shell_binary:
            kwargs["executable"] = shell_binary
        if login is not None and runner is not subprocess.run:
            kwargs["login"] = login
        completed = runner(command, **kwargs)
    except subprocess.TimeoutExpired as exc:
        return (
            _truncate_shell_tool_output(
                f"exit_code: timeout\nstdout:\n{exc.stdout or ''}\nstderr:\n{exc.stderr or ''}".rstrip(),
                output_max_chars,
            ),
            False,
        )
    stdout = getattr(completed, "stdout", "") or ""
    stderr = getattr(completed, "stderr", "") or ""
    returncode = getattr(completed, "returncode", 0)
    return (
        _truncate_shell_tool_output(
            f"exit_code: {returncode}\nstdout:\n{stdout}\nstderr:\n{stderr}".rstrip(),
            output_max_chars,
        ),
        returncode == 0,
    )


def _truncate_shell_tool_output(output: str, max_chars: int | None) -> str:
    if max_chars is None or len(output.encode("utf-8")) <= max_chars:
        return output
    total_lines = len(output.splitlines())
    truncated = _truncate_middle_shell_tool_output(output, max_chars)
    return f"Total output lines: {total_lines}\n\n{truncated}"


def _truncate_middle_shell_tool_output(output: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return f"... {len(output)} chars truncated ..."
    marker = f"... {len(output)} chars truncated ..."
    marker_bytes = len(marker.encode("utf-8"))
    available = max(max_bytes - marker_bytes, 0)
    if available == 0:
        return marker
    encoded = output.encode("utf-8")
    head_bytes = available // 2
    tail_bytes = available - head_bytes
    head = encoded[:head_bytes].decode("utf-8", errors="ignore")
    tail = encoded[-tail_bytes:].decode("utf-8", errors="ignore") if tail_bytes else ""
    omitted = len(output) - len(head) - len(tail)
    return f"{head}... {omitted} chars truncated ...{tail}"


def _tool_name_from_item(item: Mapping[str, Any]) -> str:
    value = item.get("name") or item.get("tool") or item.get("server_label")
    return str(value or "")


def _tool_arguments_from_item(item: Mapping[str, Any]) -> Any:
    value = item.get("arguments")
    if value is None:
        value = item.get("input")
    if isinstance(value, str):
        try:
            import json

            return json.loads(value)
        except ValueError:
            return value
    return value if value is not None else {}


def _tool_output_from_item(item: Mapping[str, Any]) -> Any:
    value = item.get("output")
    if value is None:
        value = item.get("result")
    if value is None:
        value = item.get("content")
    return value if value is not None else ""


def reasoning_texts_from_local_http_exec_result(result: UserTurnSamplingResult) -> tuple[str, ...]:
    """Extract reasoning summary text from a local HTTP Responses payload."""

    texts: list[str] = []
    for payload in _raw_responses_payloads(result):
        for item in _response_output_mappings(payload):
            item_type = str(item.get("type") or "")
            if item_type not in {"reasoning", "reasoning_summary"}:
                continue
            text = _reasoning_text_from_item(item)
            if text:
                texts.append(text)
    return tuple(texts)


def _reasoning_text_from_item(item: Mapping[str, Any]) -> str:
    direct = _text_from_value(item.get("text") or item.get("content"))
    summary = _text_from_value(item.get("summary"))
    combined = "\n".join(part for part in (direct, summary) if part)
    return combined.strip()


def _text_from_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        for name in ("text", "summary", "content"):
            text = _text_from_value(value.get(name))
            if text:
                return text
        return ""
    if isinstance(value, (list, tuple)):
        parts = tuple(_text_from_value(item) for item in value)
        return "\n".join(part for part in parts if part)
    return ""


def usage_from_local_http_exec_result(result: UserTurnSamplingResult) -> Usage:
    """Extract exec usage from a local HTTP sampling result."""

    total = Usage()
    for payload in _raw_responses_payloads(result):
        usage = _usage_from_responses_payload(payload)
        total = Usage(
            input_tokens=total.input_tokens + usage.input_tokens,
            cached_input_tokens=total.cached_input_tokens + usage.cached_input_tokens,
            output_tokens=total.output_tokens + usage.output_tokens,
            reasoning_output_tokens=total.reasoning_output_tokens + usage.reasoning_output_tokens,
        )
    return total


def _usage_from_responses_payload(payload: Mapping[str, Any]) -> Usage:
    usage = payload.get("usage")
    if not isinstance(usage, Mapping):
        usage = payload.get("token_usage")
    if not isinstance(usage, Mapping):
        usage = payload.get("tokenUsage")
    if not isinstance(usage, Mapping):
        return Usage()

    input_details = _mapping_field(usage, "input_tokens_details", "inputTokensDetails")
    output_details = _mapping_field(usage, "output_tokens_details", "outputTokensDetails")
    return Usage(
        input_tokens=_int_field(usage, "input_tokens", "inputTokens"),
        cached_input_tokens=_int_field(input_details, "cached_tokens", "cachedTokens"),
        output_tokens=_int_field(usage, "output_tokens", "outputTokens"),
        reasoning_output_tokens=_int_field(output_details, "reasoning_tokens", "reasoningTokens"),
    )


def _raw_responses_payload(result: UserTurnSamplingResult) -> Any:
    raw = getattr(result, "raw_result", None)
    while raw is not None and not isinstance(raw, Mapping):
        nested = getattr(raw, "raw_result", None)
        if nested is None or nested is raw:
            break
        raw = nested
    return raw


def _raw_responses_payloads(result: UserTurnSamplingResult) -> tuple[Mapping[str, Any], ...]:
    raw_results = getattr(result, "raw_results", ()) or ()
    if not raw_results:
        raw_results = (getattr(result, "raw_result", None),)
    payloads: list[Mapping[str, Any]] = []
    for raw in raw_results:
        while raw is not None and not isinstance(raw, Mapping):
            nested = getattr(raw, "raw_result", None)
            if nested is None or nested is raw:
                break
            raw = nested
        if isinstance(raw, Mapping):
            payloads.append(raw)
    return tuple(payloads)


def _response_output_mappings(payload: Mapping[str, Any]) -> tuple[Mapping[str, Any], ...]:
    output = payload.get("output")
    if isinstance(output, Mapping):
        return (output,)
    if isinstance(output, (list, tuple)):
        return tuple(item for item in output if isinstance(item, Mapping))
    return ()


def _response_item_mapping(item: ResponseItem) -> Mapping[str, Any] | None:
    if isinstance(item, Mapping):
        return item
    to_mapping = getattr(item, "to_mapping", None)
    if not callable(to_mapping):
        return None
    mapping = to_mapping()
    return mapping if isinstance(mapping, Mapping) else None


def _merge_local_http_sampling_result(
    previous: UserTurnSamplingResult,
    tool_outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    followup: UserTurnSamplingResult,
) -> UserTurnSamplingResult:
    tool_response_items = response_items_from_local_http_tool_outputs(tool_outputs)
    previous_request_plans = tuple(getattr(previous, "request_plans", ()) or (previous.request_plan,))
    followup_request_plans = tuple(getattr(followup, "request_plans", ()) or (followup.request_plan,))
    previous_raw_results = tuple(getattr(previous, "raw_results", ()) or (previous.raw_result,))
    followup_raw_results = tuple(getattr(followup, "raw_results", ()) or (followup.raw_result,))
    return UserTurnSamplingResult(
        request_plan=followup.request_plan,
        response_items=previous.response_items + followup.response_items,
        tool_response_items=(
            tuple(getattr(previous, "tool_response_items", ()) or ())
            + tool_response_items
            + tuple(getattr(followup, "tool_response_items", ()) or ())
        ),
        request_plans=previous_request_plans + followup_request_plans,
        raw_results=previous_raw_results + followup_raw_results,
        raw_result=followup.raw_result,
    )


def _mapping_field(value: Any, *names: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    for name in names:
        item = value.get(name)
        if isinstance(item, Mapping):
            return item
    return {}


def _int_field(value: Any, *names: str) -> int:
    if not isinstance(value, Mapping):
        return 0
    for name in names:
        item = value.get(name)
        if isinstance(item, bool):
            return 0
        if isinstance(item, int):
            return item
        if isinstance(item, float):
            return int(item)
    return 0


def emit_local_http_exec_error(
    processor: HumanEventProcessor | JsonEventProcessor,
    message: str,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Render a local HTTP exec failure through the normal exec processors."""

    if isinstance(processor, JsonEventProcessor):
        processor.emit_json_lines(
            (
                ThreadEvent.turn_started(),
                ThreadEvent.turn_failed(ThreadErrorEvent(message)),
            ),
            stdout,
        )
        return

    processor.process_server_notification(
        exec_turn_completed_notification(
            "",
            "",
            (),
            status="failed",
            error={"message": message},
        ),
        stderr=stderr,
    )


__all__ = [
    "DEFAULT_OPENAI_BASE_URL",
    "DEFAULT_OPENAI_MODEL",
    "LOCAL_HTTP_EXEC_ENV",
    "LOCAL_HTTP_EXEC_MAX_TOOL_ROUNDS_ENV",
    "LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV",
    "LOCAL_HTTP_EXEC_TOOL_OUTPUT_MAX_CHARS_ENV",
    "DEFAULT_LOCAL_HTTP_EXEC_YIELD_TIME_MS",
    "DEFAULT_LOCAL_HTTP_WRITE_STDIN_YIELD_TIME_MS",
    "DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS",
    "LOCAL_HTTP_APPROX_BYTES_PER_TOKEN",
    "LOCAL_HTTP_EXEC_MIN_YIELD_TIME_MS",
    "LOCAL_HTTP_EXEC_MIN_EMPTY_STDIN_YIELD_TIME_MS",
    "LOCAL_HTTP_EXEC_MAX_YIELD_TIME_MS",
    "LOCAL_HTTP_EXEC_MAX_BACKGROUND_TERMINAL_TIMEOUT_MS",
    "LOCAL_HTTP_EXEC_EARLY_EXIT_GRACE_PERIOD_MS",
    "LOCAL_HTTP_EXEC_TRAILING_OUTPUT_GRACE_MS",
    "LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE",
    "LOCAL_HTTP_EXEC_OUTPUT_MAX_BYTES",
    "LOCAL_HTTP_EXEC_OUTPUT_MAX_TOKENS",
    "LOCAL_HTTP_MAX_UNIFIED_EXEC_PROCESSES",
    "LOCAL_HTTP_UNIFIED_EXEC_PROTECTED_RECENT_PROCESSES",
    "LocalHttpShellInvocation",
    "LocalHttpWriteStdinInvocation",
    "LocalHttpHeadTailBuffer",
    "LocalHttpExecSessionManager",
    "LocalHttpModelInfo",
    "LocalHttpProvider",
    "local_http_exec_command_output_schema",
    "local_http_exec_output_text",
    "local_http_write_stdin_tool_spec",
    "local_http_request_permissions_tool_spec",
    "local_http_request_permissions_unavailable_output",
    "local_http_write_stdin_unavailable_output",
    "local_http_shell_tools_built_tools",
    "local_http_shell_tool_spec",
    "local_http_apply_patch_approval_required_output",
    "local_http_apply_patch_tool_spec",
    "LocalHttpShellToolRouter",
    "align_local_http_exec_resume_model_client",
    "build_default_local_http_exec_runtime",
    "default_local_http_exec_auth",
    "default_local_http_exec_base_url",
    "default_local_http_exec_model",
    "emit_local_http_exec_error",
    "emit_local_http_exec_result",
    "final_text_from_response_items",
    "local_http_exec_enabled",
    "local_http_exec_max_tool_rounds",
    "local_http_generate_chunk_id",
    "local_http_retain_head_tail_output",
    "local_http_exec_schema_output_payload",
    "local_http_exec_shell_tools_enabled",
    "local_http_exec_tool_output_max_chars",
    "local_http_exec_config_summary",
    "local_http_shell_tool_approval_required_output",
    "local_http_shell_tool_auto_execute_allowed",
    "persist_local_http_exec_rollout",
    "persist_local_http_exec_resume_rollout",
    "reasoning_texts_from_local_http_exec_result",
    "resolve_local_http_exec_resume_rollout_path",
    "response_items_from_local_http_tool_outputs",
    "run_exec_user_turn_default_local_http_sampling",
    "run_exec_tool_output_http_sampling",
    "run_exec_resume_user_turn_http_sampling",
    "run_exec_user_turn_http_sampling",
    "run_exec_user_turn_with_shell_tools_http_sampling",
    "shell_tool_outputs_from_local_http_exec_result",
    "tool_call_items_from_local_http_exec_result",
    "tool_output_items_from_local_http_exec_result",
    "tool_timeline_items_from_local_http_exec_result",
    "usage_from_local_http_exec_result",
]


