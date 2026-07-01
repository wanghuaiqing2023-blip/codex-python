"""Local in-process runtime bridge for ``codex exec`` user turns."""

from __future__ import annotations

import os
import json
import inspect
import secrets
import shlex
import signal
import subprocess
import threading
import time
from collections import deque
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from itertools import count
from pathlib import Path
from typing import Any, TextIO
from uuid import uuid4


def _goal_debug_trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG") or os.environ.get("PYCODEX_GOAL_DEBUG_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        return


from pycodex.apply_patch import (
    apply_patch_action_to_disk,
    convert_apply_patch_to_protocol,
    create_apply_patch_freeform_tool,
    maybe_parse_apply_patch_verified,
    parse_patch,
    verify_apply_patch_args,
)
from pycodex.core.client import ModelClient
from pycodex.core.client_common import REVIEW_EXIT_INTERRUPTED_TMPL, REVIEW_EXIT_SUCCESS_TMPL, REVIEW_PROMPT
from pycodex.core.compact_remote import normalize_call_outputs
from pycodex.core.context import TurnAborted
from pycodex.execpolicy import (
    ExecApprovalRequest,
    ExecPolicyCommandOrigin,
    commands_for_exec_policy,
    create_exec_approval_requirement_for_command,
    match_exec_policy_rules_for_command,
)
from pycodex.features import Feature
from pycodex.core.tools.handlers.utils import (
    merge_permission_profiles,
    normalize_additional_permissions,
    permissions_are_preapproved,
)
from pycodex.core.http_transport import (
    http_sampling_stream_max_retries,
    http_transport_config_from_provider,
    model_client_http_sampler,
    model_client_websocket_preferred_sampler,
    prewarm_model_client_websocket_session,
    response_items_from_responses_payload,
    run_user_turn_http_sampling_from_session,
)
from pycodex.core.function_tool import FunctionCallError
from pycodex.core.tools.handlers.request_permissions import RequestPermissionsHandler
from pycodex.core.review_format import format_review_findings_block, render_review_output_text
from pycodex.core.review_prompts import resolve_review_request
from pycodex.rollout import (
    SessionMeta,
    ThreadSortKey,
    append_event_msg_to_rollout,
    append_turn_to_latest_thread_rollout,
    append_turn_to_thread_rollout,
    append_turn_to_rollout,
    find_thread_meta_by_name_str,
    find_thread_path_by_id_str,
    get_threads,
    materialize_session_rollout,
    read_event_msgs_from_rollout,
    read_model_history_from_rollout,
    read_thread_item_from_rollout,
    read_session_meta_line,
)
from pycodex.core.session.runtime import InMemoryCodexSession
from pycodex.core.shell import default_user_shell
from pycodex.core.tools.handlers.shell_spec import (
    CommandToolOptions,
    create_exec_command_tool,
    create_request_permissions_tool,
    create_write_stdin_tool,
    request_permissions_tool_description,
    unified_exec_output_schema,
)
from pycodex.core.tools.events import command_actions_from_argv
from pycodex.core.session.turn.runtime import (
    UserTurnSamplingResult,
    build_user_turn_responses_request_from_session,
    run_user_turn_sampling_from_session,
)
from pycodex.core.tools.handlers.view_image import (
    ViewImageHandler,
    ViewImageToolOptions,
    create_view_image_tool,
)
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
from pycodex.core.tools.context import ToolPayload
from pycodex.core.tools.sandboxing import ExecApprovalRequirement
from pycodex.shell_command import command_might_be_dangerous, is_dangerous_powershell_words
from pycodex.protocol import (
    AskForApproval,
    BaseInstructions,
    CodexErr,
    ContentItem,
    EventMsg,
    ExitedReviewModeEvent,
    FileChange,
    FileChangeItem,
    FileSystemAccessMode,
    FileSystemPermissions,
    FileSystemPath,
    FileSystemSandboxEntry,
    FileSystemSandboxPolicy,
    PatchApplyStatus,
    ResponseInputItem,
    ResponseItem,
    ReviewOutputEvent,
    RequestPermissionProfile,
    PermissionGrantScope,
    RequestPermissionsResponse,
    SandboxPermissions,
    TurnEnvironmentSelection,
    UserInput,
    approval_policy_display_value,
)
from pycodex.protocol import TurnAbortReason, TurnAbortedEvent, TurnItem
from pycodex.protocol.models import AdditionalPermissionProfile, FunctionCallOutputPayload
from pycodex.model_provider_info import CHATGPT_CODEX_BASE_URL, ModelProviderInfo

from .event_processor import HumanEventProcessor, JsonEventProcessor, exec_turn_completed_notification
from .events import (
    ExecThreadItem,
    ThreadErrorEvent,
    ThreadEvent,
    Usage,
    agent_message_item,
    command_execution_item,
    file_change_item,
    reasoning_item,
)
from .run import ExecRunPlan, InitialOperation
from .session import ExecSessionConfig, cwds_match


DEFAULT_OPENAI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_OPENAI_MODEL = "gpt-5.3-codex"
LOCAL_HTTP_EXEC_ENV = "PYCODEX_EXEC_LOCAL_HTTP"
CORE_EXEC_ENV = "PYCODEX_EXEC_CORE"
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
    default_reasoning_summary: Any = "auto"
    support_verbosity: bool = False
    apply_patch_tool_type: str | None = "freeform"
    input_modalities: tuple[str, ...] = ("text", "image")
    supports_image_detail_original: bool = False
    supports_parallel_tool_calls: bool = False
    context_window: int | None = 272_000
    max_context_window: int | None = 272_000
    effective_context_window_percent: int = 95

    def service_tier_for_request(self, service_tier: str | None) -> str | None:
        return service_tier

    def resolved_context_window(self) -> int | None:
        if self.context_window is None:
            return None
        percent = max(min(int(self.effective_context_window_percent), 100), 1)
        return int(self.context_window) * percent // 100


@dataclass(frozen=True)
class LocalHttpProvider:
    """Small provider value compatible with the stdlib HTTP transport."""

    base_url: str = DEFAULT_OPENAI_BASE_URL
    auth: Any = None
    name: str = "OpenAI"
    supports_websockets: bool = True
    stream_idle_timeout_ms: int = 300_000
    websocket_connect_timeout_ms: int = 15_000

    def is_azure_responses_endpoint(self) -> bool:
        return False

    def info(self) -> ModelProviderInfo:
        return ModelProviderInfo(
            name=self.name,
            base_url=self.base_url,
            supports_websockets=self.supports_websockets,
            stream_idle_timeout_ms=self.stream_idle_timeout_ms,
            websocket_connect_timeout_ms=self.websocket_connect_timeout_ms,
        )

    async def api_provider(self) -> Any:
        return self.info().to_api_provider(_local_http_auth_mode(self.auth))

    async def api_auth(self) -> Any:
        return self.auth


@dataclass(frozen=True)
class LocalHttpBearerAuthProvider:
    """Bearer/account header provider for first-party OAuth auth snapshots."""

    token: str | None = None
    account_id: str | None = None
    is_fedramp_account: bool = False

    def to_auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.token is not None and _local_http_valid_header_value(f"Bearer {self.token}"):
            headers["Authorization"] = f"Bearer {self.token}"
        if self.account_id is not None and _local_http_valid_header_value(self.account_id):
            headers["ChatGPT-Account-ID"] = self.account_id
        if self.is_fedramp_account:
            headers["X-OpenAI-Fedramp"] = "true"
        return headers


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


@dataclass(frozen=True)
class LocalHttpOutputBudget:
    """Model-output truncation budget for local HTTP exec tool output."""

    kind: str
    amount: int


@dataclass(frozen=True)
class LocalHttpApplyPatchCommand:
    """Verified apply_patch intercepted from an exec_command shell script."""

    action: Any | None = None
    changes: dict[Path, FileChange] | None = None
    error: str | None = None


LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES = frozenset(
    {
        "view_image",
        "web_search",
        "get_goal",
        "create_goal",
        "update_goal",
    }
)


