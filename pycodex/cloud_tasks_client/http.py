"""Port of Rust ``codex-cloud-tasks-client/src/http.rs``.

The Rust module wraps ``codex_backend_client`` and ``codex_git_utils``. Python
keeps the same CloudBackend-facing behavior with injectable backend and apply
adapters so tests and core callers do not need a live cloud service.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .api import (
    ApplyOutcome,
    ApplyStatus,
    AttemptStatus,
    CloudTaskError,
    CreatedTask,
    DiffSummary,
    TaskId,
    TaskListPage,
    TaskStatus,
    TaskSummary,
    TaskText,
    TurnAttempt,
)


@dataclass(frozen=True)
class ApplyGitRequest:
    cwd: Path
    diff: str
    revert: bool = False
    preflight: bool = False


@dataclass(frozen=True)
class ApplyGitResult:
    exit_code: int
    applied_paths: list[str] = field(default_factory=list)
    skipped_paths: list[str] = field(default_factory=list)
    conflicted_paths: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    cmd_for_log: str = "git apply"


ApplyGitPatch = Callable[[ApplyGitRequest], ApplyGitResult]


class HttpClient:
    def __init__(
        self,
        base_url: str,
        *,
        backend: Any | None = None,
        apply_git_patch: ApplyGitPatch | None = None,
    ) -> None:
        self.base_url = str(base_url)
        self.backend = backend if backend is not None else _MissingBackend(self.base_url)
        self._apply_git_patch = apply_git_patch or _missing_apply_git_patch
        self.user_agent: str | None = None
        self.auth_provider: object | None = None
        self.chatgpt_account_id: str | None = None

    @classmethod
    def new(cls, base_url: str) -> "HttpClient":
        return cls(base_url)

    def with_user_agent(self, ua: str) -> "HttpClient":
        self.user_agent = str(ua)
        if hasattr(self.backend, "with_user_agent"):
            self.backend = self.backend.with_user_agent(ua)
        else:
            setattr(self.backend, "user_agent", self.user_agent)
        return self

    def with_auth_provider(self, auth: object) -> "HttpClient":
        self.auth_provider = auth
        if hasattr(self.backend, "with_auth_provider"):
            self.backend = self.backend.with_auth_provider(auth)
        else:
            setattr(self.backend, "auth_provider", self.auth_provider)
        return self

    def with_chatgpt_account_id(self, account_id: str) -> "HttpClient":
        self.chatgpt_account_id = str(account_id)
        if hasattr(self.backend, "with_chatgpt_account_id"):
            self.backend = self.backend.with_chatgpt_account_id(account_id)
        else:
            setattr(self.backend, "chatgpt_account_id", self.chatgpt_account_id)
        return self

    async def list_tasks(
        self, env: str | None = None, limit: int | None = None, cursor: str | None = None
    ) -> TaskListPage:
        limit_i32 = limit if isinstance(limit, int) and -(2**31) <= limit < 2**31 else None
        try:
            resp = await self.backend.list_tasks(limit_i32, "current", env, cursor)
        except Exception as exc:  # pragma: no cover - exercised through tests with fake errors
            raise CloudTaskError.http(f"list_tasks failed: {exc}") from exc
        items = _get(resp, "items", []) or []
        return TaskListPage(
            tasks=[map_task_list_item_to_summary(item) for item in items],
            cursor=_get(resp, "cursor"),
        )

    async def get_task_summary(self, id: TaskId) -> TaskSummary:
        details, body, content_type = await self._details_with_body(id.value)
        try:
            parsed = json.loads(body)
        except Exception as exc:
            raise CloudTaskError.http(
                f"Decode error for {id.value}: {exc}; content-type={content_type}; body={body}"
            ) from exc
        task_obj = _get(parsed, "task")
        if not isinstance(task_obj, dict):
            raise CloudTaskError.http(f"Task metadata missing from details for {id.value}")
        status_display = _get(parsed, "task_status_display") or _get(task_obj, "task_status_display")
        if not isinstance(status_display, dict):
            status_display = None
        summary = diff_summary_from_status_display(status_display)
        if summary == DiffSummary():
            diff = unified_diff(details)
            if diff is not None:
                summary = diff_summary_from_diff(diff)
        updated_at_raw = (
            _float_or_none(_get(task_obj, "updated_at"))
            or _float_or_none(_get(task_obj, "created_at"))
            or latest_turn_timestamp(status_display)
        )
        return TaskSummary(
            id=id,
            title=str(_get(task_obj, "title", "<untitled>")),
            status=map_status(status_display),
            updated_at=parse_updated_at(updated_at_raw),
            environment_id=_string_or_none(_get(task_obj, "environment_id")),
            environment_label=env_label_from_status_display(status_display),
            summary=summary,
            is_review=bool(_get(task_obj, "is_review", False)),
            attempt_total=attempt_total_from_status_display(status_display),
        )

    async def get_task_diff(self, id: TaskId) -> str | None:
        details, _body, _content_type = await self._details_with_body(id.value)
        return unified_diff(details)

    async def get_task_messages(self, id: TaskId) -> list[str]:
        details, body, content_type = await self._details_with_body(id.value)
        messages = assistant_text_messages(details)
        if not messages:
            messages.extend(extract_assistant_messages_from_body(body))
        if messages:
            return messages
        error = assistant_error_message(details)
        if error:
            return [f"Task failed: {error}"]
        url = details_path(self.base_url, id.value) or f"{self.base_url}/api/codex/tasks/{id.value}"
        raise CloudTaskError.http(
            f"No assistant text messages in response. GET {url}; content-type={content_type}; body={body}"
        )

    async def get_task_text(self, id: TaskId) -> TaskText:
        details, body, _content_type = await self._details_with_body(id.value)
        messages = assistant_text_messages(details)
        if not messages:
            messages.extend(extract_assistant_messages_from_body(body))
        assistant_turn = _get(details, "current_assistant_turn")
        return TaskText(
            prompt=user_text_prompt(details),
            messages=messages,
            turn_id=_string_or_none(_get(assistant_turn, "id")),
            sibling_turn_ids=list(_get(assistant_turn, "sibling_turn_ids", []) or []),
            attempt_placement=_int_or_none(_get(assistant_turn, "attempt_placement")),
            attempt_status=attempt_status_from_str(_string_or_none(_get(assistant_turn, "turn_status"))),
        )

    async def list_sibling_attempts(self, task: TaskId, turn_id: str) -> list[TurnAttempt]:
        try:
            resp = await self.backend.list_sibling_turns(task.value, turn_id)
        except Exception as exc:
            raise CloudTaskError.http(f"list_sibling_turns failed: {exc}") from exc
        attempts = [
            attempt
            for turn in (_get(resp, "sibling_turns", []) or [])
            if (attempt := turn_attempt_from_map(turn)) is not None
        ]
        return sorted(attempts, key=_attempt_sort_key)

    async def apply_task_preflight(
        self, id: TaskId, diff_override: str | None = None
    ) -> ApplyOutcome:
        return await self._run_apply(id, diff_override, preflight=True)

    async def apply_task(self, id: TaskId, diff_override: str | None = None) -> ApplyOutcome:
        return await self._run_apply(id, diff_override, preflight=False)

    async def create_task(
        self, env_id: str, prompt: str, git_ref: str, qa_mode: bool, best_of_n: int
    ) -> CreatedTask:
        input_items: list[dict[str, Any]] = [
            {
                "type": "message",
                "role": "user",
                "content": [{"content_type": "text", "text": prompt}],
            }
        ]
        diff = os.environ.get("CODEX_STARTING_DIFF", "")
        if diff:
            input_items.append({"type": "pre_apply_patch", "output_diff": {"diff": diff}})
        request_body: dict[str, Any] = {
            "new_task": {
                "environment_id": env_id,
                "branch": git_ref,
                "run_environment_in_qa_mode": qa_mode,
            },
            "input_items": input_items,
        }
        if best_of_n > 1:
            request_body["metadata"] = {"best_of_n": best_of_n}
        try:
            created_id = await self.backend.create_task(request_body)
        except Exception as exc:
            raise CloudTaskError.http(f"create_task failed: {exc}") from exc
        return CreatedTask(id=TaskId(str(created_id)))

    async def _details_with_body(self, id: str) -> tuple[Any, str, str]:
        try:
            return await self.backend.get_task_details_with_body(id)
        except Exception as exc:
            raise CloudTaskError.http(f"get_task_details failed: {exc}") from exc

    async def _run_apply(
        self, task_id: TaskId, diff_override: str | None, *, preflight: bool
    ) -> ApplyOutcome:
        id = task_id.value
        if diff_override is None:
            try:
                details = await self.backend.get_task_details(id)
            except Exception as exc:
                raise CloudTaskError.http(f"get_task_details failed: {exc}") from exc
            diff = unified_diff(details)
            if diff is None:
                raise CloudTaskError.msg(f"No diff available for task {id}")
        else:
            diff = diff_override

        if not is_unified_diff(diff):
            return ApplyOutcome(
                applied=False,
                status=ApplyStatus.ERROR,
                message="Expected unified git diff; backend returned an incompatible format.",
            )

        try:
            result = self._apply_git_patch(
                ApplyGitRequest(cwd=Path.cwd(), diff=diff, revert=False, preflight=preflight)
            )
        except OSError as exc:
            raise CloudTaskError.io(f"git apply failed to run: {exc}") from exc

        if result.exit_code == 0:
            status = ApplyStatus.SUCCESS
        elif result.applied_paths or result.conflicted_paths:
            status = ApplyStatus.PARTIAL
        else:
            status = ApplyStatus.ERROR
        applied = status is ApplyStatus.SUCCESS and not preflight

        if preflight:
            if status is ApplyStatus.SUCCESS:
                message = f"Preflight passed for task {id} (applies cleanly)"
            elif status is ApplyStatus.PARTIAL:
                message = (
                    f"Preflight: patch does not fully apply for task {id} "
                    f"(applied={len(result.applied_paths)}, skipped={len(result.skipped_paths)}, "
                    f"conflicts={len(result.conflicted_paths)})"
                )
            else:
                message = (
                    f"Preflight failed for task {id} "
                    f"(applied={len(result.applied_paths)}, skipped={len(result.skipped_paths)}, "
                    f"conflicts={len(result.conflicted_paths)})"
                )
        elif status is ApplyStatus.SUCCESS:
            message = f"Applied task {id} locally ({len(result.applied_paths)} files)"
        elif status is ApplyStatus.PARTIAL:
            message = (
                f"Apply partially succeeded for task {id} "
                f"(applied={len(result.applied_paths)}, skipped={len(result.skipped_paths)}, "
                f"conflicts={len(result.conflicted_paths)})"
            )
        else:
            message = (
                f"Apply failed for task {id} "
                f"(applied={len(result.applied_paths)}, skipped={len(result.skipped_paths)}, "
                f"conflicts={len(result.conflicted_paths)})"
            )

        return ApplyOutcome(
            applied=applied,
            status=status,
            message=message,
            skipped_paths=list(result.skipped_paths),
            conflict_paths=list(result.conflicted_paths),
        )


def details_path(base_url: str, id: str) -> str | None:
    if "/backend-api" in base_url:
        return f"{base_url}/wham/tasks/{id}"
    if "/api/codex" in base_url:
        return f"{base_url}/tasks/{id}"
    return None


def extract_assistant_messages_from_body(body: str) -> list[str]:
    try:
        full = json.loads(body)
    except Exception:
        return []
    arr = _get(_get(_get(full, "current_assistant_turn"), "worklog"), "messages")
    if not isinstance(arr, list):
        return []
    messages: list[str] = []
    for message in arr:
        if _get(_get(message, "author"), "role") != "assistant":
            continue
        parts = _get(_get(message, "content"), "parts")
        if not isinstance(parts, list):
            continue
        for part in parts:
            if isinstance(part, str):
                if part:
                    messages.append(part)
            elif isinstance(part, dict) and part.get("content_type") == "text":
                if isinstance(part.get("text"), str):
                    messages.append(part["text"])
    return messages


def turn_attempt_from_map(turn: Any) -> TurnAttempt | None:
    turn_id = _string_or_none(_get(turn, "id"))
    if turn_id is None:
        return None
    return TurnAttempt(
        turn_id=turn_id,
        attempt_placement=_int_or_none(_get(turn, "attempt_placement")),
        created_at=parse_timestamp_value(_get(turn, "created_at")),
        status=attempt_status_from_str(_string_or_none(_get(turn, "turn_status"))),
        diff=extract_diff_from_turn(turn),
        messages=extract_assistant_messages_from_turn(turn),
    )


def extract_diff_from_turn(turn: Any) -> str | None:
    items = _get(turn, "output_items")
    if not isinstance(items, list):
        return None
    for item in items:
        kind = _get(item, "type")
        if kind == "output_diff":
            diff = _string_or_none(_get(item, "diff"))
            if diff:
                return diff
        elif kind == "pr":
            diff = _string_or_none(_get(_get(item, "output_diff"), "diff"))
            if diff:
                return diff
    return None


def extract_assistant_messages_from_turn(turn: Any) -> list[str]:
    messages: list[str] = []
    items = _get(turn, "output_items")
    if not isinstance(items, list):
        return messages
    for item in items:
        if _get(item, "type") != "message":
            continue
        content = _get(item, "content")
        if not isinstance(content, list):
            continue
        for part in content:
            if _get(part, "content_type") == "text":
                text = _string_or_none(_get(part, "text"))
                if text:
                    messages.append(text)
    return messages


def attempt_status_from_str(raw: str | None) -> AttemptStatus:
    if raw == "failed":
        return AttemptStatus.FAILED
    if raw == "completed":
        return AttemptStatus.COMPLETED
    if raw == "in_progress":
        return AttemptStatus.IN_PROGRESS
    if raw == "pending":
        return AttemptStatus.PENDING
    return AttemptStatus.PENDING


def parse_timestamp_value(value: Any) -> datetime | None:
    ts = _float_or_none(value)
    if ts is None:
        return None
    return datetime.fromtimestamp(max(ts, 0.0), timezone.utc)


def map_task_list_item_to_summary(src: Any) -> TaskSummary:
    status_display = _get(src, "task_status_display")
    if not isinstance(status_display, dict):
        status_display = None
    pull_requests = _get(src, "pull_requests")
    return TaskSummary(
        id=TaskId(str(_get(src, "id"))),
        title=str(_get(src, "title", "")),
        status=map_status(status_display),
        updated_at=parse_updated_at(_float_or_none(_get(src, "updated_at"))),
        environment_id=None,
        environment_label=env_label_from_status_display(status_display),
        summary=diff_summary_from_status_display(status_display),
        is_review=bool(pull_requests),
        attempt_total=attempt_total_from_status_display(status_display),
    )


def map_status(value: dict[str, Any] | None) -> TaskStatus:
    if value:
        latest = _get(value, "latest_turn_status_display")
        turn_status = _string_or_none(_get(latest, "turn_status"))
        if turn_status is not None:
            return {
                "failed": TaskStatus.ERROR,
                "completed": TaskStatus.READY,
                "in_progress": TaskStatus.PENDING,
                "pending": TaskStatus.PENDING,
                "cancelled": TaskStatus.ERROR,
            }.get(turn_status, TaskStatus.PENDING)
        state = _string_or_none(_get(value, "state"))
        if state is not None:
            return {
                "pending": TaskStatus.PENDING,
                "ready": TaskStatus.READY,
                "applied": TaskStatus.APPLIED,
                "error": TaskStatus.ERROR,
            }.get(state, TaskStatus.PENDING)
    return TaskStatus.PENDING


def parse_updated_at(ts: float | None) -> datetime:
    if ts is None:
        return datetime.now(timezone.utc)
    return datetime.fromtimestamp(max(ts, 0.0), timezone.utc)


def env_label_from_status_display(value: dict[str, Any] | None) -> str | None:
    return _string_or_none(_get(value, "environment_label"))


def diff_summary_from_diff(diff: str) -> DiffSummary:
    files_changed = 0
    lines_added = 0
    lines_removed = 0
    for line in diff.splitlines():
        if line.startswith("diff --git "):
            files_changed += 1
            continue
        if line.startswith(("+++", "---", "@@")):
            continue
        if line.startswith("+"):
            lines_added += 1
        elif line.startswith("-"):
            lines_removed += 1
    if files_changed == 0 and diff.strip():
        files_changed = 1
    return DiffSummary(files_changed, lines_added, lines_removed)


def diff_summary_from_status_display(value: dict[str, Any] | None) -> DiffSummary:
    latest = _get(value, "latest_turn_status_display")
    stats = _get(latest, "diff_stats")
    if not isinstance(stats, dict):
        return DiffSummary()
    return DiffSummary(
        files_changed=max(_int_or_none(_get(stats, "files_modified")) or 0, 0),
        lines_added=max(_int_or_none(_get(stats, "lines_added")) or 0, 0),
        lines_removed=max(_int_or_none(_get(stats, "lines_removed")) or 0, 0),
    )


def latest_turn_timestamp(value: dict[str, Any] | None) -> float | None:
    latest = _get(value, "latest_turn_status_display")
    return _float_or_none(_get(latest, "updated_at")) or _float_or_none(_get(latest, "created_at"))


def attempt_total_from_status_display(value: dict[str, Any] | None) -> int | None:
    latest = _get(value, "latest_turn_status_display")
    siblings = _get(latest, "sibling_turn_ids")
    if not isinstance(siblings, list):
        return None
    return len(siblings) + 1


def is_unified_diff(diff: str) -> bool:
    trimmed = diff.lstrip()
    if trimmed.startswith("diff --git "):
        return True
    return ("\n--- " in diff and "\n+++ " in diff) and ("\n@@ " in diff or diff.startswith("@@ "))


def tail(text: str, max_chars: int) -> str:
    return text if len(text) <= max_chars else text[-max_chars:]


def summarize_patch_for_logging(patch: str) -> str:
    trimmed = patch.lstrip()
    if trimmed.startswith("*** Begin Patch"):
        kind = "codex-patch"
    elif trimmed.startswith("diff --git ") or "\n*** End Patch\n" in trimmed:
        kind = "git-diff"
    elif trimmed.startswith("@@ ") or "\n@@ " in trimmed:
        kind = "unified-diff"
    else:
        kind = "unknown"
    head = "\n".join(patch.splitlines()[:20])
    if len(head) > 800:
        head = f"{head[:800]}..."
    return (
        f"patch_summary: kind={kind} lines={len(patch.splitlines())} "
        f"chars={len(patch)} cwd={Path.cwd()} ; head=\n{head}"
    )


def unified_diff(details: Any) -> str | None:
    for turn_name in ("current_diff_task_turn", "current_assistant_turn"):
        diff = extract_diff_from_turn(_get(details, turn_name))
        if diff:
            return diff
    return None


def assistant_text_messages(details: Any) -> list[str]:
    messages: list[str] = []
    for turn_name in ("current_diff_task_turn", "current_assistant_turn"):
        turn = _get(details, turn_name)
        messages.extend(extract_assistant_messages_from_turn(turn))
        messages.extend(_worklog_assistant_messages(turn))
    return messages


def user_text_prompt(details: Any) -> str | None:
    turn = _get(details, "current_user_turn")
    items = _get(turn, "input_items")
    if not isinstance(items, list):
        return None
    parts: list[str] = []
    for item in items:
        if _get(item, "type") != "message":
            continue
        role = _string_or_none(_get(item, "role"))
        if role is not None and role.lower() != "user":
            continue
        parts.extend(_content_text_values(_get(item, "content")))
    return "\n\n".join(parts) if parts else None


def assistant_error_message(details: Any) -> str | None:
    error = _get(_get(details, "current_assistant_turn"), "error")
    code = _string_or_none(_get(error, "code")) or ""
    message = _string_or_none(_get(error, "message")) or ""
    if code and message:
        return f"{code}: {message}"
    return code or message or None


def _worklog_assistant_messages(turn: Any) -> list[str]:
    messages = _get(_get(turn, "worklog"), "messages")
    if not isinstance(messages, list):
        return []
    out: list[str] = []
    for message in messages:
        role = _string_or_none(_get(_get(message, "author"), "role"))
        if role is None or role.lower() != "assistant":
            continue
        out.extend(_content_text_values(_get(_get(message, "content"), "parts")))
    return out


def _content_text_values(content: Any) -> list[str]:
    if not isinstance(content, list):
        return []
    out: list[str] = []
    for fragment in content:
        if isinstance(fragment, str):
            if fragment.strip():
                out.append(fragment)
        elif isinstance(fragment, dict):
            content_type = _string_or_none(_get(fragment, "content_type"))
            text = _string_or_none(_get(fragment, "text"))
            if content_type and content_type.lower() == "text" and text:
                out.append(text)
    return out


def _attempt_sort_key(attempt: TurnAttempt) -> tuple[int, Any]:
    if attempt.attempt_placement is not None:
        return (0, attempt.attempt_placement)
    if attempt.created_at is not None:
        return (1, attempt.created_at)
    return (2, attempt.turn_id)


def _get(value: Any, key: str, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, dict):
        return value.get(key, default)
    return getattr(value, key, default)


def _string_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _float_or_none(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


class _MissingBackend:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def _raise(self) -> None:
        raise RuntimeError("no backend adapter configured")

    async def list_tasks(self, *_args: Any, **_kwargs: Any) -> Any:
        self._raise()

    async def get_task_details_with_body(self, *_args: Any, **_kwargs: Any) -> Any:
        self._raise()

    async def get_task_details(self, *_args: Any, **_kwargs: Any) -> Any:
        self._raise()

    async def list_sibling_turns(self, *_args: Any, **_kwargs: Any) -> Any:
        self._raise()

    async def create_task(self, *_args: Any, **_kwargs: Any) -> Any:
        self._raise()


def _missing_apply_git_patch(_request: ApplyGitRequest) -> ApplyGitResult:
    raise OSError("no git apply adapter configured")


__all__ = [
    "ApplyGitRequest",
    "ApplyGitResult",
    "HttpClient",
    "assistant_error_message",
    "assistant_text_messages",
    "attempt_status_from_str",
    "attempt_total_from_status_display",
    "details_path",
    "diff_summary_from_diff",
    "diff_summary_from_status_display",
    "env_label_from_status_display",
    "extract_assistant_messages_from_body",
    "extract_assistant_messages_from_turn",
    "extract_diff_from_turn",
    "is_unified_diff",
    "latest_turn_timestamp",
    "map_status",
    "map_task_list_item_to_summary",
    "parse_timestamp_value",
    "parse_updated_at",
    "summarize_patch_for_logging",
    "tail",
    "turn_attempt_from_map",
    "unified_diff",
    "user_text_prompt",
]
