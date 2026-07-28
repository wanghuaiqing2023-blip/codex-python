"""Inline ``api`` module from Rust ``cloud-tasks-client/src/http.rs``."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ..api import (
    AttemptStatus,
    DiffSummary,
    TaskId,
    TaskStatus,
    TaskSummary,
    TurnAttempt,
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