class LocalHttpReviewModelInfo:
    """Model metadata view with Rust's review-task base instructions."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.base_instructions = REVIEW_PROMPT
        self.view_image_tool_disabled = True
        self.disabled_tool_names = LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES

    def get_model_instructions(self, _prompt: Any = None) -> str:
        return REVIEW_PROMPT

    def __getattr__(self, name: str) -> Any:
        return getattr(self.inner, name)


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
        if chars == "\x04":
            self.process.stdin.close()
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
        return body, not timed_out

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

    def __init__(
        self,
        base_router: Any = None,
        *,
        allow_login_shell: bool = True,
        exec_permission_approvals_enabled: bool = False,
        request_permissions_tool_enabled: bool = False,
        apply_patch_tool_enabled: bool = True,
        can_request_original_image_detail: bool = False,
        view_image_tool_enabled: bool = True,
        disabled_tool_names: Iterable[str] = (),
    ) -> None:
        self._base_router = base_router
        if not isinstance(allow_login_shell, bool):
            raise TypeError("allow_login_shell must be a bool")
        if not isinstance(exec_permission_approvals_enabled, bool):
            raise TypeError("exec_permission_approvals_enabled must be a bool")
        if not isinstance(request_permissions_tool_enabled, bool):
            raise TypeError("request_permissions_tool_enabled must be a bool")
        if not isinstance(apply_patch_tool_enabled, bool):
            raise TypeError("apply_patch_tool_enabled must be a bool")
        if not isinstance(can_request_original_image_detail, bool):
            raise TypeError("can_request_original_image_detail must be a bool")
        if not isinstance(view_image_tool_enabled, bool):
            raise TypeError("view_image_tool_enabled must be a bool")
        if isinstance(disabled_tool_names, (str, bytes)):
            raise TypeError("disabled_tool_names must be an iterable of strings")
        self._allow_login_shell = allow_login_shell
        self._exec_permission_approvals_enabled = exec_permission_approvals_enabled
        self._request_permissions_tool_enabled = request_permissions_tool_enabled
        self._apply_patch_tool_enabled = apply_patch_tool_enabled
        self._can_request_original_image_detail = can_request_original_image_detail
        self._view_image_tool_enabled = view_image_tool_enabled
        self._disabled_tool_names = frozenset(str(name) for name in disabled_tool_names)

    def model_visible_specs(self) -> list[dict[str, Any]]:
        specs: list[dict[str, Any]] = []
        if self._base_router is not None:
            base_specs = getattr(self._base_router, "model_visible_specs", None)
            if callable(base_specs):
                for spec in base_specs():
                    if isinstance(spec, Mapping):
                        spec_dict = dict(spec)
                        if _local_http_tool_spec_name(spec_dict) in self._disabled_tool_names:
                            continue
                        specs.append(spec_dict)
        if not any(_local_http_shell_tool_spec_matches(spec) for spec in specs):
            specs.append(
                local_http_shell_tool_spec(
                    allow_login_shell=self._allow_login_shell,
                    exec_permission_approvals_enabled=self._exec_permission_approvals_enabled,
                )
            )
        if not any(_local_http_write_stdin_tool_spec_matches(spec) for spec in specs):
            specs.append(local_http_write_stdin_tool_spec())
        if self._request_permissions_tool_enabled and not any(
            _local_http_request_permissions_tool_spec_matches(spec) for spec in specs
        ):
            specs.append(local_http_request_permissions_tool_spec())
        if self._apply_patch_tool_enabled and not any(
            _local_http_apply_patch_tool_spec_matches(spec) for spec in specs
        ):
            specs.append(local_http_apply_patch_tool_spec())
        if self._view_image_tool_enabled and not any(_local_http_view_image_tool_spec_matches(spec) for spec in specs):
            specs.append(
                local_http_view_image_tool_spec(
                    can_request_original_image_detail=self._can_request_original_image_detail,
                )
            )
        return specs


def local_http_shell_tool_spec(
    *,
    allow_login_shell: bool = True,
    exec_permission_approvals_enabled: bool = False,
) -> dict[str, Any]:
    """Return the Responses function tool spec used by local HTTP exec loop."""

    return create_exec_command_tool(
        CommandToolOptions(
            allow_login_shell=allow_login_shell,
            exec_permission_approvals_enabled=exec_permission_approvals_enabled,
        )
    )


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

    return unified_exec_output_schema()


def local_http_write_stdin_tool_spec() -> dict[str, Any]:
    """Return the Rust Codex ``write_stdin`` companion tool spec."""

    return create_write_stdin_tool()


def local_http_request_permissions_tool_spec() -> dict[str, Any]:
    """Return the Rust Codex ``request_permissions`` tool spec."""

    return create_request_permissions_tool(request_permissions_tool_description())


def local_http_apply_patch_tool_spec() -> dict[str, Any]:
    """Return the Responses custom tool spec for apply_patch."""

    return dict(create_apply_patch_freeform_tool(False).to_mapping())


def local_http_view_image_tool_spec(
    *,
    can_request_original_image_detail: bool = False,
) -> dict[str, Any]:
    """Return the Rust Codex ``view_image`` function tool spec."""

    return create_view_image_tool(
        ViewImageToolOptions(
            can_request_original_image_detail=can_request_original_image_detail,
        )
    )


def local_http_shell_tools_built_tools(
    base_built_tools: Any = None,
    *,
    config: ExecSessionConfig | None = None,
    model_info: Any = None,
) -> Any:
    """Wrap an optional built-tools callback with the local shell tool spec."""

    allow_login_shell = True if config is None else config.allow_login_shell
    exec_permission_approvals_enabled = False if config is None else config.exec_permission_approvals_enabled
    request_permissions_tool_enabled = False if config is None else config.request_permissions_tool_enabled
    apply_patch_tool_enabled = local_http_model_allows_apply_patch_tool(model_info)
    can_request_original_image_detail = local_http_model_can_request_original_image_detail(model_info)
    disabled_tool_names = local_http_model_disabled_tool_names(model_info)
    view_image_tool_enabled = local_http_model_allows_view_image_tool(model_info)

    def build(session: Any, turn_context: Any) -> Any:
        base_router = base_built_tools(session, turn_context) if callable(base_built_tools) else base_built_tools
        if inspect.isawaitable(base_router):
            async def resolve() -> LocalHttpShellToolRouter:
                return LocalHttpShellToolRouter(
                    await base_router,
                    allow_login_shell=allow_login_shell,
                    exec_permission_approvals_enabled=exec_permission_approvals_enabled,
                    request_permissions_tool_enabled=request_permissions_tool_enabled,
                    apply_patch_tool_enabled=apply_patch_tool_enabled,
                    can_request_original_image_detail=can_request_original_image_detail,
                    view_image_tool_enabled=view_image_tool_enabled,
                    disabled_tool_names=disabled_tool_names,
                )

            return resolve()
        return LocalHttpShellToolRouter(
            base_router,
            allow_login_shell=allow_login_shell,
            exec_permission_approvals_enabled=exec_permission_approvals_enabled,
            request_permissions_tool_enabled=request_permissions_tool_enabled,
            apply_patch_tool_enabled=apply_patch_tool_enabled,
            can_request_original_image_detail=can_request_original_image_detail,
            view_image_tool_enabled=view_image_tool_enabled,
            disabled_tool_names=disabled_tool_names,
        )

    return build


def local_http_model_allows_apply_patch_tool(model_info: Any) -> bool:
    """Return whether Rust would expose apply_patch for this local model view."""

    if model_info is None:
        return True
    missing = object()
    apply_patch_tool_type = getattr(model_info, "apply_patch_tool_type", missing)
    if apply_patch_tool_type is missing:
        return True
    return apply_patch_tool_type is not None


def local_http_model_supports_image_inputs(model_info: Any) -> bool:
    """Return whether the local model view can consume image input content."""

    if model_info is None:
        return True
    modalities = getattr(model_info, "input_modalities", None)
    if modalities is None:
        return True
    try:
        return any(str(modality).lower().split(".")[-1] == "image" for modality in modalities)
    except TypeError:
        return False


def local_http_model_can_request_original_image_detail(model_info: Any) -> bool:
    """Return whether view_image may request original-resolution detail."""

    if model_info is None:
        return False
    return bool(getattr(model_info, "supports_image_detail_original", False))


def local_http_model_allows_view_image_tool(model_info: Any) -> bool:
    """Return whether the model view should expose the view_image tool."""

    if bool(getattr(model_info, "view_image_tool_disabled", False)):
        return False
    return "view_image" not in local_http_model_disabled_tool_names(model_info)


def local_http_model_disabled_tool_names(model_info: Any) -> frozenset[str]:
    """Return direct tool names hidden from this local model view."""

    raw_names = getattr(model_info, "disabled_tool_names", ())
    if raw_names is None:
        return frozenset()
    if isinstance(raw_names, (str, bytes)):
        return frozenset((str(raw_names),))
    try:
        return frozenset(str(name) for name in raw_names)
    except TypeError:
        return frozenset()


def _local_http_tool_spec_name(spec: Mapping[str, Any]) -> str:
    return str(spec.get("name") or spec.get("tool") or spec.get("server_label") or "")


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


def _local_http_view_image_tool_spec_matches(spec: Mapping[str, Any]) -> bool:
    return spec.get("type") == "function" and spec.get("name") == "view_image"


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
    return False


def local_core_exec_enabled(env: Any = None) -> bool:
    """Return true when the direct in-memory core exec path is enabled."""

    source = os.environ if env is None else env
    explicit_state = str(source.get(CORE_EXEC_ENV, "")).strip().lower()
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
    local_http_state = str(source.get(LOCAL_HTTP_EXEC_ENV, "")).strip().lower()
    if local_http_state in {
        "1",
        "true",
        "yes",
        "on",
        "enable",
        "enabled",
    }:
        return False
    if local_http_state in {"0", "false", "no", "off", "disable", "disabled"}:
        return True
    return True


def local_http_exec_shell_tools_enabled(env: Any = None) -> bool:
    """Return true when local HTTP exec should run the legacy shell tool loop."""

    source = os.environ if env is None else env
    explicit_state = str(source.get(LOCAL_HTTP_EXEC_SHELL_TOOLS_ENV, "")).strip().lower()
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
    return False


def local_http_exec_max_tool_rounds(env: Any = None, default: int | None = None) -> int | None:
    """Resolve the local HTTP exec shell tool loop round limit."""

    if default is not None:
        if isinstance(default, bool) or not isinstance(default, int):
            raise TypeError("default must be an integer or None")
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
        return auth
    if _local_http_auth_uses_codex_backend(auth):
        return _local_http_bearer_auth_provider_from_auth(auth)
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
    base_url = default_local_http_exec_base_url(
        env=source,
        config_toml=config_toml,
        provider_id=provider_id,
        auth=auth,
    )
    provider = LocalHttpProvider(
        base_url=base_url,
        auth=resolved_auth,
        supports_websockets=_config_provider_supports_websockets(config_toml, provider_id, base_url),
    )
    model_info = LocalHttpModelInfo(
        slug=model,
        supports_reasoning_summaries=_config_or_default_model_supports_reasoning_summaries(
            config_toml,
            provider_id,
            model,
            base_url,
        ),
        default_reasoning_summary=_config_or_default_model_reasoning_summary(config_toml, model),
        supports_parallel_tool_calls=_config_provider_supports_parallel_tool_calls(config_toml, provider_id),
        context_window=_config_model_context_window(config_toml) or 272_000,
        max_context_window=272_000,
    )
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
    auth: Any = None,
) -> str:
    """Resolve the default local HTTP exec provider base URL."""

    source = os.environ if env is None else env
    configured = source.get("OPENAI_BASE_URL") or _config_provider_base_url(config_toml, provider_id)
    if configured:
        return configured
    if _local_http_auth_uses_codex_backend(auth):
        return CHATGPT_CODEX_BASE_URL
    return DEFAULT_OPENAI_BASE_URL


def _local_http_auth_mode(auth: Any) -> str | None:
    if auth is None:
        return None
    if isinstance(auth, Mapping):
        value = auth.get("auth_mode") or auth.get("mode")
    else:
        value = getattr(auth, "auth_mode", None)
        if callable(value):
            value = value()
    return str(value).strip().lower() if value is not None else None


def _local_http_auth_uses_codex_backend(auth: Any) -> bool:
    mode = _local_http_auth_mode(auth)
    return mode in {
        "chatgpt",
        "chatgpt_auth",
        "chatgpt_auth_tokens",
        "chatgptauthtokens",
        "codex_backend",
    }


def _local_http_bearer_auth_provider_from_auth(auth: Any) -> LocalHttpBearerAuthProvider:
    token_method = getattr(auth, "get_token", None)
    token = token_method() if callable(token_method) else _local_http_get(auth, "token")
    account_method = getattr(auth, "get_account_id", None)
    account_id = account_method() if callable(account_method) else _local_http_get(auth, "account_id")
    tokens = _local_http_get(auth, "tokens")
    if isinstance(tokens, Mapping):
        token = token or tokens.get("access_token")
        account_id = account_id or tokens.get("account_id")
    fedramp_method = getattr(auth, "is_fedramp_account", None)
    is_fedramp = bool(fedramp_method()) if callable(fedramp_method) else bool(_local_http_get(auth, "is_fedramp_account", False))
    return LocalHttpBearerAuthProvider(
        token=str(token) if token is not None else None,
        account_id=str(account_id) if account_id is not None else None,
        is_fedramp_account=is_fedramp,
    )


def _local_http_get(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _local_http_valid_header_value(value: str) -> bool:
    return not any(char in value for char in "\r\n\0")


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


def _config_provider_supports_parallel_tool_calls(
    config_toml: Mapping[str, Any] | None,
    provider_id: str | None,
) -> bool:
    if config_toml is None or provider_id is None:
        return False
    providers = config_toml.get("model_providers")
    if not isinstance(providers, Mapping):
        return False
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return False
    return provider.get("supports_parallel_tool_calls") is True


def _config_or_default_model_supports_reasoning_summaries(
    config_toml: Mapping[str, Any] | None,
    provider_id: str | None,
    model: str,
    base_url: str,
) -> bool:
    configured = _config_model_supports_reasoning_summaries(config_toml)
    if configured is not None:
        return configured
    return _default_model_supports_reasoning_summaries(provider_id, model, base_url)


def _config_model_supports_reasoning_summaries(config_toml: Mapping[str, Any] | None) -> bool | None:
    if config_toml is None:
        return None
    value = config_toml.get("model_supports_reasoning_summaries")
    return value if isinstance(value, bool) else None


def _config_or_default_model_reasoning_summary(config_toml: Mapping[str, Any] | None, model: str) -> Any:
    if config_toml is not None:
        configured = config_toml.get("model_reasoning_summary")
        if isinstance(configured, str) and configured:
            return configured
    return _default_model_reasoning_summary(model)


def _config_model_context_window(config_toml: Mapping[str, Any] | None) -> int | None:
    if config_toml is None:
        return None
    value = config_toml.get("model_context_window")
    if isinstance(value, bool):
        return None
    if isinstance(value, int) and value > 0:
        return value
    return None


def _default_model_reasoning_summary(model: str) -> str:
    try:
        from pycodex.models_manager import load_remote_models_from_file

        candidates = load_remote_models_from_file()
    except Exception:
        return "auto"
    best = None
    model_text = str(model)
    for candidate in candidates:
        slug = getattr(candidate, "slug", None)
        if not isinstance(slug, str) or not model_text.startswith(slug):
            continue
        if best is None or len(slug) > len(str(getattr(best, "slug", ""))):
            best = candidate
    if best is None:
        return "auto"
    summary = getattr(best, "default_reasoning_summary", None)
    value = getattr(summary, "value", summary)
    return str(value) if value is not None else "auto"


def _default_model_supports_reasoning_summaries(provider_id: str | None, model: str, base_url: str) -> bool:
    if provider_id != "openai" and base_url.rstrip("/") not in {
        DEFAULT_OPENAI_BASE_URL,
        CHATGPT_CODEX_BASE_URL,
    }:
        return False
    slug = str(model).lower()
    return slug.startswith("gpt-5") or "codex" in slug


def _config_provider_supports_websockets(
    config_toml: Mapping[str, Any] | None,
    provider_id: str | None,
    base_url: str,
) -> bool:
    if provider_id == "openai" and base_url.rstrip("/") in {
        DEFAULT_OPENAI_BASE_URL,
        CHATGPT_CODEX_BASE_URL,
    }:
        return True
    if config_toml is None or provider_id is None:
        return False
    providers = config_toml.get("model_providers")
    if not isinstance(providers, Mapping):
        return False
    provider = providers.get(provider_id)
    if not isinstance(provider, Mapping):
        return False
    return provider.get("supports_websockets") is True


def local_http_exec_config_summary(
    config: ExecSessionConfig,
    *,
    model: str | None = None,
    provider_id: str | None = None,
    session_id: str = "local-http",
    thread_id: str | None = None,
    initial_messages: tuple[EventMsg, ...] | list[EventMsg] | tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]] | None = None,
    rollout_path: Path | str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build config/session-configured mappings for exec config summaries."""

    resolved_model = model or default_local_http_exec_model(config)
    resolved_provider = provider_id or config.model_provider_id or "openai"
    resolved_thread_id = thread_id or session_id
    approval = approval_policy_display_value(config.approval_policy)
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
    if initial_messages is not None:
        session_configured["initial_messages"] = [_event_msg_mapping(message) for message in initial_messages]
    if rollout_path is not None:
        session_configured["rollout_path"] = str(rollout_path)
    return config_mapping, session_configured


def local_http_exec_initial_messages_from_rollout(path: Path | str) -> tuple[EventMsg, ...]:
    """Read rollout protocol events for a resumed local HTTP session summary."""

    return read_event_msgs_from_rollout(Path(path))


def _event_msg_mapping(message: EventMsg | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(message, EventMsg):
        return _drop_none_values(message.to_mapping())
    return _drop_none_values(dict(message))


def _drop_none_values(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _drop_none_values(item) for key, item in value.items() if item is not None}
    if isinstance(value, list):
        return [_drop_none_values(item) for item in value]
    if isinstance(value, tuple):
        return [_drop_none_values(item) for item in value]
    return value


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
    _append_local_http_interrupted_event_to_rollout(rollout_path, result, timestamp=timestamp)
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
        path = append_turn_to_thread_rollout(
            codex_home,
            thread_id,
            input_payload,
            response_payloads,
            timestamp=timestamp,
            cwd=config.cwd,
        )
        if path is not None:
            _append_local_http_interrupted_event_to_rollout(path, result, timestamp=timestamp)
        return path
    if resume_last:
        path = append_turn_to_latest_thread_rollout(
            codex_home,
            input_payload,
            response_payloads,
            current_cwd=config.cwd,
            include_all=include_all,
            timestamp=timestamp,
        )
        if path is not None:
            _append_local_http_interrupted_event_to_rollout(path, result, timestamp=timestamp)
        return path
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
    max_tool_rounds: int | None = None,
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
    history_items = read_model_history_from_rollout(rollout_path)
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
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    append_turn_to_rollout(
        rollout_path,
        _local_http_input_rollout_payload(input_items),
        _local_http_response_rollout_payloads(result),
        timestamp=timestamp,
        cwd=config.cwd,
    )
    _append_local_http_interrupted_event_to_rollout(rollout_path, result, timestamp=timestamp)
    return result


async def run_exec_resume_user_turn_core_http_sampling(
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
    resolved_rollout_path: Path | None = None,
    max_tool_followups: int | None = None,
    auth_manager: Any = None,
) -> UserTurnSamplingResult:
    """Run a resumed ``codex exec`` turn through the in-memory core loop."""

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
    history_items = read_model_history_from_rollout(rollout_path)
    result = await run_exec_user_turn_core_http_sampling(
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
        max_tool_followups=max_tool_followups,
        auth_manager=auth_manager,
    )
    operation = plan.initial_operation
    input_items = operation.items if operation.kind == "user_turn" else ()
    timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    append_turn_to_rollout(
        rollout_path,
        _local_http_input_rollout_payload(input_items),
        _local_http_response_rollout_payloads(result),
        timestamp=timestamp,
        cwd=config.cwd,
    )
    _append_local_http_interrupted_event_to_rollout(rollout_path, result, timestamp=timestamp)
    return result


def _local_http_input_rollout_payload(input_items: tuple[Any, ...] | list[Any]) -> dict[str, Any] | None:
    if not input_items:
        return None
    return ResponseItem.from_response_input_item(ResponseInputItem.from_user_inputs(tuple(input_items))).to_mapping()


def _local_http_response_rollout_payloads(result: UserTurnSamplingResult) -> tuple[dict[str, Any], ...]:
    prompt_visible_items = _local_http_prompt_visible_rollout_items(result)
    if _local_http_result_turn_status(result) == "interrupted" and not _local_http_result_has_review_rollout_message(result):
        prompt_visible_items = prompt_visible_items + (_local_http_interrupted_turn_marker_item(),)
    return tuple(_response_item_rollout_payload(item) for item in prompt_visible_items)


def _local_http_result_has_review_rollout_message(result: UserTurnSamplingResult) -> bool:
    summary = getattr(result, "stream_runtime_state_summary", None)
    if not isinstance(summary, Mapping):
        return False
    message = summary.get("review_rollout_user_message")
    return isinstance(message, str) and bool(message)


def _local_http_interrupted_turn_marker_item() -> ResponseItem:
    return TurnAborted(TurnAborted.INTERRUPTED_GUIDANCE).into_response_item()


def _append_local_http_interrupted_event_to_rollout(
    rollout_path: Path,
    result: UserTurnSamplingResult,
    *,
    timestamp: str,
) -> None:
    if _local_http_result_turn_status(result) != "interrupted":
        return
    append_event_msg_to_rollout(
        rollout_path,
        EventMsg.with_payload(
            "turn_aborted",
            TurnAbortedEvent(
                turn_id=None,
                reason=TurnAbortReason.INTERRUPTED,
            ),
        ),
        timestamp=timestamp,
    )


def _local_http_prompt_visible_rollout_items(result: UserTurnSamplingResult) -> tuple[ResponseItem, ...]:
    tool_response_items = tuple(getattr(result, "tool_response_items", ()) or ())
    raw_payloads = _raw_responses_payloads(result)
    if raw_payloads and not tool_response_items:
        raw_items = []
        for payload in raw_payloads:
            try:
                raw_items.extend(response_items_from_responses_payload(payload))
            except (KeyError, TypeError, ValueError):
                continue
        if raw_items:
            return _normalize_local_http_rollout_items(tuple(raw_items))
    if len(raw_payloads) <= 1:
        return _normalize_local_http_rollout_items(tuple(result.response_items) + tool_response_items)

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
    return _normalize_local_http_rollout_items(tuple(items) if items else tuple(result.response_items) + tool_response_items)


def _normalize_local_http_rollout_items(items: tuple[Any, ...]) -> tuple[Any, ...]:
    if not all(isinstance(item, ResponseItem) for item in items):
        return items
    return normalize_call_outputs(items)


def _tool_call_count(items: tuple[ResponseItem, ...]) -> int:
    count = 0
    for item in items:
        item_type = str(getattr(item, "type", ""))
        if item_type in {"function_call", "custom_tool_call"}:
            count += 1
        elif (
            item_type == "tool_search_call"
            and isinstance(getattr(item, "call_id", None), str)
            and getattr(item, "execution", None) == "client"
        ):
            count += 1
    return count


def _response_item_rollout_payload(item: Any) -> dict[str, Any]:
    to_mapping = getattr(item, "to_mapping", None)
    if callable(to_mapping):
        return dict(to_mapping())
    if isinstance(item, Mapping):
        return dict(item)
    raise TypeError(f"response item is not serializable to rollout payload: {type(item).__name__}")


@dataclass(frozen=True)
class _ExecConfigFeatures:
    exec_permission_approvals_enabled: bool = False
    request_permissions_tool_enabled: bool = False
    goal_tools_enabled: bool = False

    def enabled(self, feature: Feature) -> bool:
        if feature is Feature.EXEC_PERMISSION_APPROVALS:
            return self.exec_permission_approvals_enabled
        if feature is Feature.REQUEST_PERMISSIONS_TOOL:
            return self.request_permissions_tool_enabled
        if feature is Feature.GOALS:
            return self.goal_tools_enabled
        return False


def _in_memory_exec_session(
    config: ExecSessionConfig,
    model_info: Any,
    *,
    environments: tuple[TurnEnvironmentSelection, ...] = (),
    event_observer: Any = None,
    thread_id: str | None = None,
    state_db: Any = None,
    goal_tools_enabled: bool = False,
) -> InMemoryCodexSession:
    reasoning_summary = config.model_reasoning_summary
    if reasoning_summary is None:
        reasoning_summary = getattr(model_info, "default_reasoning_summary", "auto")
    return InMemoryCodexSession(
        cwd=config.cwd,
        thread_id=thread_id or "thread",
        model_info=model_info,
        user_instructions=config.user_instructions,
        base_instructions=_base_instructions_from_model_info(model_info),
        workspace_roots=config.workspace_roots,
        request_permissions_callback=config.request_permissions_callback,
        approval_policy=config.approval_policy,
        approvals_reviewer=config.approvals_reviewer,
        permission_profile=config.permission_profile,
        allow_login_shell=config.allow_login_shell,
        file_system_sandbox_policy=config.permission_profile.file_system_sandbox_policy(),
        features=_ExecConfigFeatures(
            exec_permission_approvals_enabled=config.exec_permission_approvals_enabled,
            request_permissions_tool_enabled=config.request_permissions_tool_enabled,
            goal_tools_enabled=goal_tools_enabled,
        ),
        state_db=state_db,
        goal_tools_enabled_value=goal_tools_enabled,
        _granted_session_permissions=config.granted_session_permissions,
        environments=environments,
        event_observer=event_observer,
        reasoning_effort=config.reasoning_effort,
        reasoning_summary=reasoning_summary,
        service_tier=config.service_tier,
    )


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
    session = _in_memory_exec_session(
        config,
        model_info,
        environments=(TurnEnvironmentSelection("local", str(config.cwd)),),
    )
    if history_items:
        turn_context = await session.new_default_turn()
        await session.record_conversation_items(turn_context, tuple(history_items))
    try:
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
            summary=config.model_reasoning_summary,
            service_tier=config.service_tier,
            output_schema=operation.output_schema,
        )
    except CodexErr as exc:
        _attach_local_http_session_events(exc, session)
        raise


