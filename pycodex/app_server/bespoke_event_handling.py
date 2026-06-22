"""Bespoke app-server event handling helpers.

Ported from ``codex-app-server/src/bespoke_event_handling.rs``. The Rust
module contains the full async event dispatcher; this Python slice mirrors the
module-local conversion and fallback helpers that are stable at the behavior
contract boundary. Concrete thread state, outgoing transport, and Codex thread
submission remain runtime-owned.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import time
from typing import Any, Mapping

from pycodex.app_server_protocol import (
    FileChangeApprovalDecision,
    HookPromptFragment,
    McpServerElicitationAction,
    McpServerElicitationRequestResponse,
    PermissionGrantScope,
    PermissionsRequestApprovalResponse,
    ThreadItem,
    Turn,
    TurnCompletedNotification,
    TurnDiffUpdatedNotification,
    TurnError,
    TurnItemsView,
    TurnPlanStep,
    TurnPlanUpdatedNotification,
    TurnStatus,
)
from pycodex.protocol import ReviewDecision, parse_hook_prompt_message

JsonValue = Any
REVIEW_FALLBACK_MESSAGE = "Reviewer failed to output a response."


@dataclass(frozen=True)
class CommandExecutionCompletionItem:
    command: str
    cwd: Path | str
    command_actions: tuple[JsonValue, ...] = ()


@dataclass(frozen=True)
class TurnCompletionMetadata:
    status: TurnStatus | str
    error: TurnError | Mapping[str, JsonValue] | None = None
    started_at: int | None = None
    completed_at: int | None = None
    duration_ms: int | None = None


def turn_diff_updated_notification(
    conversation_id: str,
    event_turn_id: str,
    unified_diff: str,
) -> TurnDiffUpdatedNotification:
    return TurnDiffUpdatedNotification(
        thread_id=str(conversation_id),
        turn_id=str(event_turn_id),
        diff=unified_diff,
    )


def turn_plan_updated_notification(
    conversation_id: str,
    event_turn_id: str,
    plan_update_event: Mapping[str, JsonValue] | Any,
) -> TurnPlanUpdatedNotification:
    plan = tuple(TurnPlanStep.from_mapping(_mapping_step(step)) for step in _field(plan_update_event, "plan", ()))
    return TurnPlanUpdatedNotification(
        thread_id=str(conversation_id),
        turn_id=str(event_turn_id),
        explanation=_field(plan_update_event, "explanation", None),
        plan=plan,
    )


def turn_completed_notification(
    conversation_id: str,
    event_turn_id: str,
    metadata: TurnCompletionMetadata,
) -> TurnCompletedNotification:
    return TurnCompletedNotification(
        thread_id=str(conversation_id),
        turn=Turn(
            id=str(event_turn_id),
            items=(),
            items_view=TurnItemsView.NOT_LOADED,
            error=metadata.error,
            status=metadata.status,
            started_at=metadata.started_at,
            completed_at=metadata.completed_at,
            duration_ms=metadata.duration_ms,
        ),
    )


def hook_prompt_item_completed_payload(
    conversation_id: str,
    turn_id: str,
    item: Mapping[str, JsonValue] | Any,
    *,
    completed_at_ms: int | None = None,
) -> dict[str, JsonValue] | None:
    role = _field(item, "role", None)
    if role != "user":
        return None
    content = _field(item, "content", ())
    item_id = _field(item, "id", None)
    hook_prompt = parse_hook_prompt_message(item_id, content)
    if hook_prompt is None:
        return None
    return {
        "thread_id": str(conversation_id),
        "turn_id": str(turn_id),
        "completed_at_ms": now_unix_timestamp_ms() if completed_at_ms is None else completed_at_ms,
        "item": ThreadItem(
            "hookPrompt",
            {
                "id": hook_prompt.id,
                "fragments": tuple(
                    HookPromptFragment(text=fragment.text, hook_run_id=fragment.hook_run_id)
                    for fragment in hook_prompt.fragments
                ),
            },
        ),
    }


def mcp_server_elicitation_response_from_client_result(
    response: JsonValue,
    *,
    turn_transition_error: bool = False,
) -> McpServerElicitationRequestResponse:
    if turn_transition_error:
        return McpServerElicitationRequestResponse(
            action=McpServerElicitationAction.CANCEL,
            content=None,
            meta=None,
        )
    if _is_error_result(response):
        return McpServerElicitationRequestResponse(
            action=McpServerElicitationAction.DECLINE,
            content=None,
            meta=None,
        )
    try:
        return McpServerElicitationRequestResponse.from_mapping(_unwrap_ok_result(response))
    except Exception:
        return McpServerElicitationRequestResponse(
            action=McpServerElicitationAction.DECLINE,
            content=None,
            meta=None,
        )


def request_permissions_response_from_client_result(
    response: JsonValue,
    *,
    turn_transition_error: bool = False,
) -> dict[str, JsonValue] | None:
    if turn_transition_error:
        return None
    if _is_error_result(response):
        return _default_request_permissions_response()
    try:
        parsed = PermissionsRequestApprovalResponse.from_mapping(_unwrap_ok_result(response))
    except Exception:
        return _default_request_permissions_response()
    strict_auto_review = bool(parsed.strict_auto_review or False)
    if strict_auto_review and parsed.scope == PermissionGrantScope.SESSION:
        return _default_request_permissions_response()
    return {
        "permissions": parsed.permissions,
        "scope": parsed.scope.to_core(),
        "strict_auto_review": strict_auto_review,
    }


def render_review_output_text(output: Mapping[str, JsonValue] | Any) -> str:
    sections: list[str] = []
    explanation = str(_field(output, "overall_explanation", "") or "").strip()
    if explanation:
        sections.append(explanation)
    findings = tuple(_field(output, "findings", ()) or ())
    findings_block = _format_review_findings_block(findings).strip()
    if findings_block:
        sections.append(findings_block)
    if not sections:
        return REVIEW_FALLBACK_MESSAGE
    return "\n\n".join(sections)


def map_file_change_approval_decision(decision: FileChangeApprovalDecision | str) -> ReviewDecision:
    parsed = FileChangeApprovalDecision.parse(decision)
    if parsed == FileChangeApprovalDecision.ACCEPT:
        return ReviewDecision.approved()
    if parsed == FileChangeApprovalDecision.ACCEPT_FOR_SESSION:
        return ReviewDecision.approved_for_session()
    if parsed == FileChangeApprovalDecision.DECLINE:
        return ReviewDecision.denied()
    if parsed == FileChangeApprovalDecision.CANCEL:
        return ReviewDecision.abort()
    raise ValueError(f"unknown file change approval decision: {decision}")


def now_unix_timestamp_ms() -> int:
    return int(time() * 1000)


def _default_request_permissions_response() -> dict[str, JsonValue]:
    return {
        "permissions": {},
        "scope": "turn",
        "strict_auto_review": False,
    }


def _format_review_findings_block(findings: tuple[JsonValue, ...]) -> str:
    lines: list[str] = []
    for index, finding in enumerate(findings, start=1):
        title = _field(finding, "title", None) or _field(finding, "message", None) or _field(finding, "body", None)
        if title is None:
            title = str(finding)
        lines.append(f"{index}. {str(title).strip()}")
    return "\n".join(line for line in lines if line.strip())


def _mapping_step(step: Mapping[str, JsonValue] | Any) -> Mapping[str, JsonValue]:
    if isinstance(step, Mapping):
        return step
    return {"step": _field(step, "step"), "status": _field(step, "status")}


def _unwrap_ok_result(response: JsonValue) -> Mapping[str, JsonValue]:
    if isinstance(response, Mapping) and "ok" in response:
        value = response["ok"]
    else:
        value = response
    if not isinstance(value, Mapping):
        raise TypeError("client result must be a mapping")
    return value


def _is_error_result(response: JsonValue) -> bool:
    return isinstance(response, Mapping) and ("error" in response or "err" in response)


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        if name in value:
            return value[name]
        camel = _snake_to_camel(name)
        if camel in value:
            return value[camel]
        return default
    return getattr(value, name, default)


def _snake_to_camel(value: str) -> str:
    head, *tail = value.split("_")
    return head + "".join(part[:1].upper() + part[1:] for part in tail)


__all__ = [
    "CommandExecutionCompletionItem",
    "REVIEW_FALLBACK_MESSAGE",
    "TurnCompletionMetadata",
    "hook_prompt_item_completed_payload",
    "map_file_change_approval_decision",
    "mcp_server_elicitation_response_from_client_result",
    "now_unix_timestamp_ms",
    "render_review_output_text",
    "request_permissions_response_from_client_result",
    "turn_completed_notification",
    "turn_diff_updated_notification",
    "turn_plan_updated_notification",
]
