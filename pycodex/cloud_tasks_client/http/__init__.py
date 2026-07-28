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

from ..api import (
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

from .api import (
    details_path,
    extract_assistant_messages_from_body,
    turn_attempt_from_map,
    extract_diff_from_turn,
    extract_assistant_messages_from_turn,
    attempt_status_from_str,
    parse_timestamp_value,
    map_task_list_item_to_summary,
    map_status,
    parse_updated_at,
    env_label_from_status_display,
    diff_summary_from_diff,
    diff_summary_from_status_display,
    latest_turn_timestamp,
    attempt_total_from_status_display,
    is_unified_diff,
    tail,
    summarize_patch_for_logging,
    unified_diff,
    assistant_text_messages,
    user_text_prompt,
    assistant_error_message,
    _worklog_assistant_messages,
    _content_text_values,
    _attempt_sort_key,
    _get,
    _string_or_none,
    _int_or_none,
    _float_or_none,
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