async def run_exec_user_turn_core_sampling(
    config: ExecSessionConfig,
    plan: ExecRunPlan,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    sampler: Any,
    *,
    built_tools: Any = None,
    history_items: tuple[ResponseItem, ...] | list[ResponseItem] = (),
    max_tool_followups: int | None = None,
    session_event_observer: Any = None,
    cancellation_token: Any = None,
    codex_home: Path | str | None = None,
) -> UserTurnSamplingResult:
    """Run a prepared ``codex exec`` user turn through the in-memory core loop."""

    operation = plan.initial_operation
    if operation.kind != "user_turn":
        raise ValueError("local exec core runtime currently supports only user_turn operations")
    state_runtime = await _state_runtime_for_goal_tools(codex_home, config, provider)
    _goal_debug_trace(
        "goal_core_sampling_start",
        prompt_summary=getattr(plan, "prompt_summary", None),
        state_runtime=state_runtime is not None,
        max_tool_followups=max_tool_followups,
    )
    session = _in_memory_exec_session(
        config,
        model_info,
        environments=(TurnEnvironmentSelection("local", str(config.cwd)),),
        event_observer=session_event_observer,
        thread_id=_model_client_thread_id(model_client),
        state_db=state_runtime,
        goal_tools_enabled=state_runtime is not None,
    )
    try:
        if history_items:
            turn_context = await session.new_default_turn()
            await session.record_conversation_items(turn_context, tuple(history_items))
        result = await run_user_turn_sampling_from_session(
            session,
            operation.items,
            model_client,
            provider,
            model_info,
            sampler,
            built_tools=built_tools,
            effort=config.reasoning_effort,
            summary=config.model_reasoning_summary,
            service_tier=config.service_tier,
            output_schema=operation.output_schema,
            max_tool_followups=max_tool_followups,
            cancellation_token=cancellation_token,
        )
        _goal_debug_trace(
            "goal_core_sampling_finished",
            prompt_summary=getattr(plan, "prompt_summary", None),
            request_count=len(getattr(result, "request_plans", ()) or ()),
            response_items=len(getattr(result, "response_items", ()) or ()),
            tool_response_items=len(getattr(result, "tool_response_items", ()) or ()),
            last_agent_message=bool(getattr(result, "last_agent_message", None)),
        )
        return result
    except CodexErr as exc:
        _attach_local_http_session_events(exc, session)
        raise
    finally:
        close = getattr(state_runtime, "close", None)
        if callable(close):
            closed = close()
            if inspect.isawaitable(closed):
                await closed


async def _state_runtime_for_goal_tools(
    codex_home: Path | str | None,
    config: ExecSessionConfig,
    provider: Any,
) -> Any:
    if codex_home is None or bool(getattr(config, "ephemeral", False)):
        return None
    from pycodex.state.state_runtime import StateRuntime

    return await StateRuntime.init(Path(codex_home), _runtime_default_provider_id(config, provider))


def _model_client_thread_id(model_client: Any) -> str | None:
    state = getattr(model_client, "state", None)
    value = getattr(state, "thread_id", None)
    if value is None:
        value = getattr(model_client, "thread_id", None)
    return str(value) if value is not None else None


def _runtime_default_provider_id(config: ExecSessionConfig, provider: Any) -> str:
    value = getattr(config, "model_provider_id", None)
    if isinstance(value, str) and value:
        return value
    if isinstance(provider, Mapping):
        value = provider.get("id") or provider.get("name")
    else:
        value = getattr(provider, "id", None) or getattr(provider, "name", None)
    return str(value) if value else "openai"


async def run_exec_user_turn_core_http_sampling(
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
    max_tool_followups: int | None = None,
    auth_manager: Any = None,
    codex_home: Path | str | None = None,
    session_event_observer: Any = None,
    cancellation_token: Any = None,
) -> UserTurnSamplingResult:
    """Run ``codex exec`` through the in-memory core loop with stdlib HTTP sampling."""

    if auth_manager is None and codex_home is not None:
        from pycodex.login.auth.manager import AuthManager

        auth_manager = await AuthManager.new(codex_home, True)

    def transport_config() -> Any:
        return http_transport_config_from_provider(
            model_client,
            provider,
            auth=_local_http_auth_for_recovered_manager(auth_manager, auth),
            endpoint=endpoint,
            timeout=timeout,
        )

    sampler = model_client_http_sampler(
        model_client.new_session(),
        transport_config(),
        opener=opener,
        max_retries=http_sampling_stream_max_retries(provider),
        auth_manager=auth_manager,
        config_factory=transport_config,
    )
    return await run_exec_user_turn_core_sampling(
        config,
        plan,
        model_client,
        provider,
        model_info,
        sampler,
        built_tools=built_tools,
        history_items=history_items,
        max_tool_followups=max_tool_followups,
        session_event_observer=session_event_observer,
        cancellation_token=cancellation_token,
        codex_home=codex_home,
    )


async def run_exec_user_turn_core_sampling_websocket_preferred(
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
    max_tool_followups: int | None = None,
    auth_manager: Any = None,
    codex_home: Path | str | None = None,
    session_event_observer: Any = None,
    stream_event_observer: Any = None,
    model_session: Any = None,
    cancellation_token: Any = None,
) -> UserTurnSamplingResult:
    """Run a core user turn through Rust's websocket-preferred transport shape."""

    _goal_debug_trace(
        "goal_ws_preferred_start",
        prompt_summary=getattr(plan, "prompt_summary", None),
        has_model_session=model_session is not None,
        codex_home=bool(codex_home),
    )
    if auth_manager is None and codex_home is not None:
        from pycodex.login.auth.manager import AuthManager

        auth_manager = await AuthManager.new(codex_home, True)

    if model_session is None:
        model_session = model_client.new_session()

    def transport_config() -> Any:
        return http_transport_config_from_provider(
            model_client,
            provider,
            auth=_local_http_auth_for_recovered_manager(auth_manager, auth),
            endpoint=endpoint,
            timeout=timeout,
        )

    sampler = model_client_websocket_preferred_sampler(
        model_session,
        transport_config(),
        opener=opener,
        max_retries=http_sampling_stream_max_retries(provider),
        auth_manager=auth_manager,
        config_factory=transport_config,
        stream_event_observer=stream_event_observer,
    )
    try:
        result = await run_exec_user_turn_core_sampling(
            config,
            plan,
            model_client,
            provider,
            model_info,
            sampler,
            built_tools=built_tools,
            history_items=history_items,
            max_tool_followups=max_tool_followups,
            session_event_observer=session_event_observer,
            cancellation_token=cancellation_token,
            codex_home=codex_home,
        )
        _goal_debug_trace(
            "goal_ws_preferred_finished",
            prompt_summary=getattr(plan, "prompt_summary", None),
            request_count=len(getattr(result, "request_plans", ()) or ()),
            response_items=len(getattr(result, "response_items", ()) or ()),
            tool_response_items=len(getattr(result, "tool_response_items", ()) or ()),
        )
        return result
    finally:
        close = getattr(model_session, "close", None)
        if callable(close):
            close()


async def prewarm_exec_core_websocket_session(
    config: ExecSessionConfig,
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    built_tools: Any = None,
    auth_manager: Any = None,
    codex_home: Path | str | None = None,
    model_session: Any = None,
) -> Any | None:
    """Build a Rust-shaped startup prompt and prewarm its websocket session."""

    if auth_manager is None and codex_home is not None:
        from pycodex.login.auth.manager import AuthManager

        auth_manager = await AuthManager.new(codex_home, True)
    if model_session is None:
        model_session = model_client.new_session()
    session = _in_memory_exec_session(
        config,
        model_info,
        environments=(TurnEnvironmentSelection("local", str(config.cwd)),),
    )
    request_plan = await build_user_turn_responses_request_from_session(
        session,
        (),
        model_client,
        provider,
        model_info,
        built_tools=built_tools,
        effort=config.reasoning_effort,
        summary=config.model_reasoning_summary,
        service_tier=config.service_tier,
    )

    def transport_config() -> Any:
        return http_transport_config_from_provider(
            model_client,
            provider,
            auth=_local_http_auth_for_recovered_manager(auth_manager, auth),
            endpoint=endpoint,
            timeout=timeout,
        )

    result = await prewarm_model_client_websocket_session(
        model_session,
        transport_config(),
        request=request_plan.request,
    )
    return model_session if result is not None else None


def _local_http_auth_for_recovered_manager(auth_manager: Any, fallback_auth: Any) -> Any:
    if auth_manager is None:
        return fallback_auth
    cached = auth_manager.auth_cached() if callable(getattr(auth_manager, "auth_cached", None)) else None
    if cached is None:
        return fallback_auth
    if _local_http_auth_uses_codex_backend(cached):
        return _local_http_bearer_auth_provider_from_auth(cached)
    return cached


def local_http_review_user_turn_plan(config: ExecSessionConfig, plan: ExecRunPlan) -> ExecRunPlan:
    """Convert an exec review operation into the user turn run by Rust's ReviewTask."""

    review_plan, _review_request = _local_http_review_plan_and_request(config, plan)
    return review_plan


def _local_http_review_plan_and_request(config: ExecSessionConfig, plan: ExecRunPlan) -> tuple[ExecRunPlan, Any]:
    operation = plan.initial_operation
    if operation.kind != "review" or operation.review_request is None:
        raise ValueError("local exec review runtime requires a review initial operation")
    resolved = resolve_review_request(operation.review_request, config.cwd)
    return (
        ExecRunPlan(
            InitialOperation.user_turn((UserInput.text_input(resolved.prompt),)),
            resolved.user_facing_hint,
        ),
        resolved.to_review_request(),
    )


async def run_exec_review_http_sampling(
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
    max_tool_rounds: int | None = None,
    use_shell_tools: bool = False,
) -> UserTurnSamplingResult:
    """Run a local HTTP review turn using Rust's review prompt and output rendering."""

    review_plan, review_request = _local_http_review_plan_and_request(config, plan)
    review_config = replace(config, user_instructions=None, approval_policy=AskForApproval.NEVER)
    review_model_info = LocalHttpReviewModelInfo(model_info)
    run_local_http_sampling = (
        run_exec_user_turn_with_shell_tools_http_sampling
        if use_shell_tools
        else run_exec_user_turn_http_sampling
    )
    kwargs: dict[str, Any] = {
        "auth": auth,
        "endpoint": endpoint,
        "timeout": timeout,
        "opener": opener,
        "built_tools": built_tools,
    }
    if run_local_http_sampling is run_exec_user_turn_with_shell_tools_http_sampling:
        kwargs.update(
            {
                "runner": runner,
                "tool_timeout": tool_timeout,
                "tool_output_max_chars": tool_output_max_chars,
                "max_tool_rounds": max_tool_rounds,
            }
        )
    result = await run_local_http_sampling(
        review_config,
        review_plan,
        model_client,
        provider,
        review_model_info,
        **kwargs,
    )
    return _render_local_http_review_result(result, review_request)


async def run_exec_review_core_http_sampling(
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
    max_tool_followups: int | None = None,
    auth_manager: Any = None,
) -> UserTurnSamplingResult:
    """Run a review turn through the in-memory core loop and render review output."""

    review_plan, review_request = _local_http_review_plan_and_request(config, plan)
    review_config = replace(config, user_instructions=None, approval_policy=AskForApproval.NEVER)
    review_model_info = LocalHttpReviewModelInfo(model_info)
    result = await run_exec_user_turn_core_http_sampling(
        review_config,
        review_plan,
        model_client,
        provider,
        review_model_info,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        opener=opener,
        built_tools=built_tools,
        max_tool_followups=max_tool_followups,
        auth_manager=auth_manager,
    )
    return _render_local_http_review_result(result, review_request)


def _render_local_http_review_result(result: UserTurnSamplingResult, review_request: Any | None = None) -> UserTurnSamplingResult:
    if _local_http_result_turn_status(result) == "interrupted":
        return _render_local_http_interrupted_review_result(result, review_request)
    review_output = parse_local_http_review_output(final_text_from_local_http_exec_result(result))
    rendered = render_review_output_text(review_output)
    rollout_user_message = render_local_http_review_rollout_user_message(review_output)
    rendered_item = ResponseItem.message(
        "assistant",
        (ContentItem.output_text(rendered),),
        id="review_rollout_assistant",
    )
    summary = dict(getattr(result, "stream_runtime_state_summary", None) or {})
    summary["review_output"] = review_output.to_mapping()
    summary["review_rollout_user_message"] = rollout_user_message
    session_events = tuple(getattr(result, "session_events", ()) or ())
    if review_request is not None:
        non_terminal_events, terminal_events = _split_local_http_review_terminal_events(session_events)
        session_events = (
            EventMsg.with_payload("entered_review_mode", review_request),
            *non_terminal_events,
            EventMsg.with_payload("exited_review_mode", ExitedReviewModeEvent(review_output)),
            *terminal_events,
        )
    return replace(
        result,
        response_items=(rendered_item,),
        session_events=session_events,
        stream_runtime_state_summary=summary,
        last_agent_message=rendered,
    )


def _render_local_http_interrupted_review_result(
    result: UserTurnSamplingResult,
    review_request: Any | None = None,
) -> UserTurnSamplingResult:
    rendered = "Review was interrupted. Please re-run /review and wait for it to complete."
    rendered_item = ResponseItem.message(
        "assistant",
        (ContentItem.output_text(rendered),),
        id="review_rollout_assistant",
    )
    summary = dict(getattr(result, "stream_runtime_state_summary", None) or {})
    summary.pop("review_output", None)
    summary["review_rollout_user_message"] = render_local_http_review_interrupted_rollout_user_message()
    session_events = tuple(getattr(result, "session_events", ()) or ())
    if review_request is not None:
        non_terminal_events, terminal_events = _split_local_http_review_terminal_events(session_events)
        session_events = (
            EventMsg.with_payload("entered_review_mode", review_request),
            *non_terminal_events,
            EventMsg.with_payload("exited_review_mode", ExitedReviewModeEvent(None)),
            *terminal_events,
        )
    return replace(
        result,
        response_items=(rendered_item,),
        session_events=session_events,
        stream_runtime_state_summary=summary,
        last_agent_message=rendered,
    )


def _split_local_http_review_terminal_events(session_events: tuple[Any, ...]) -> tuple[tuple[Any, ...], tuple[Any, ...]]:
    terminal: list[Any] = []
    non_terminal: list[Any] = []
    for event in session_events:
        if getattr(event, "type", None) in {"task_complete", "turn_complete"}:
            terminal.append(event)
        else:
            non_terminal.append(event)
    return tuple(non_terminal), tuple(terminal)


def local_http_review_rollout_input_items(result: UserTurnSamplingResult) -> tuple[UserInput, ...]:
    """Return parent-thread rollout input items for a rendered review result."""

    summary = getattr(result, "stream_runtime_state_summary", None)
    message = summary.get("review_rollout_user_message") if isinstance(summary, Mapping) else None
    if not isinstance(message, str) or not message:
        if _local_http_result_turn_status(result) == "interrupted":
            message = render_local_http_review_interrupted_rollout_user_message()
        else:
            review_output = parse_local_http_review_output(final_text_from_local_http_exec_result(result))
            message = render_local_http_review_rollout_user_message(review_output)
    return (UserInput.text_input(message),)


def render_local_http_review_interrupted_rollout_user_message() -> str:
    """Render Rust's parent-thread review interrupted user-action message."""

    return REVIEW_EXIT_INTERRUPTED_TMPL.replace("\r\n", "\n").replace("\r", "\n")


def render_local_http_review_rollout_user_message(review_output: ReviewOutputEvent) -> str:
    """Render Rust's parent-thread review history user-action message."""

    text = review_output.overall_explanation.strip()
    findings_str = text
    if review_output.findings:
        findings_str += f"\n{format_review_findings_block(review_output.findings)}"
    return REVIEW_EXIT_SUCCESS_TMPL.replace("\r\n", "\n").replace("\r", "\n").replace("{{results}}", findings_str)


def parse_local_http_review_output(text: str) -> ReviewOutputEvent:
    """Parse Rust review-task JSON output, falling back to plain explanation text."""

    try:
        return ReviewOutputEvent.from_mapping(json.loads(text))
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and start < end:
        try:
            return ReviewOutputEvent.from_mapping(json.loads(text[start : end + 1]))
        except (TypeError, ValueError, json.JSONDecodeError):
            pass
    return ReviewOutputEvent(overall_explanation=text)


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
    output_schema: Any = None,
) -> Any:
    """Run a follow-up model turn with tool output items in history."""

    session = _in_memory_exec_session(config, model_info)
    turn_context = await session.new_default_turn()
    if previous_result.response_items:
        await session.record_conversation_items(turn_context, previous_result.response_items)
    previous_tool_response_items = tuple(getattr(previous_result, "tool_response_items", ()) or ())
    if previous_tool_response_items:
        await session.record_conversation_items(turn_context, previous_tool_response_items)
    tool_response_items = response_items_from_local_http_tool_outputs(tool_outputs)
    if tool_response_items:
        await session.record_conversation_items(turn_context, tool_response_items)
    try:
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
            summary=config.model_reasoning_summary,
            service_tier=config.service_tier,
            output_schema=output_schema,
        )
    except CodexErr as exc:
        _attach_local_http_session_events(exc, session)
        raise


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
    max_tool_rounds: int | None = None,
    history_items: tuple[ResponseItem, ...] | list[ResponseItem] = (),
) -> Any:
    """Run a user turn and feed shell tool outputs back to the model."""

    if max_tool_rounds is not None:
        if isinstance(max_tool_rounds, bool) or not isinstance(max_tool_rounds, int):
            raise TypeError("max_tool_rounds must be an integer or None")
        if max_tool_rounds < 0:
            raise ValueError("max_tool_rounds must be non-negative")
    shell_built_tools = local_http_shell_tools_built_tools(
        built_tools,
        config=config,
        model_info=model_info,
    )
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
    turn_granted_permissions: AdditionalPermissionProfile | None = None
    rounds_completed = 0
    while max_tool_rounds is None or rounds_completed < max_tool_rounds:
        rounds_completed += 1
        effective_granted_permissions = merge_permission_profiles(
            config.granted_session_permissions,
            turn_granted_permissions,
        )
        tool_outputs = shell_tool_outputs_from_local_http_exec_result(
            result,
            config,
            runner=runner,
            timeout=tool_timeout,
            output_max_chars=tool_output_max_chars,
            granted_permissions=effective_granted_permissions,
            model_info=model_info,
        )
        if not tool_outputs:
            return result
        turn_granted_permissions = _merge_granted_permissions_from_tool_outputs(
            turn_granted_permissions,
            tool_outputs,
            scope=PermissionGrantScope.TURN,
        )
        session_granted_permissions = _merge_granted_permissions_from_tool_outputs(
            config.granted_session_permissions,
            tool_outputs,
            scope=PermissionGrantScope.SESSION,
        )
        if session_granted_permissions != config.granted_session_permissions:
            object.__setattr__(config, "granted_session_permissions", session_granted_permissions)
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
            output_schema=plan.initial_operation.output_schema,
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


def final_text_from_local_http_exec_result(result: UserTurnSamplingResult) -> str:
    """Return the final answer text for local HTTP exec rendering."""

    if _local_http_result_turn_status(result) == "interrupted":
        return ""
    final_text = final_text_from_response_items(result.response_items)
    if final_text:
        return final_text
    last_agent_message = getattr(result, "last_agent_message", None)
    return last_agent_message if isinstance(last_agent_message, str) else ""


def emit_local_http_exec_result(
    processor: HumanEventProcessor | JsonEventProcessor,
    result: UserTurnSamplingResult,
    *,
    config: ExecSessionConfig | Mapping[str, Any] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    stdout_is_terminal: bool | None = None,
    stderr_is_terminal: bool | None = None,
) -> str:
    """Render a local HTTP exec result through the normal exec processors."""

    turn_status = _local_http_result_turn_status(result)
    final_text = final_text_from_local_http_exec_result(result)
    usage = usage_from_local_http_exec_result(result)
    if isinstance(processor, JsonEventProcessor):
        processor.emit_json_lines((ThreadEvent.turn_started(),), stdout)
        _replay_local_http_session_events(processor, result, stdout=stdout)
        if _usage_is_zero(usage) and processor.last_usage is not None:
            usage = processor.last_usage
        events = []
        for reasoning_text in reasoning_texts_from_local_http_exec_result(result):
            events.append(ThreadEvent.item_completed(reasoning_item(processor.next_item_id(), reasoning_text)))
        for tool_item in tool_timeline_items_from_local_http_exec_result(result, processor, config=config):
            events.append(ThreadEvent.item_completed(tool_item))
        if final_text:
            processor.final_message = final_text
            events.append(ThreadEvent.item_completed(agent_message_item(processor.next_item_id(), final_text)))
        processor.emit_final_message_on_shutdown = turn_status == "completed"
        if turn_status == "completed":
            events.append(ThreadEvent.turn_completed(usage))
        processor.emit_json_lines(events, stdout)
        if turn_status == "interrupted":
            processor.process_server_notification(
                exec_turn_completed_notification("", "", (), status="interrupted"),
                output=stdout,
            )
        processor.print_final_output(stderr=stderr)
        return final_text

    if final_text:
        processor.final_message = final_text
    processor.final_message_rendered = False
    processor.emit_final_message_on_shutdown = turn_status == "completed"
    if config is not None:
        processor.configure_from_config(config)
    _replay_local_http_session_events(processor, result, stderr=stderr)
    for item in reasoning_turn_items_from_local_http_exec_result(result):
        processor.collect_item_completed(item, stderr=stderr)
    for item in tool_timeline_items_from_local_http_exec_result(result, JsonEventProcessor(), config=config):
        status = str(item.payload.get("status") or "").lower() if isinstance(item.payload, Mapping) else ""
        rendered_item = item.to_mapping()
        if item.type == "command_execution" and status == "in_progress":
            processor.process_server_notification(
                {"method": "item/started", "params": {"item": rendered_item}},
                stderr=stderr,
            )
        else:
            processor.process_server_notification(
                {"method": "item/completed", "params": {"item": rendered_item}},
                stderr=stderr,
            )
    if _usage_is_zero(usage) and processor.last_usage is not None:
        usage = processor.last_usage
    processor.last_usage = usage
    if turn_status == "interrupted":
        processor.process_server_notification(
            exec_turn_completed_notification("", "", (), status="interrupted"),
            stderr=stderr,
        )
    else:
        processor.print_final_output(
            stdout=stdout,
            stderr=stderr,
            stdout_is_terminal=stdout_is_terminal,
            stderr_is_terminal=stderr_is_terminal,
        )
    return final_text


def _local_http_result_turn_status(result: UserTurnSamplingResult) -> str:
    status = getattr(result, "turn_status", "completed")
    normalized = str(getattr(status, "value", status)).lower()
    return "interrupted" if normalized == "interrupted" else "completed"


def tool_call_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
) -> tuple[ExecThreadItem, ...]:
    """Extract read-only tool/function call items from a local HTTP Responses payload."""

    items: list[ExecThreadItem] = []
    seen_call_ids: set[str] = set()
    for payload in _raw_responses_payloads(result):
        for item in _response_output_mappings(payload):
            item_type = str(item.get("type") or "")
            if item_type not in {"function_call", "custom_tool_call", "mcp_tool_call"}:
                continue
            call_id = str(item.get("call_id") or item.get("id") or "")
            if call_id:
                seen_call_ids.add(call_id)
            items.append(_tool_call_exec_thread_item(item, processor))
    for item in _response_item_tool_call_mappings(result):
        call_id = str(item.get("call_id") or item.get("id") or "")
        if call_id and call_id in seen_call_ids:
            continue
        if call_id:
            seen_call_ids.add(call_id)
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
    raw_tool_output_items = tuple(getattr(result, "raw_tool_output_items", ()) or ())
    if raw_tool_output_items:
        output_items.extend(item for item in raw_tool_output_items if isinstance(item, Mapping))
    else:
        for response_item in getattr(result, "tool_response_items", ()) or ():
            mapping = _response_item_mapping(response_item)
            if mapping is not None:
                output_items.append(mapping)
    if not output_items:
        output_items.extend(_response_item_tool_output_mappings(result))
    for item in output_items:
        items.append(_tool_output_exec_thread_item(item, processor))
    return tuple(items)


def _merge_granted_permissions_from_tool_outputs(
    current: AdditionalPermissionProfile | None,
    tool_outputs: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    *,
    scope: PermissionGrantScope,
) -> AdditionalPermissionProfile | None:
    granted = current
    for output in tool_outputs:
        if output.get("name") != "request_permissions" or output.get("success") is not True:
            continue
        response = _request_permissions_response_from_tool_output(output)
        if response is None or response.scope is not scope:
            continue
        granted = merge_permission_profiles(
            granted,
            response.permissions.to_additional_permission_profile(),
        )
    return normalize_additional_permissions(granted) if granted is not None else None


def _request_permissions_response_from_tool_output(output: Mapping[str, Any]) -> RequestPermissionsResponse | None:
    internal_output = output.get("internal_output")
    if isinstance(internal_output, Mapping):
        response = internal_output.get("response")
        if isinstance(response, RequestPermissionsResponse):
            return response
    response_output = output.get("output")
    if isinstance(response_output, FunctionCallOutputPayload):
        response_output = response_output.body
    if not isinstance(response_output, str):
        return None
    try:
        parsed = json.loads(response_output)
        return RequestPermissionsResponse.from_mapping(parsed)
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def tool_timeline_items_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    processor: JsonEventProcessor,
    *,
    config: ExecSessionConfig | Mapping[str, Any] | None = None,
) -> tuple[ExecThreadItem, ...]:
    """Extract tool call/output items in user-turn order."""

    calls: list[Mapping[str, Any]] = []
    output_items: list[Mapping[str, Any]] = []
    for payload in _raw_responses_payloads(result):
        for item in _response_output_mappings(payload):
            item_type = str(item.get("type") or "")
            if item_type in {"function_call", "custom_tool_call", "mcp_tool_call", "local_shell_call"}:
                calls.append(item)
            elif item_type in {"function_call_output", "custom_tool_call_output", "mcp_tool_call_output"}:
                output_items.append(item)
    seen_call_ids = {str(item.get("call_id") or item.get("id") or "") for item in calls}
    for item in _response_item_tool_call_mappings(result, include_local_shell=True):
        call_id = str(item.get("call_id") or item.get("id") or "")
        if call_id and call_id in seen_call_ids:
            continue
        if call_id:
            seen_call_ids.add(call_id)
        calls.append(item)
    raw_tool_output_items = tuple(getattr(result, "raw_tool_output_items", ()) or ())
    if raw_tool_output_items:
        output_items.extend(item for item in raw_tool_output_items if isinstance(item, Mapping))
    else:
        for response_item in getattr(result, "tool_response_items", ()) or ():
            mapping = _response_item_mapping(response_item)
            if mapping is not None:
                output_items.append(mapping)
    if not output_items:
        output_items.extend(_response_item_tool_output_mappings(result))

    outputs_by_call_id: dict[str, list[Mapping[str, Any]]] = {}
    unkeyed_outputs: list[Mapping[str, Any]] = []
    for output in output_items:
        call_id = str(output.get("call_id") or output.get("id") or "")
        if call_id:
            outputs_by_call_id.setdefault(call_id, []).append(output)
        else:
            unkeyed_outputs.append(output)
    _insert_missing_local_shell_call_outputs(calls, outputs_by_call_id)
    timeline: list[ExecThreadItem] = []
    default_cwd = _local_http_timeline_default_cwd(config)
    for call in calls:
        call_item_type = str(call.get("type") or "")
        call_id = str(call.get("call_id") or call.get("id") or "")
        matching_outputs = outputs_by_call_id.pop(call_id, ()) if call_id else ()
        output_has_apply_patch_changes = any(_tool_output_has_apply_patch_changes(output) for output in matching_outputs)
        is_apply_patch = output_has_apply_patch_changes or (
            _tool_name_from_item(call) == "apply_patch"
            and call_item_type == "custom_tool_call"
            and not matching_outputs
            and bool(_apply_patch_protocol_changes_from_call(call))
        )
        is_local_shell_call = call_item_type == "local_shell_call"
        is_shell_tool = is_local_shell_call or (
            call_item_type == "function_call" and _local_http_tool_name_is_shell(_tool_name_from_item(call))
        )
        timeline.append(
            _apply_patch_file_change_exec_thread_item(
                call,
                None,
                processor,
                changes_output=matching_outputs[0] if is_apply_patch and matching_outputs else None,
            )
            if is_apply_patch
            else _local_shell_command_execution_exec_thread_item(call, None, processor, default_cwd=default_cwd)
            if is_local_shell_call
            else _shell_command_execution_exec_thread_item(call, None, processor, default_cwd=default_cwd)
            if is_shell_tool
            else _tool_call_exec_thread_item(call, processor)
        )
        if matching_outputs:
            timeline.extend(
                _apply_patch_file_change_exec_thread_item(call, output, processor)
                if is_apply_patch
                else _local_shell_command_execution_exec_thread_item(call, output, processor, default_cwd=default_cwd)
                if is_local_shell_call
                else _shell_command_execution_exec_thread_item(call, output, processor, default_cwd=default_cwd)
                if is_shell_tool
                else _tool_output_exec_thread_item(output, processor)
                for output in matching_outputs
            )
    for remaining in outputs_by_call_id.values():
        timeline.extend(
            _tool_output_exec_thread_item(output, processor)
            for output in remaining
            if not _drop_orphan_tool_output_from_timeline(output)
        )
    timeline.extend(_tool_output_exec_thread_item(output, processor) for output in unkeyed_outputs)
    return tuple(timeline)


def _response_item_tool_call_mappings(
    result: UserTurnSamplingResult,
    *,
    include_local_shell: bool = False,
) -> tuple[Mapping[str, Any], ...]:
    items: list[Mapping[str, Any]] = []
    tool_call_types = {"function_call", "custom_tool_call", "mcp_tool_call"}
    if include_local_shell:
        tool_call_types.add("local_shell_call")
    for response_item in getattr(result, "response_items", ()) or ():
        mapping = _response_item_mapping(response_item)
        if mapping is None:
            continue
        if str(mapping.get("type") or "") in tool_call_types:
            items.append(mapping)
    return tuple(items)


def _response_item_tool_output_mappings(result: UserTurnSamplingResult) -> tuple[Mapping[str, Any], ...]:
    items: list[Mapping[str, Any]] = []
    for response_item in getattr(result, "response_items", ()) or ():
        mapping = _response_item_mapping(response_item)
        if mapping is None:
            continue
        if str(mapping.get("type") or "") in {"function_call_output", "custom_tool_call_output", "mcp_tool_call_output"}:
            items.append(mapping)
    return tuple(items)


def _insert_missing_local_shell_call_outputs(
    calls: list[Mapping[str, Any]],
    outputs_by_call_id: dict[str, list[Mapping[str, Any]]],
) -> None:
    for call in calls:
        if str(call.get("type") or "") != "local_shell_call":
            continue
        call_id = str(call.get("call_id") or call.get("id") or "")
        if not call_id or outputs_by_call_id.get(call_id):
            continue
        outputs_by_call_id[call_id] = [
            {
                "type": "function_call_output",
                "call_id": call_id,
                "output": "aborted",
            }
        ]


def _drop_orphan_tool_output_from_timeline(item: Mapping[str, Any]) -> bool:
    item_type = str(item.get("type") or "")
    call_id = str(item.get("call_id") or item.get("id") or "")
    tool_name = str(item.get("name") or item.get("tool") or "")
    return bool(call_id) and not tool_name and item_type in {"function_call_output", "custom_tool_call_output"}


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


def _local_http_tool_name_is_shell(tool_name: str) -> bool:
    return tool_name in {"exec_command", "shell_command", "shell", "local_shell", "exec"}


def _local_http_timeline_default_cwd(config: ExecSessionConfig | Mapping[str, Any] | None) -> Path | None:
    if config is None:
        return None
    if isinstance(config, Mapping):
        value = config.get("cwd")
    else:
        value = getattr(config, "cwd", None)
    return value if isinstance(value, Path) else Path(value) if isinstance(value, str) and value else None


def _local_shell_command_execution_exec_thread_item(
    call: Mapping[str, Any],
    output: Mapping[str, Any] | None,
    processor: JsonEventProcessor,
    *,
    default_cwd: Path | None = None,
) -> ExecThreadItem:
    call_id = str(call.get("call_id") or call.get("id") or "")
    argv = _local_shell_command_argv_from_call(call)
    cwd = _local_shell_command_cwd_from_call(call, default_cwd)
    return command_execution_item(
        call_id or processor.next_item_id(),
        command=shlex.join(argv) if argv else "",
        cwd=cwd,
        process_id=_shell_command_execution_process_id_from_tool_output(output),
        source="agent",
        command_actions=command_actions_from_argv(argv, Path(cwd) if cwd is not None else Path.cwd()) if argv else None,
        duration_ms=None if output is None else _shell_command_execution_duration_ms_from_tool_output(output),
        aggregated_output="" if output is None else _shell_command_execution_aggregated_output_from_tool_output(output),
        exit_code=None if output is None else _tool_output_exit_code_from_item(output),
        status="in_progress" if output is None else _shell_command_execution_status_from_tool_output(output),
    )


def _local_shell_command_argv_from_call(item: Mapping[str, Any]) -> tuple[str, ...]:
    action = item.get("action")
    if not isinstance(action, Mapping) or action.get("type") != "exec":
        return ()
    command = action.get("command")
    if isinstance(command, str) or not isinstance(command, (list, tuple)):
        return ()
    if not all(isinstance(part, str) for part in command):
        return ()
    return tuple(command)


def _local_shell_command_cwd_from_call(item: Mapping[str, Any], default_cwd: Path | None) -> str | Path | None:
    action = item.get("action")
    if isinstance(action, Mapping):
        working_directory = action.get("working_directory")
        if isinstance(working_directory, str) and working_directory:
            return working_directory
    return default_cwd


def _shell_command_execution_exec_thread_item(
    call: Mapping[str, Any],
    output: Mapping[str, Any] | None,
    processor: JsonEventProcessor,
    *,
    default_cwd: Path | None = None,
) -> ExecThreadItem:
    call_id = str(call.get("call_id") or call.get("id") or "")
    invocation = _shell_invocation_from_arguments(
        _tool_arguments_from_item(call),
        default_cwd=default_cwd or Path.cwd(),
        default_timeout=None,
        unified_exec=_tool_name_from_item(call) == "exec_command",
    )
    return command_execution_item(
        call_id or processor.next_item_id(),
        command=invocation.command if invocation is not None else _shell_command_execution_command_from_call(call),
        cwd=(invocation.workdir if invocation is not None else None) or default_cwd,
        process_id=_shell_command_execution_process_id_from_tool_output(output),
        source="agent",
        command_actions=_shell_command_execution_command_actions(invocation, default_cwd),
        duration_ms=None if output is None else _shell_command_execution_duration_ms_from_tool_output(output),
        aggregated_output="" if output is None else _shell_command_execution_aggregated_output_from_tool_output(output),
        exit_code=None if output is None else _tool_output_exit_code_from_item(output),
        status="in_progress" if output is None else _shell_command_execution_status_from_tool_output(output),
    )


def _shell_command_execution_command_from_call(item: Mapping[str, Any]) -> str:
    arguments = _tool_arguments_from_item(item)
    for key in ("cmd", "command"):
        value = arguments.get(key)
        if isinstance(value, str):
            return value
    return ""


def _shell_command_execution_command_actions(
    invocation: LocalHttpShellInvocation | None,
    default_cwd: Path | None,
) -> tuple[dict[str, Any], ...] | None:
    if invocation is None:
        return None
    cwd = invocation.workdir or default_cwd or Path.cwd()
    return command_actions_from_argv(_shell_command_execution_argv(invocation), cwd)


def _shell_command_execution_argv(invocation: LocalHttpShellInvocation) -> tuple[str, ...]:
    if invocation.shell:
        name = Path(invocation.shell.replace("\\", "/")).stem.lower()
        if name in {"pwsh", "powershell"}:
            return (invocation.shell, "-Command", invocation.command)
        if name == "cmd":
            return (invocation.shell, "/C", invocation.command)
        return (invocation.shell, "-lc" if invocation.login is not False else "-c", invocation.command)
    return tuple(default_user_shell().derive_exec_args(invocation.command, invocation.login is not False))


def _shell_command_execution_aggregated_output_from_tool_output(item: Mapping[str, Any]) -> str:
    for key in ("internal_output", "structured_output"):
        value = item.get(key)
        if isinstance(value, Mapping):
            output = value.get("output")
            if isinstance(output, str):
                return output
    output = _tool_output_from_item(item)
    if not isinstance(output, str):
        return ""
    return _shell_command_execution_aggregated_output_from_text(output)


def _shell_command_execution_aggregated_output_from_text(output: str) -> str:
    output_marker = "\nOutput:\n"
    if output_marker in output:
        return output.rsplit(output_marker, 1)[1]
    return _strip_process_exit_marker(output)


def _strip_process_exit_marker(output: str) -> str:
    lines = output.splitlines()
    while lines and lines[-1] == "":
        lines.pop()
    if lines and lines[-1].startswith("Process exited with code "):
        lines.pop()
    return "\n".join(lines)


def _shell_command_execution_status_from_tool_output(item: Mapping[str, Any]) -> str:
    output = _tool_output_from_item(item)
    if isinstance(output, str) and (
        "exit_code: approval_required" in output
        or "exit_code: forbidden" in output
        or "permission_request_rejected" in output
    ):
        return "declined"
    return _tool_output_status_from_item(item)


def _shell_command_execution_process_id_from_tool_output(item: Mapping[str, Any] | None) -> str | None:
    if item is None:
        return None
    for key in ("internal_output", "structured_output"):
        value = item.get(key)
        if isinstance(value, Mapping):
            process_id = value.get("process_id")
            if isinstance(process_id, str):
                return process_id
            session_id = value.get("session_id")
            if isinstance(session_id, int) and not isinstance(session_id, bool):
                return str(session_id)
    return None


def _shell_command_execution_duration_ms_from_tool_output(item: Mapping[str, Any]) -> int | None:
    for key in ("internal_output", "structured_output"):
        value = item.get(key)
        if isinstance(value, Mapping):
            duration_ms = value.get("duration_ms")
            if isinstance(duration_ms, int) and not isinstance(duration_ms, bool):
                return duration_ms
            wall_time_seconds = value.get("wall_time_seconds")
            if isinstance(wall_time_seconds, (int, float)) and not isinstance(wall_time_seconds, bool):
                return max(0, int(float(wall_time_seconds) * 1000))
    return None


def _apply_patch_file_change_exec_thread_item(
    call: Mapping[str, Any],
    output: Mapping[str, Any] | None,
    processor: JsonEventProcessor,
    *,
    changes_output: Mapping[str, Any] | None = None,
) -> ExecThreadItem:
    status = None if output is None else _patch_apply_status_from_tool_output(output)
    changes = (
        _apply_patch_protocol_changes_from_tool_output(changes_output or output)
        if (changes_output is not None or output is not None)
        else None
    )
    return file_change_item(
        processor.next_item_id(),
        FileChangeItem(
            id=str(call.get("call_id") or call.get("id") or ""),
            changes=changes or _apply_patch_protocol_changes_from_call(call),
            status=status,
            auto_approved=(
                _apply_patch_auto_approved_from_tool_output(changes_output)
                if output is None
                else None
            ),
            stdout=_apply_patch_stdout_from_tool_output(output),
            stderr=_apply_patch_stderr_from_tool_output(output),
        ),
    )


def _tool_output_has_apply_patch_changes(item: Mapping[str, Any]) -> bool:
    return _apply_patch_protocol_changes_from_tool_output(item) is not None


def _apply_patch_auto_approved_from_tool_output(item: Mapping[str, Any] | None) -> bool | None:
    metadata = _apply_patch_internal_output_mapping(item)
    if metadata is None:
        return None
    value = metadata.get("auto_approved")
    return value if isinstance(value, bool) else None


def _apply_patch_stdout_from_tool_output(item: Mapping[str, Any] | None) -> str | None:
    metadata = _apply_patch_internal_output_mapping(item)
    if metadata is None:
        return None
    value = metadata.get("stdout")
    return value if isinstance(value, str) else None


def _apply_patch_stderr_from_tool_output(item: Mapping[str, Any] | None) -> str | None:
    metadata = _apply_patch_internal_output_mapping(item)
    if metadata is None:
        return None
    value = metadata.get("stderr")
    return value if isinstance(value, str) else None


def _patch_apply_status_from_tool_output(item: Mapping[str, Any]) -> PatchApplyStatus:
    output = _tool_output_from_item(item)
    if isinstance(output, str) and "approval_required" in output:
        return PatchApplyStatus.DECLINED
    return PatchApplyStatus.FAILED if _tool_output_status_from_item(item) == "failed" else PatchApplyStatus.COMPLETED


def _apply_patch_protocol_changes_from_call(item: Mapping[str, Any]) -> dict[Path, FileChange]:
    patch_text = _apply_patch_text_from_arguments(_tool_arguments_from_item(item))
    if patch_text is None:
        return {}
    try:
        parsed = parse_patch(patch_text)
    except Exception:
        return {}
    changes: dict[Path, FileChange] = {}
    for hunk in parsed.hunks:
        hunk_type = getattr(hunk, "type", None)
        path = Path(getattr(hunk, "path", ""))
        if hunk_type == "add":
            changes[path] = FileChange.add(getattr(hunk, "contents", None) or "")
        elif hunk_type == "delete":
            changes[path] = FileChange.delete(getattr(hunk, "contents", None) or "")
        elif hunk_type == "update":
            changes[path] = FileChange.update("", move_path=getattr(hunk, "move_path", None))
    return changes


def _apply_patch_protocol_changes_from_tool_output(item: Mapping[str, Any] | None) -> dict[Path, FileChange] | None:
    internal_output = _apply_patch_internal_output_mapping(item)
    if internal_output is None:
        return None
    changes = internal_output.get("changes")
    if not isinstance(changes, Mapping):
        return None
    protocol_changes: dict[Path, FileChange] = {}
    for path, change in changes.items():
        if not isinstance(path, (str, Path)) or not isinstance(change, FileChange):
            return None
        protocol_changes[Path(path)] = change
    return protocol_changes


def _apply_patch_internal_output_mapping(item: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if item is None:
        return None
    internal_output = item.get("internal_output")
    return internal_output if isinstance(internal_output, Mapping) else None


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
            "status": _tool_output_status_from_item(item),
        },
    )


def _tool_output_status_from_item(item: Mapping[str, Any]) -> str:
    success = item.get("success")
    if success is False:
        return "failed"
    exit_code = _tool_output_exit_code_from_item(item)
    if exit_code is not None and exit_code != 0:
        return "failed"
    return "completed"


def _tool_output_exit_code_from_item(item: Mapping[str, Any]) -> int | None:
    for key in ("structured_output", "internal_output"):
        value = item.get(key)
        if isinstance(value, Mapping):
            exit_code = value.get("exit_code")
            if isinstance(exit_code, bool):
                continue
            if isinstance(exit_code, int):
                return exit_code
    output = _tool_output_from_item(item)
    if not isinstance(output, str):
        return None
    marker = "Process exited with code "
    start = output.find(marker)
    if start < 0:
        return None
    start += len(marker)
    end = start
    while end < len(output) and (output[end].isdigit() or (end == start and output[end] == "-")):
        end += 1
    if end == start or output[start:end] == "-":
        return None
    try:
        return int(output[start:end])
    except ValueError:
        return None


def shell_tool_outputs_from_local_http_exec_result(
    result: UserTurnSamplingResult,
    config: ExecSessionConfig,
    *,
    runner: Any = None,
    session_manager: LocalHttpExecSessionManager | None = None,
    timeout: float | None = 30.0,
    output_max_chars: int | None = None,
    granted_permissions: AdditionalPermissionProfile | None = None,
    model_info: Any = None,
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
        argument_error = _local_http_function_call_argument_error(item, tool)
        if argument_error is not None:
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "name": tool,
                    "output": argument_error,
                    "success": False,
                }
            )
            continue
        if _local_http_tool_payload_incompatible(item_type, tool):
            outputs.append(_local_http_incompatible_tool_payload_output(item_type, str(call_id), tool))
            continue
        if tool == "request_permissions":
            request_permissions_callback = (
                _local_http_request_permissions_empty_callback
                if _local_http_request_permissions_auto_denied(config)
                else config.request_permissions_callback
            )
            output_text, success, response = _local_http_request_permissions_output(
                _tool_arguments_from_item(item),
                str(call_id),
                config.cwd,
                request_permissions_callback,
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "name": "request_permissions",
                    "output": output_text,
                    **({"internal_output": {"response": response}} if response is not None else {}),
                    "success": success,
                }
            )
            continue
        if tool == "view_image":
            view_image_output, success, internal_output = _local_http_view_image_tool_output(
                item,
                config,
                model_info=model_info,
            )
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "name": "view_image",
                    "output": view_image_output,
                    **({"structured_output": internal_output} if internal_output is not None else {}),
                    **({"internal_output": internal_output} if internal_output is not None else {}),
                    "success": success,
                }
            )
            continue
        if tool == "apply_patch":
            patch_text = _apply_patch_text_from_arguments(_tool_arguments_from_item(item))
            if patch_text is None:
                outputs.append(
                    {
                        "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                        "call_id": str(call_id),
                        "output": "apply_patch handler received non-apply_patch input",
                        "success": False,
                    }
                )
                continue
            changes = _local_http_apply_patch_protocol_changes(patch_text, config.cwd)
            patch_auto_approved = local_http_shell_tool_auto_execute_allowed(config)
            if not patch_auto_approved and not _local_http_apply_patch_preapproved(
                changes,
                config.cwd,
                granted_permissions,
            ):
                outputs.append(
                    {
                        "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                        "call_id": str(call_id),
                        "output": (approval_output := local_http_apply_patch_approval_required_output(config)),
                        "internal_output": (
                            {
                                "changes": changes,
                                "auto_approved": False,
                                "stdout": "",
                                "stderr": approval_output,
                            }
                            if changes is not None
                            else None
                        ),
                        "success": False,
                    }
                )
                continue
            output_text, success, changes = _apply_local_http_apply_patch(patch_text, config.cwd)
            outputs.append(
                {
                    "type": "custom_tool_call_output" if item_type == "custom_tool_call" else "function_call_output",
                    "call_id": str(call_id),
                    "output": output_text,
                    "internal_output": (
                        {
                            "changes": changes,
                            "auto_approved": patch_auto_approved,
                            "stdout": output_text if success else "",
                            "stderr": "" if success else output_text,
                        }
                        if changes is not None
                        else None
                    ),
                    "success": success,
                }
            )
            continue
        if tool == "write_stdin":
            stdin_arguments = _tool_arguments_from_item(item)
            stdin_argument_error = _local_http_write_stdin_argument_error(stdin_arguments)
            if stdin_argument_error is not None:
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "name": "write_stdin",
                        "output": stdin_argument_error,
                        "success": False,
                    }
                )
                continue
            stdin_invocation = _write_stdin_invocation_from_arguments(stdin_arguments)
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
            outputs.append(_local_http_unsupported_tool_call_output(item_type, str(call_id), tool))
            continue
        invocation = _shell_invocation_from_arguments(
            _tool_arguments_from_item(item),
            default_cwd=config.cwd,
            default_timeout=timeout,
            unified_exec=tool == "exec_command",
        )
        if invocation is None:
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "name": tool,
                    "output": "failed to parse function arguments: missing required command",
                    "success": False,
                }
            )
            continue
        login_error = local_http_shell_tool_login_error(invocation, config)
        if login_error is not None:
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": login_error,
                    "success": False,
                }
            )
            continue
        invocation = local_http_shell_invocation_with_config_login(invocation, config)
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
        auto_execute_allowed = local_http_shell_tool_auto_execute_allowed(config)
        permission_cwd = invocation.workdir or config.cwd
        preapproved_permissions = _local_http_shell_tool_preapproved(
            invocation,
            granted_permissions=granted_permissions,
            cwd=permission_cwd,
        )
        additional_permissions_allowed = local_http_shell_tool_additional_permissions_allowed(
            config,
            permissions_preapproved=preapproved_permissions,
        )
        permission_error = local_http_shell_tool_permission_request_error(
            invocation,
            granted_permissions=granted_permissions,
            cwd=permission_cwd,
            additional_permissions_allowed=additional_permissions_allowed,
            allow_pending_approval=not auto_execute_allowed and not preapproved_permissions,
        )
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
        approval_requirement = _local_http_shell_tool_exec_approval_requirement(
            invocation,
            config,
            permissions_preapproved=preapproved_permissions,
        )
        if approval_requirement.type == "forbidden" and _local_http_shell_tool_forbidden_applies(invocation):
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": local_http_shell_tool_forbidden_output(
                        invocation,
                        config,
                        approval_requirement.reason or "command rejected by policy",
                    ),
                    "success": False,
                }
            )
            continue
        pending_permission_approval = _local_http_shell_tool_pending_permission_approval(
            invocation,
            config,
            permissions_preapproved=preapproved_permissions,
        )
        if (
            approval_requirement.type == "needs_approval" or pending_permission_approval
        ) and not preapproved_permissions:
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": local_http_shell_tool_approval_required_output(
                        invocation,
                        config,
                        granted_permissions=granted_permissions,
                        exec_approval_requirement=approval_requirement,
                    ),
                    "success": False,
                }
            )
            continue
        apply_patch_command = _local_http_apply_patch_command_from_shell_invocation(
            invocation,
            cwd=invocation.workdir or config.cwd,
        )
        if apply_patch_command is not None:
            if apply_patch_command.error is not None:
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "output": apply_patch_command.error,
                        "success": False,
                    }
                )
                continue
            changes = apply_patch_command.changes
            patch_auto_approved = auto_execute_allowed
            if not patch_auto_approved and not _local_http_apply_patch_preapproved(
                changes,
                invocation.workdir or config.cwd,
                granted_permissions,
            ):
                outputs.append(
                    {
                        "type": "function_call_output",
                        "call_id": str(call_id),
                        "output": (approval_output := local_http_apply_patch_approval_required_output(config)),
                        "internal_output": (
                            {
                                "changes": changes,
                                "auto_approved": False,
                                "stdout": "",
                                "stderr": approval_output,
                            }
                            if changes is not None
                            else None
                        ),
                        "success": False,
                    }
                )
                continue
            try:
                if apply_patch_command.action is None:
                    raise ValueError("missing apply_patch action")
                output_text = apply_patch_action_to_disk(apply_patch_command.action)
                success = True
            except Exception as exc:
                output_text = f"apply_patch failed: {exc}"
                success = False
            outputs.append(
                {
                    "type": "function_call_output",
                    "call_id": str(call_id),
                    "output": output_text,
                    "internal_output": (
                        {
                            "changes": changes,
                            "auto_approved": patch_auto_approved,
                            "stdout": output_text if success else "",
                            "stderr": "" if success else output_text,
                        }
                        if changes is not None
                        else None
                    ),
                    "success": success,
                }
            )
            continue
        effective_output_budget = _effective_shell_output_budget(output_max_chars, invocation.max_output_tokens)
        effective_output_max_chars = _output_budget_max_bytes(effective_output_budget)
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
                output_max_chars=effective_output_budget,
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


def _local_http_unsupported_tool_call_output(item_type: str, call_id: str, tool: str) -> dict[str, Any]:
    custom = item_type == "custom_tool_call"
    return {
        "type": "custom_tool_call_output" if custom else "function_call_output",
        "call_id": call_id,
        **({} if custom else {"name": tool}),
        "output": (
            f"unsupported custom tool call: {tool}"
            if custom
            else f"unsupported call: {tool}"
        ),
        "success": False,
    }


def _local_http_tool_payload_incompatible(item_type: str, tool: str) -> bool:
    if item_type == "custom_tool_call" and tool in {
        "exec_command",
        "shell_command",
        "shell",
        "local_shell",
        "exec",
        "write_stdin",
        "request_permissions",
        "view_image",
    }:
        return True
    if item_type == "function_call" and tool == "apply_patch":
        return True
    return False


def _local_http_incompatible_tool_payload_output(item_type: str, call_id: str, tool: str) -> dict[str, Any]:
    custom = item_type == "custom_tool_call"
    return {
        "type": "custom_tool_call_output" if custom else "function_call_output",
        "call_id": call_id,
        **({} if custom else {"name": tool}),
        "output": f"tool {tool} invoked with incompatible payload",
        "success": False,
    }


def local_http_shell_tool_login_error(
    invocation: LocalHttpShellInvocation,
    config: ExecSessionConfig,
) -> str | None:
    """Return Rust's model-facing error for disallowed explicit login shells."""

    if invocation.login is True and not config.allow_login_shell:
        return "login shell is disabled by config; omit `login` or set it to false."
    return None


def local_http_shell_invocation_with_config_login(
    invocation: LocalHttpShellInvocation,
    config: ExecSessionConfig,
) -> LocalHttpShellInvocation:
    """Resolve omitted login flag using Rust's allow_login_shell default."""

    if invocation.login is not None:
        return invocation
    return replace(invocation, login=config.allow_login_shell)


def _local_http_view_image_tool_output(
    item: Mapping[str, Any],
    config: ExecSessionConfig,
    *,
    model_info: Any = None,
) -> tuple[Any, bool, dict[str, Any] | None]:
    arguments = _tool_arguments_json_from_item(item)
    handler = ViewImageHandler(
        ViewImageToolOptions(
            can_request_original_image_detail=local_http_model_can_request_original_image_detail(model_info),
        ),
        supports_image_inputs=local_http_model_supports_image_inputs(model_info),
        cwd=config.cwd,
    )
    try:
        output = handler.handle(ToolPayload.function(arguments))
    except FunctionCallError as exc:
        return str(exc), False, None
    content_item = {
        "type": "input_image",
        "image_url": output.image_url,
        "detail": output.image_detail.value,
    }
    return (
        (content_item,),
        True,
        {
            "image_url": output.image_url,
            "detail": output.image_detail.value,
        },
    )


def local_http_apply_patch_approval_required_output(config: ExecSessionConfig) -> str:
    approval = approval_policy_display_value(config.approval_policy)
    return (
        "apply_patch: approval_required\n"
        f"approval_policy: {approval}\n"
        "stderr:\nPatch application requires approval and was not run by the local HTTP helper."
    )


def local_http_write_stdin_approval_required_output(config: ExecSessionConfig) -> str:
    approval = approval_policy_display_value(config.approval_policy)
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
    return "request_permissions was cancelled before receiving a response"


def _local_http_request_permissions_output(
    arguments: Any,
    call_id: str,
    cwd: Path,
    request_permissions_callback: Any = None,
) -> tuple[str, bool, RequestPermissionsResponse | None]:
    try:
        output = RequestPermissionsHandler(
            _local_http_request_permissions_callback(request_permissions_callback, cwd)
        ).handle(
            ToolPayload.function(_request_permissions_arguments_text(arguments)),
            call_id=call_id,
            cwd=cwd,
        )
    except FunctionCallError as exc:
        return str(exc), False, None
    if inspect.isawaitable(output):
        return local_http_request_permissions_unavailable_output(), False, None
    into_text = getattr(output, "into_text", None)
    output_text = into_text() if callable(into_text) else str(output)
    try:
        response = RequestPermissionsResponse.from_mapping(json.loads(output_text))
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        response = None
    return output_text, True, response


def _local_http_request_permissions_auto_denied(config: ExecSessionConfig) -> bool:
    approval_policy = config.approval_policy
    if approval_policy is AskForApproval.NEVER or approval_policy == AskForApproval.NEVER:
        return True
    allows_request_permissions = getattr(approval_policy, "allows_request_permissions", None)
    return callable(allows_request_permissions) and not allows_request_permissions()


def _local_http_request_permissions_empty_callback(
    _parent_ctx: Any,
    _call_id: str,
    _args: Any,
    _cwd: Path,
    _cancel_token: Any,
) -> RequestPermissionsResponse:
    return RequestPermissionsResponse(RequestPermissionProfile())


def _request_permissions_arguments_text(arguments: Any) -> str:
    if isinstance(arguments, str):
        return arguments
    return json.dumps(arguments, separators=(",", ":"))


def _local_http_request_permissions_callback(callback: Any, cwd: Path) -> Any:
    if callback is None:
        return None

    def call(call_id: str, args: Any) -> Any:
        return callback(None, call_id, args, cwd, None)

    return call


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


def _local_http_write_stdin_argument_error(arguments: Any) -> str | None:
    if not isinstance(arguments, Mapping):
        return "failed to parse function arguments: expected JSON object"
    if "session_id" not in arguments:
        return "failed to parse function arguments: missing field `session_id`"
    session_id = arguments.get("session_id")
    if isinstance(session_id, bool) or not isinstance(session_id, int):
        return "failed to parse function arguments: invalid type for `session_id`, expected i32"
    if session_id < -(2**31) or session_id > 2**31 - 1:
        return "failed to parse function arguments: invalid value for `session_id`, expected i32"
    chars = arguments.get("chars")
    if chars is not None and not isinstance(chars, str):
        return "failed to parse function arguments: invalid type for `chars`, expected string"
    yield_time_ms = arguments.get("yield_time_ms")
    if yield_time_ms is not None and (
        isinstance(yield_time_ms, bool) or not isinstance(yield_time_ms, int) or yield_time_ms < 0
    ):
        return "failed to parse function arguments: invalid type for `yield_time_ms`, expected u64"
    max_output_tokens = arguments.get("max_output_tokens")
    if max_output_tokens is not None and (
        isinstance(max_output_tokens, bool) or not isinstance(max_output_tokens, int) or max_output_tokens < 0
    ):
        return "failed to parse function arguments: invalid type for `max_output_tokens`, expected usize"
    return None


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
    output_max_chars: LocalHttpOutputBudget | int | None,
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


def _apply_local_http_apply_patch(patch_text: str, cwd: Path) -> tuple[str, bool, dict[Path, FileChange] | None]:
    try:
        verified = verify_apply_patch_args(parse_patch(patch_text), cwd)
    except Exception as exc:
        return f"apply_patch verification failed: {exc}", False, None
    if verified.type != "body" or verified.body is None:
        return f"apply_patch verification failed: {verified.error}", False, None
    changes = _relative_apply_patch_protocol_changes(
        convert_apply_patch_to_protocol(verified.body),
        cwd,
    )
    try:
        return apply_patch_action_to_disk(verified.body), True, changes
    except OSError as exc:
        return f"apply_patch failed: {exc}", False, changes


def _local_http_apply_patch_command_from_shell_invocation(
    invocation: LocalHttpShellInvocation,
    *,
    cwd: Path,
) -> LocalHttpApplyPatchCommand | None:
    for argv in _local_http_apply_patch_argv_candidates(invocation):
        try:
            verified = maybe_parse_apply_patch_verified(argv, cwd)
        except Exception as exc:
            return LocalHttpApplyPatchCommand(error=f"apply_patch verification failed: {exc}")
        if verified.type in {"not_apply_patch", "shell_parse_error"}:
            continue
        if verified.type == "correctness_error":
            return LocalHttpApplyPatchCommand(error=f"apply_patch verification failed: {verified.error}")
        if verified.type == "body":
            if verified.body is None:
                return LocalHttpApplyPatchCommand(error="apply_patch verification failed: missing patch body")
            changes = _relative_apply_patch_protocol_changes(
                convert_apply_patch_to_protocol(verified.body),
                cwd,
            )
            return LocalHttpApplyPatchCommand(action=verified.body, changes=changes)
    return None


def _local_http_apply_patch_argv_candidates(invocation: LocalHttpShellInvocation) -> tuple[tuple[str, ...], ...]:
    command = invocation.command
    shell = invocation.shell
    candidates: list[tuple[str, ...]] = []
    if shell:
        name = Path(shell.replace("\\", "/")).stem.lower()
        if name in {"pwsh", "powershell"}:
            candidates.append((shell, "-Command", command))
            candidates.append((shell, "-NoProfile", "-Command", command))
        elif name == "cmd":
            candidates.append((shell, "/C", command))
        else:
            candidates.append((shell, "-lc" if invocation.login is not False else "-c", command))
    else:
        flag = "-lc" if invocation.login is not False else "-c"
        candidates.extend(
            (
                ("bash", flag, command),
                ("sh", "-c", command),
                ("pwsh", "-Command", command),
                ("cmd", "/C", command),
            )
        )
    candidates.append((command,))
    return tuple(dict.fromkeys(candidates))


def _local_http_apply_patch_protocol_changes(patch_text: str, cwd: Path) -> dict[Path, FileChange] | None:
    try:
        verified = verify_apply_patch_args(parse_patch(patch_text), cwd)
    except Exception:
        return None
    if verified.type != "body" or verified.body is None:
        return None
    return _relative_apply_patch_protocol_changes(
        convert_apply_patch_to_protocol(verified.body),
        cwd,
    )


def _local_http_apply_patch_preapproved(
    changes: Mapping[Path, FileChange] | None,
    cwd: Path,
    granted_permissions: AdditionalPermissionProfile | None,
) -> bool:
    if not changes or granted_permissions is None:
        return False
    granted = normalize_additional_permissions(granted_permissions)
    file_system = granted.file_system
    if file_system is None:
        return False
    policy = FileSystemSandboxPolicy.restricted(file_system.entries)
    return all(
        policy.resolve_access_with_cwd(path, cwd) is FileSystemAccessMode.WRITE
        for path in _local_http_apply_patch_write_targets(changes, cwd)
    )


def _local_http_apply_patch_write_targets(
    changes: Mapping[Path, FileChange],
    cwd: Path,
) -> tuple[Path, ...]:
    targets: list[Path] = []
    for path, change in changes.items():
        targets.append(_resolve_local_http_apply_patch_target(path, cwd))
        move_path = getattr(change, "move_path", None)
        if move_path is not None:
            targets.append(_resolve_local_http_apply_patch_target(move_path, cwd))
    return tuple(dict.fromkeys(targets))


def _resolve_local_http_apply_patch_target(path: Path | str, cwd: Path) -> Path:
    path = Path(path)
    return path if path.is_absolute() else Path(cwd) / path


def _relative_apply_patch_protocol_changes(
    changes: Mapping[Path, FileChange],
    cwd: Path,
) -> dict[Path, FileChange]:
    cwd = Path(cwd)
    return {
        _path_relative_to(path, cwd): _file_change_relative_to(change, cwd)
        for path, change in changes.items()
    }


def _file_change_relative_to(change: FileChange, cwd: Path) -> FileChange:
    if change.type != "update" or change.move_path is None:
        return change
    return FileChange.update(change.unified_diff or "", move_path=_path_relative_to(change.move_path, cwd))


def _path_relative_to(path: str | Path, cwd: Path) -> Path:
    path = Path(path)
    try:
        return path.relative_to(cwd)
    except ValueError:
        return path


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


def local_http_shell_tool_permission_request_error(
    invocation: LocalHttpShellInvocation,
    *,
    granted_permissions: AdditionalPermissionProfile | None = None,
    cwd: Path | str | None = None,
    additional_permissions_allowed: bool = True,
    allow_pending_approval: bool = False,
) -> str | None:
    """Return a Rust-style model-facing error for unsupported local permission requests."""

    if not isinstance(additional_permissions_allowed, bool):
        raise TypeError("additional_permissions_allowed must be a bool")
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
            requested_profile = normalize_additional_permissions(profile)
            if requested_profile.is_empty():
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
        if granted_permissions is not None and permissions_are_preapproved(
            requested_profile,
            granted_permissions,
            Path.cwd() if cwd is None else cwd,
        ):
            if additional_permissions_allowed:
                return None
            return (
                "exit_code: permission_request_unsupported\n"
                "stderr:\n"
                "additional permissions are disabled; enable `features.exec_permission_approvals` before using `with_additional_permissions`"
            )
        if not additional_permissions_allowed:
            return (
                "exit_code: permission_request_unsupported\n"
                "stderr:\n"
                "additional permissions are disabled; enable `features.exec_permission_approvals` before using `with_additional_permissions`"
            )
        if allow_pending_approval:
            return None
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
        if allow_pending_approval:
            return None
        return (
            "exit_code: permission_request_rejected\n"
            "stderr:\n"
            "approval policy is never; reject command - you cannot ask for escalated permissions if the approval policy is never"
        )
    return None


def local_http_shell_tool_additional_permissions_allowed(
    config: ExecSessionConfig,
    *,
    permissions_preapproved: bool,
) -> bool:
    """Return Rust's feature gate for shell additional permissions."""

    if not isinstance(permissions_preapproved, bool):
        raise TypeError("permissions_preapproved must be a bool")
    return bool(config.exec_permission_approvals_enabled) or (
        bool(config.request_permissions_tool_enabled) and permissions_preapproved
    )


def _local_http_shell_tool_preapproved(
    invocation: LocalHttpShellInvocation,
    *,
    granted_permissions: AdditionalPermissionProfile | None,
    cwd: Path | str,
) -> bool:
    if granted_permissions is None or invocation.additional_permissions is None:
        return False
    if invocation.additional_permissions_is_invalid or invocation.sandbox_permissions != "with_additional_permissions":
        return False
    try:
        profile = normalize_additional_permissions(
            AdditionalPermissionProfile.from_mapping(dict(invocation.additional_permissions))
        )
    except (KeyError, TypeError, ValueError):
        return False
    if profile.is_empty():
        return False
    return permissions_are_preapproved(profile, granted_permissions, cwd)


def local_http_shell_tool_approval_required_output(
    invocation: LocalHttpShellInvocation | str,
    config: ExecSessionConfig,
    *,
    granted_permissions: AdditionalPermissionProfile | None = None,
    exec_approval_requirement: ExecApprovalRequirement | None = None,
) -> str:
    """Build a tool output explaining that approval is required."""

    approval = approval_policy_display_value(config.approval_policy)
    if isinstance(invocation, LocalHttpShellInvocation):
        command = invocation.command
        sandbox_permissions = invocation.sandbox_permissions
        additional_permissions = invocation.additional_permissions
        permission_cwd = invocation.workdir or config.cwd
        justification = invocation.justification
        prefix_rule = invocation.prefix_rule
    else:
        command = invocation
        sandbox_permissions = None
        additional_permissions = None
        permission_cwd = config.cwd
        justification = None
        prefix_rule = None
    metadata = ""
    if sandbox_permissions:
        metadata += f"sandbox_permissions: {sandbox_permissions}\n"
    if additional_permissions:
        additional_permissions_mapping = _local_http_additional_permissions_output_mapping(
            additional_permissions,
            cwd=permission_cwd,
            granted_permissions=granted_permissions,
        )
        metadata += (
            "additional_permissions: "
            f"{json.dumps(additional_permissions_mapping, ensure_ascii=False, separators=(',', ':'))}\n"
        )
    if exec_approval_requirement is not None and exec_approval_requirement.reason:
        metadata += f"reason: {exec_approval_requirement.reason}\n"
    if justification:
        metadata += f"justification: {justification}\n"
    if prefix_rule:
        metadata += f"prefix_rule: {json.dumps(list(prefix_rule), ensure_ascii=False, separators=(',', ':'))}\n"
    proposed_amendment = _local_http_shell_tool_proposed_execpolicy_amendment(
        invocation,
        config,
        exec_approval_requirement=exec_approval_requirement,
    )
    if proposed_amendment is not None:
        metadata += (
            "proposed_execpolicy_amendment: "
            f"{json.dumps(proposed_amendment.to_mapping(), ensure_ascii=False, separators=(',', ':'))}\n"
        )
    return (
        "exit_code: approval_required\n"
        f"approval_policy: {approval}\n"
        f"{metadata}"
        f"command:\n{command}\n"
        "stderr:\nCommand execution requires approval and was not run by the local HTTP helper."
    )


def _local_http_shell_tool_pending_permission_approval(
    invocation: LocalHttpShellInvocation,
    config: ExecSessionConfig,
    *,
    permissions_preapproved: bool,
) -> bool:
    if permissions_preapproved:
        return False
    if invocation.sandbox_permissions not in {"require_escalated", "with_additional_permissions"}:
        return False
    return config.approval_policy is AskForApproval.ON_REQUEST or config.approval_policy == AskForApproval.ON_REQUEST


def _local_http_shell_tool_forbidden_applies(invocation: LocalHttpShellInvocation) -> bool:
    parsed = commands_for_exec_policy(_local_http_shell_tool_exec_policy_command(invocation))
    for command in parsed.commands:
        if parsed.command_origin is ExecPolicyCommandOrigin.POWERSHELL:
            if is_dangerous_powershell_words(command):
                return True
        elif command_might_be_dangerous(command):
            return True
    return False


def local_http_shell_tool_forbidden_output(
    invocation: LocalHttpShellInvocation | str,
    config: ExecSessionConfig,
    reason: str,
) -> str:
    approval = approval_policy_display_value(config.approval_policy)
    command = invocation.command if isinstance(invocation, LocalHttpShellInvocation) else invocation
    return (
        "exit_code: forbidden\n"
        f"approval_policy: {approval}\n"
        f"command:\n{command}\n"
        f"stderr:\n{reason}"
    )


def _local_http_shell_tool_exec_approval_requirement(
    invocation: LocalHttpShellInvocation,
    config: ExecSessionConfig,
    *,
    permissions_preapproved: bool = False,
) -> ExecApprovalRequirement:
    sandbox_permissions = SandboxPermissions.USE_DEFAULT
    if not permissions_preapproved and invocation.sandbox_permissions:
        sandbox_permissions = SandboxPermissions(invocation.sandbox_permissions)
    return create_exec_approval_requirement_for_command(
        ExecApprovalRequest(
            command=_local_http_shell_tool_exec_policy_command(invocation),
            approval_policy=config.approval_policy,
            permission_profile=config.permission_profile,
            file_system_sandbox_policy=config.permission_profile.file_system_sandbox_policy(),
            sandbox_cwd=invocation.workdir or config.cwd,
            sandbox_permissions=sandbox_permissions,
            prefix_rule=invocation.prefix_rule,
            matched_rules=match_exec_policy_rules_for_command(
                _local_http_shell_tool_exec_policy_command(invocation),
                getattr(config, "exec_policy_rules", ()),
            ),
        )
    )


def _local_http_shell_tool_proposed_execpolicy_amendment(
    invocation: LocalHttpShellInvocation | str,
    config: ExecSessionConfig,
    *,
    exec_approval_requirement: ExecApprovalRequirement | None = None,
):
    if not isinstance(invocation, LocalHttpShellInvocation):
        return None
    if _local_http_shell_command_uses_heredoc_or_herestring(invocation.command):
        return None
    requirement = exec_approval_requirement
    if requirement is None:
        requirement = _local_http_shell_tool_exec_approval_requirement(invocation, config)
    return requirement.proposed_amendment()


def _local_http_shell_command_uses_heredoc_or_herestring(command: str) -> bool:
    if not isinstance(command, str):
        return False
    return "<<" in command


def _local_http_shell_tool_exec_policy_command(invocation: LocalHttpShellInvocation) -> tuple[str, ...]:
    return _shell_command_execution_argv(invocation)


def _local_http_additional_permissions_output_mapping(
    additional_permissions: Mapping[str, Any],
    *,
    cwd: Path | str | None = None,
    granted_permissions: AdditionalPermissionProfile | None = None,
) -> Mapping[str, Any]:
    """Return a normalized Rust-style additional permission profile mapping when possible."""

    try:
        profile = AdditionalPermissionProfile.from_mapping(dict(additional_permissions))
        if cwd is not None:
            profile = _materialize_local_http_additional_permissions(profile, Path(cwd))
        profile = merge_permission_profiles(granted_permissions, profile) or AdditionalPermissionProfile()
        return normalize_additional_permissions(profile).to_mapping()
    except (KeyError, TypeError, ValueError):
        return dict(additional_permissions)


def _materialize_local_http_additional_permissions(
    profile: AdditionalPermissionProfile,
    cwd: Path,
) -> AdditionalPermissionProfile:
    file_system = profile.file_system
    if file_system is None:
        return profile
    entries = tuple(_materialize_local_http_permission_entry(entry, cwd) for entry in file_system.entries)
    return AdditionalPermissionProfile(
        network=profile.network,
        file_system=FileSystemPermissions(
            entries=entries,
            glob_scan_max_depth=file_system.glob_scan_max_depth,
        ),
    )


def _materialize_local_http_permission_entry(
    entry: FileSystemSandboxEntry,
    cwd: Path,
) -> FileSystemSandboxEntry:
    if entry.path.type != "path" or entry.path.path is None or entry.path.path.is_absolute():
        return entry
    return FileSystemSandboxEntry(FileSystemPath.explicit_path(cwd / entry.path.path), entry.access)


def _shell_invocation_from_arguments(
    arguments: Any,
    *,
    default_cwd: Path,
    default_timeout: float | None,
    unified_exec: bool = False,
) -> LocalHttpShellInvocation | None:
    command = _shell_command_from_arguments(arguments, unified_exec=unified_exec)
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
        workdir=_shell_workdir_from_arguments(arguments, default_cwd=default_cwd, unified_exec=unified_exec),
        timeout=_shell_timeout_from_arguments(arguments, default_timeout=default_timeout, unified_exec=unified_exec),
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


def _local_http_exec_command_argument_error(arguments: Mapping[str, Any]) -> str | None:
    if "cmd" not in arguments:
        return "failed to parse function arguments: missing field `cmd`"
    cmd = arguments.get("cmd")
    if not isinstance(cmd, str):
        return "failed to parse function arguments: invalid type for `cmd`, expected string"
    for key in ("workdir", "shell", "justification"):
        value = arguments.get(key)
        if value is not None and not isinstance(value, str):
            return f"failed to parse function arguments: invalid type for `{key}`, expected string"
    for key in ("login", "tty"):
        value = arguments.get(key)
        if value is not None and not isinstance(value, bool):
            return f"failed to parse function arguments: invalid type for `{key}`, expected bool"
    for key, expected in (("yield_time_ms", "u64"), ("max_output_tokens", "usize")):
        value = arguments.get(key)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            return f"failed to parse function arguments: invalid type for `{key}`, expected {expected}"
    sandbox_permissions = arguments.get("sandbox_permissions")
    if sandbox_permissions is not None and not isinstance(sandbox_permissions, str):
        return "failed to parse function arguments: invalid type for `sandbox_permissions`, expected string"
    additional_permissions = arguments.get("additional_permissions")
    if additional_permissions is not None and not isinstance(additional_permissions, Mapping):
        return "failed to parse function arguments: invalid type for `additional_permissions`, expected object"
    prefix_rule = arguments.get("prefix_rule")
    if prefix_rule is not None and (
        isinstance(prefix_rule, (str, bytes))
        or not isinstance(prefix_rule, (list, tuple))
        or not all(isinstance(item, str) for item in prefix_rule)
    ):
        return "failed to parse function arguments: invalid type for `prefix_rule`, expected array of strings"
    return None


def _shell_command_from_arguments(arguments: Any, *, unified_exec: bool = False) -> str | None:
    if isinstance(arguments, str):
        return arguments if arguments else None
    if not isinstance(arguments, Mapping):
        return None
    if unified_exec:
        value = arguments.get("cmd")
        return value if isinstance(value, str) and value else None
    for key in ("command", "cmd", "script"):
        value = arguments.get(key)
        if isinstance(value, str) and value:
            return value
    argv = arguments.get("argv")
    if isinstance(argv, (list, tuple)) and all(isinstance(item, str) for item in argv):
        return subprocess.list2cmdline(list(argv))
    return None


def _shell_workdir_from_arguments(
    arguments: Mapping[str, Any],
    *,
    default_cwd: Path,
    unified_exec: bool = False,
) -> Path | None:
    value = arguments.get("workdir")
    if value is None and not unified_exec:
        value = arguments.get("cwd")
    if not isinstance(value, str) or not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else Path(default_cwd) / path


def _shell_timeout_from_arguments(
    arguments: Mapping[str, Any],
    *,
    default_timeout: float | None,
    unified_exec: bool = False,
) -> float | None:
    if unified_exec:
        return default_timeout
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
    if isinstance(value, int | float) and value >= 0:
        return int(value)
    return None


def _effective_shell_output_max_chars(global_max_chars: int | None, max_output_tokens: int | None) -> int | None:
    resolved_max_output_tokens = DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS if max_output_tokens is None else max_output_tokens
    token_max_chars = _approx_bytes_for_tokens(resolved_max_output_tokens)
    if global_max_chars is None:
        return token_max_chars
    return min(global_max_chars, token_max_chars)


def _effective_shell_output_budget(
    global_max_chars: int | None,
    max_output_tokens: int | None,
) -> LocalHttpOutputBudget | None:
    resolved_max_output_tokens = DEFAULT_LOCAL_HTTP_MAX_OUTPUT_TOKENS if max_output_tokens is None else max_output_tokens
    if global_max_chars is not None:
        return LocalHttpOutputBudget("chars", min(global_max_chars, _approx_bytes_for_tokens(resolved_max_output_tokens)))
    return LocalHttpOutputBudget("tokens", resolved_max_output_tokens)


def _output_budget_max_bytes(budget: LocalHttpOutputBudget | int | None) -> int | None:
    if isinstance(budget, LocalHttpOutputBudget):
        if budget.kind == "tokens":
            return _approx_bytes_for_tokens(budget.amount)
        return budget.amount
    return budget


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
    output_max_chars: LocalHttpOutputBudget | int | None = None,
) -> tuple[str, bool]:
    started_at = time.monotonic()
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
        duration = time.monotonic() - started_at
        timeout_ms = int((timeout or duration) * 1000)
        combined_output = (
            f"command timed out after {timeout_ms} milliseconds\n"
            f"{_combine_shell_output(exc.stdout, exc.stderr)}"
        )
        payload = _exec_session_output_payload(
            combined_output,
            wall_time_seconds=duration,
            session_id=None,
            exit_code=LOCAL_HTTP_EXEC_TIMEOUT_EXIT_CODE,
            timed_out=True,
            output_max_chars=output_max_chars,
        )
        return (
            local_http_exec_output_text(payload),
            False,
        )
    stdout = getattr(completed, "stdout", "") or ""
    stderr = getattr(completed, "stderr", "") or ""
    returncode = getattr(completed, "returncode", 0)
    duration = time.monotonic() - started_at
    payload = _exec_session_output_payload(
        _combine_shell_output(stdout, stderr),
        wall_time_seconds=duration,
        session_id=None,
        exit_code=returncode,
        output_max_chars=output_max_chars,
    )
    return (
        local_http_exec_output_text(payload),
        True,
    )


def _combine_shell_output(stdout: Any, stderr: Any) -> str:
    stdout_text = _coerce_shell_output_text(stdout)
    stderr_text = _coerce_shell_output_text(stderr)
    if stdout_text and stderr_text and not stdout_text.endswith(("\n", "\r")) and not stderr_text.startswith(("\n", "\r")):
        return f"{stdout_text}\n{stderr_text}"
    return f"{stdout_text}{stderr_text}"


def _coerce_shell_output_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value)


def _truncate_shell_tool_output(output: str, max_chars: LocalHttpOutputBudget | int | None) -> str:
    if isinstance(max_chars, LocalHttpOutputBudget):
        if max_chars.kind == "tokens":
            return _truncate_shell_tool_output_tokens(output, max_chars.amount)
        max_chars = max_chars.amount
    if max_chars is None or len(output.encode("utf-8")) <= max_chars:
        return output
    total_lines = len(output.splitlines())
    truncated = _truncate_middle_shell_tool_output(output, max_chars)
    return f"Total output lines: {total_lines}\n\n{truncated}"


def _truncate_shell_tool_output_tokens(output: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return _local_http_truncation_marker(_approx_token_count(output), unit="tokens")
    if _approx_token_count(output) <= max_tokens:
        return output
    total_lines = len(output.splitlines())
    max_bytes = _approx_bytes_for_tokens(max_tokens)
    head_budget = max_bytes // 2
    tail_budget = max_bytes - head_budget
    head, tail, omitted_chars = _split_shell_output_for_truncation(output, head_budget, tail_budget)
    omitted_bytes = max(0, len(output.encode("utf-8")) - len(head.encode("utf-8")) - len(tail.encode("utf-8")))
    omitted_tokens = _approx_token_count("x" * omitted_bytes)
    if omitted_tokens == 0 and omitted_chars > 0:
        omitted_tokens = 1
    truncated = f"{head}{_local_http_truncation_marker(omitted_tokens, unit='tokens')}{tail}"
    return f"Total output lines: {total_lines}\n\n{truncated}"


def _truncate_middle_shell_tool_output(output: str, max_bytes: int) -> str:
    if max_bytes <= 0:
        return _local_http_truncation_marker(len(output))
    head_budget = max_bytes // 2
    tail_budget = max_bytes - head_budget
    head, tail, omitted = _split_shell_output_for_truncation(output, head_budget, tail_budget)
    return f"{head}{_local_http_truncation_marker(omitted)}{tail}"


def _split_shell_output_for_truncation(output: str, head_bytes: int, tail_bytes: int) -> tuple[str, str, int]:
    encoded_len = len(output.encode("utf-8"))
    tail_start_target = max(encoded_len - tail_bytes, 0)
    prefix_end = 0
    suffix_start = len(output)
    suffix_started = False
    removed_chars = 0
    for char_index, char in _iter_shell_output_char_byte_indices(output):
        char_end = char_index + len(char.encode("utf-8"))
        if char_end <= head_bytes:
            prefix_end = char_end
            continue
        if char_index >= tail_start_target:
            if not suffix_started:
                suffix_start = char_index
                suffix_started = True
            continue
        removed_chars += 1
    if suffix_start < prefix_end:
        suffix_start = prefix_end
    encoded = output.encode("utf-8")
    head = encoded[:prefix_end].decode("utf-8", errors="ignore")
    tail = encoded[suffix_start:].decode("utf-8", errors="ignore")
    return head, tail, removed_chars


def _iter_shell_output_char_byte_indices(output: str) -> Iterable[tuple[int, str]]:
    byte_index = 0
    for char in output:
        yield byte_index, char
        byte_index += len(char.encode("utf-8"))


def _local_http_truncation_marker(removed_count: int, *, unit: str = "chars") -> str:
    return f"\u2026{removed_count} {unit} truncated\u2026"


def _tool_name_from_item(item: Mapping[str, Any]) -> str:
    value = item.get("name") or item.get("tool") or item.get("server_label")
    return str(value or "")


def _local_http_function_call_argument_error(item: Mapping[str, Any], tool: str) -> str | None:
    if item.get("type") != "function_call":
        return None
    if tool not in {
        "exec_command",
        "shell_command",
        "shell",
        "local_shell",
        "exec",
        "write_stdin",
        "request_permissions",
        "view_image",
    }:
        return None
    raw_arguments = item.get("arguments")
    if raw_arguments is None:
        return "failed to parse function arguments: expected value"
    if isinstance(raw_arguments, str):
        try:
            parsed = json.loads(raw_arguments)
        except ValueError as exc:
            return f"failed to parse function arguments: {exc}"
    else:
        parsed = raw_arguments
    if not isinstance(parsed, Mapping):
        return "failed to parse function arguments: expected JSON object"
    if tool == "exec_command":
        return _local_http_exec_command_argument_error(parsed)
    return None


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


def _tool_arguments_json_from_item(item: Mapping[str, Any]) -> str:
    value = item.get("arguments")
    if value is None:
        value = item.get("input")
    if isinstance(value, str):
        return value
    return json.dumps(value if value is not None else {})


def _tool_output_from_item(item: Mapping[str, Any]) -> Any:
    value = item.get("output")
    if value is None:
        value = item.get("result")
    if value is None:
        value = item.get("content")
    return value if value is not None else ""


def reasoning_texts_from_local_http_exec_result(result: UserTurnSamplingResult) -> tuple[str, ...]:
    """Extract reasoning summary text from a local HTTP Responses payload."""

    return tuple(
        "\n".join(item.item.summary_text)
        for item in reasoning_turn_items_from_local_http_exec_result(result)
        if item.item.summary_text
    )


def reasoning_turn_items_from_local_http_exec_result(result: UserTurnSamplingResult) -> tuple[TurnItem, ...]:
    """Extract reasoning turn items from a local HTTP Responses payload."""

    items: list[TurnItem] = []
    for payload in _raw_responses_payloads(result):
        for index, item in enumerate(_response_output_mappings(payload)):
            item_type = str(item.get("type") or "")
            if item_type not in {"reasoning", "reasoning_summary"}:
                continue
            summary_text = _reasoning_summary_entries_from_item(item)
            raw_content = _reasoning_raw_content_entries_from_item(item)
            if summary_text or raw_content:
                item_id = str(item.get("id") or f"reasoning_{index}")
                items.append(TurnItem.reasoning(item_id, summary_text, raw_content))
    return tuple(items)


def _reasoning_summary_entries_from_item(item: Mapping[str, Any]) -> tuple[str, ...]:
    return _text_entries_from_value(_first_present(item, "summary", "summary_text", "summaryText"))


def _reasoning_raw_content_entries_from_item(item: Mapping[str, Any]) -> tuple[str, ...]:
    return _text_entries_from_value(
        _first_present(item, "content", "raw_content", "rawContent"),
        include_reasoning_text=True,
    )


def _first_present(value: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in value:
            return value.get(name)
    return None


def _text_from_value(value: Any) -> str:
    return "\n".join(_text_entries_from_value(value))


def _text_entries_from_value(value: Any, *, include_reasoning_text: bool = False) -> tuple[str, ...]:
    if isinstance(value, str):
        return (value,) if value else ()
    if isinstance(value, Mapping):
        if value.get("type") == "reasoning_text" and not include_reasoning_text:
            return ()
        for name in ("text", "summary", "summary_text", "summaryText", "content", "raw_content", "rawContent"):
            text = _text_entries_from_value(value.get(name), include_reasoning_text=include_reasoning_text)
            if text:
                return text
        return ()
    if isinstance(value, (list, tuple)):
        parts: list[str] = []
        for item in value:
            parts.extend(_text_entries_from_value(item, include_reasoning_text=include_reasoning_text))
        return tuple(parts)
    return ()


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
        raw_tool_output_items=(
            tuple(getattr(previous, "raw_tool_output_items", ()) or ())
            + tuple(tool_outputs)
            + tuple(getattr(followup, "raw_tool_output_items", ()) or ())
        ),
        request_plans=previous_request_plans + followup_request_plans,
        raw_results=previous_raw_results + followup_raw_results,
        raw_result=followup.raw_result,
        session_events=(
            tuple(getattr(previous, "session_events", ()) or ())
            + tuple(getattr(followup, "session_events", ()) or ())
        ),
        stream_events=(
            tuple(getattr(previous, "stream_events", ()) or ())
            + tuple(getattr(followup, "stream_events", ()) or ())
        ),
        stream_event_dispatch_plans=(
            tuple(getattr(previous, "stream_event_dispatch_plans", ()) or ())
            + tuple(getattr(followup, "stream_event_dispatch_plans", ()) or ())
        ),
        stream_event_apply_plans=(
            tuple(getattr(previous, "stream_event_apply_plans", ()) or ())
            + tuple(getattr(followup, "stream_event_apply_plans", ()) or ())
        ),
        stream_runtime_state_summary=(
            getattr(followup, "stream_runtime_state_summary", None)
            if getattr(followup, "stream_runtime_state_summary", None) is not None
            else getattr(previous, "stream_runtime_state_summary", None)
        ),
        last_agent_message=(
            getattr(followup, "last_agent_message", None)
            if getattr(followup, "last_agent_message", None) is not None
            else getattr(previous, "last_agent_message", None)
        ),
        turn_status=getattr(followup, "turn_status", getattr(previous, "turn_status", "completed")),
    )


def _replay_local_http_session_events(
    processor: HumanEventProcessor | JsonEventProcessor,
    result: UserTurnSamplingResult,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    for event in tuple(getattr(result, "session_events", ()) or ()):
        notification = _local_http_session_event_notification(event)
        if notification is None:
            continue
        if isinstance(processor, JsonEventProcessor):
            processor.process_server_notification(notification, output=stdout)
        else:
            processor.process_server_notification(notification, stderr=stderr)


def _local_http_session_event_notification(event: Any) -> Mapping[str, Any] | None:
    event_type = getattr(event, "type", None)
    payload = getattr(event, "payload", None)
    if event_type == "warning":
        message = getattr(payload, "message", None)
        if not isinstance(message, str) or not message:
            return None
        return {"method": "warning", "params": {"message": message}}
    if event_type == "stream_error":
        message = getattr(payload, "message", None)
        if not isinstance(message, str) or not message:
            return None
        return {
            "method": "error",
            "params": {
                "error": {
                    "message": message,
                    "additionalDetails": getattr(payload, "additional_details", None),
                    "codexErrorInfo": _local_http_codex_error_info(getattr(payload, "codex_error_info", None)),
                },
                "willRetry": True,
            },
        }
    if event_type == "error":
        message = getattr(payload, "message", None)
        if not isinstance(message, str) or not message:
            return None
        return {
            "method": "error",
            "params": {
                "error": {
                    "message": message,
                    "codexErrorInfo": _local_http_codex_error_info(getattr(payload, "codex_error_info", None)),
                },
            },
        }
    if event_type == "model_reroute":
        from_model = getattr(payload, "from_model", None)
        to_model = getattr(payload, "to_model", None)
        reason = getattr(payload, "reason", None)
        if not isinstance(from_model, str) or not isinstance(to_model, str):
            return None
        return {
            "method": "model/rerouted",
            "params": {
                "from_model": from_model,
                "to_model": to_model,
                "reason": _local_http_enum_value(reason),
            },
        }
    if event_type == "model_verification":
        verifications = getattr(payload, "verifications", None)
        if verifications is None:
            return None
        return {
            "method": "model/verification",
            "params": {
                "verifications": [_local_http_enum_value(item) for item in tuple(verifications)],
            },
        }
    if event_type == "token_count":
        info = getattr(payload, "info", None)
        if info is None:
            return None
        total = getattr(info, "total_token_usage", None)
        if total is None:
            return None
        to_mapping = getattr(total, "to_mapping", None)
        total_payload = to_mapping() if callable(to_mapping) else total
        if not isinstance(total_payload, Mapping):
            return None
        return {
            "method": "thread/tokenUsage/updated",
            "params": {
                "tokenUsage": {
                    "total": dict(total_payload),
                }
            },
        }
    return None


def _session_events_include_replayed_terminal_error(session_events: tuple[Any, ...]) -> bool:
    for event in session_events:
        if getattr(event, "type", None) != "error":
            continue
        if _local_http_session_event_notification(event) is not None:
            return True
    return False


def _local_http_enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _local_http_codex_error_info(value: Any) -> Mapping[str, Any] | None:
    if value is None:
        return None
    to_mapping = getattr(value, "to_mapping", None)
    if callable(to_mapping):
        mapped = to_mapping()
        return mapped if isinstance(mapped, Mapping) else None
    if isinstance(value, Mapping):
        return value
    info_type = getattr(value, "type", None)
    if not isinstance(info_type, str) or not info_type:
        return None
    mapped: dict[str, Any] = {"type": info_type}
    http_status_code = getattr(value, "http_status_code", None)
    if http_status_code is not None:
        mapped["httpStatusCode"] = http_status_code
    return mapped


def _usage_is_zero(usage: Usage) -> bool:
    return (
        usage.input_tokens == 0
        and usage.cached_input_tokens == 0
        and usage.output_tokens == 0
        and usage.reasoning_output_tokens == 0
    )


def _attach_local_http_session_events(error: CodexErr, session: InMemoryCodexSession) -> None:
    try:
        object.__setattr__(error, "session_events", tuple(session.emitted_events))
    except Exception:
        return


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
    message: str | BaseException,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Render a local HTTP exec failure through the normal exec processors."""

    error_message = str(message)
    session_events = tuple(getattr(message, "session_events", ()) or ())
    if isinstance(processor, JsonEventProcessor):
        processor.emit_json_lines((ThreadEvent.turn_started(),), stdout)
        if session_events:
            _replay_local_http_session_events(processor, _SessionEventsResult(session_events), stdout=stdout)
        processor.emit_json_lines(
            (
                ThreadEvent.turn_failed(ThreadErrorEvent(error_message)),
            ),
            stdout,
        )
        return

    if session_events:
        _replay_local_http_session_events(processor, _SessionEventsResult(session_events), stderr=stderr)
    turn_error = None if _session_events_include_replayed_terminal_error(session_events) else {"message": error_message}
    processor.process_server_notification(
        exec_turn_completed_notification(
            "",
            "",
            (),
            status="failed",
            error=turn_error,
        ),
        stderr=stderr,
    )


@dataclass(frozen=True)
class _SessionEventsResult:
    session_events: tuple[Any, ...]


core_exec_config_summary = local_http_exec_config_summary
core_exec_enabled = local_core_exec_enabled
core_exec_initial_messages_from_rollout = local_http_exec_initial_messages_from_rollout
core_review_rollout_input_items = local_http_review_rollout_input_items
persist_core_exec_resume_rollout = persist_local_http_exec_resume_rollout
persist_core_exec_rollout = persist_local_http_exec_rollout


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
    "LOCAL_HTTP_REVIEW_DISABLED_TOOL_NAMES",
    "LocalHttpShellInvocation",
    "LocalHttpWriteStdinInvocation",
    "LocalHttpHeadTailBuffer",
    "LocalHttpExecSessionManager",
    "LocalHttpModelInfo",
    "LocalHttpProvider",
    "LocalHttpReviewModelInfo",
    "local_http_exec_command_output_schema",
    "local_http_exec_output_text",
    "local_http_write_stdin_tool_spec",
    "local_http_request_permissions_tool_spec",
    "local_http_request_permissions_unavailable_output",
    "local_http_write_stdin_unavailable_output",
    "local_http_model_allows_apply_patch_tool",
    "local_http_model_allows_view_image_tool",
    "local_http_model_disabled_tool_names",
    "local_http_model_supports_image_inputs",
    "local_http_model_can_request_original_image_detail",
    "local_http_view_image_tool_spec",
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
    "final_text_from_local_http_exec_result",
    "final_text_from_response_items",
    "core_exec_config_summary",
    "core_exec_enabled",
    "core_exec_initial_messages_from_rollout",
    "core_review_rollout_input_items",
    "persist_core_exec_resume_rollout",
    "persist_core_exec_rollout",
    "local_core_exec_enabled",
    "local_http_exec_enabled",
    "local_http_exec_max_tool_rounds",
    "local_http_generate_chunk_id",
    "local_http_retain_head_tail_output",
    "local_http_exec_schema_output_payload",
    "local_http_exec_shell_tools_enabled",
    "local_http_exec_tool_output_max_chars",
    "local_http_exec_config_summary",
    "local_http_exec_initial_messages_from_rollout",
    "local_http_review_rollout_input_items",
    "local_http_review_user_turn_plan",
    "local_http_shell_tool_approval_required_output",
    "local_http_shell_tool_auto_execute_allowed",
    "persist_local_http_exec_rollout",
    "persist_local_http_exec_resume_rollout",
    "reasoning_texts_from_local_http_exec_result",
    "resolve_local_http_exec_resume_rollout_path",
    "response_items_from_local_http_tool_outputs",
    "parse_local_http_review_output",
    "render_local_http_review_interrupted_rollout_user_message",
    "render_local_http_review_rollout_user_message",
    "prewarm_exec_core_websocket_session",
    "run_exec_review_http_sampling",
    "run_exec_review_core_http_sampling",
    "run_exec_resume_user_turn_core_http_sampling",
    "run_exec_user_turn_core_http_sampling",
    "run_exec_user_turn_core_sampling_websocket_preferred",
    "run_exec_user_turn_core_sampling",
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





