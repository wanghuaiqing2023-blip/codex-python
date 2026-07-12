"""App-server request dispatch for chat-widget semantic models.

Rust ``codex-tui::chatwidget::protocol_requests`` translates app-server
requests and a few related notifications into focused ``ChatWidget`` flows.
This Python port keeps the same behavior boundary using lightweight DTOs and
widget callback hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Mapping, Optional, Protocol, Tuple, Type, Union

from .._porting import RustTuiModule
from ...protocol.approvals import (
    ApplyPatchApprovalRequestEvent,
    ExecApprovalRequestEvent,
    FileChange,
    GuardianAssessmentAction,
    GuardianAssessmentDecisionSource,
    GuardianAssessmentEvent,
    GuardianAssessmentStatus,
    GuardianRiskLevel,
    GuardianUserAuthorization,
)
from ...protocol.request_permissions import RequestPermissionsEvent
from ...app_server_protocol.item import (
    ToolRequestUserInputOption,
    ToolRequestUserInputParams,
    ToolRequestUserInputQuestion,
)
from ...app_server_protocol.mcp import McpServerElicitationRequestParams

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::protocol_requests",
    source="codex/codex-rs/tui/src/chatwidget/protocol_requests.rs",
    status="complete",
)

__all__ = [
    "GuardianAssessmentDecisionSource",
    "GuardianAssessmentEvent",
    "GuardianAssessmentStatus",
    "GuardianRiskLevel",
    "GuardianUserAuthorization",
    "RUST_MODULE",
    "ServerRequest",
    "TUI_STUB_MESSAGE",
    "handle_server_request",
    "handle_skills_list_response",
    "on_deprecation_notice",
    "on_guardian_review_notification",
    "on_patch_apply_output_delta",
    "on_shutdown_complete",
    "on_turn_diff",
]


TUI_STUB_MESSAGE = "This request type is not supported in the TUI yet."


@dataclass(frozen=True)
class ServerRequest:
    kind: str
    id: Optional[str] = None
    params: Any = None
    request_id: Optional[str] = None


class ProtocolRequestsWidget(Protocol):
    config: Any


def handle_server_request(
    widget: Any,
    request: Union[ServerRequest, Mapping[str, Any], Any],
    replay_kind: Optional[Any] = None,
) -> None:
    """Route a server request to the matching focused chat-widget flow."""

    kind = _kind(request)
    request_id = str(_get(request, "id", _get(request, "request_id", "")))
    params = _get(request, "params", None)

    if kind == "CommandExecutionRequestApproval":
        fallback_cwd = getattr(widget.config, "cwd", None)
        _call(widget, "on_exec_approval_request", request_id, exec_approval_request_from_params(params, fallback_cwd))
    elif kind == "FileChangeRequestApproval":
        _call(widget, "on_apply_patch_approval_request", request_id, patch_approval_request_from_params(params))
    elif kind == "McpServerElicitationRequest":
        _call(
            widget,
            "on_elicitation_request",
            _get(request, "request_id", request_id),
            elicitation_params_from_params(params),
        )
    elif kind == "PermissionsRequestApproval":
        _call(widget, "on_request_permissions", request_permissions_from_params(params))
    elif kind == "ToolRequestUserInput":
        _call(widget, "on_request_user_input", user_input_params_from_params(params))
    elif kind in {
        "DynamicToolCall",
        "AttestationGenerate",
        "ChatgptAuthTokensRefresh",
        "ApplyPatchApproval",
        "ExecCommandApproval",
    }:
        if replay_kind is None:
            _call(widget, "add_error_message", TUI_STUB_MESSAGE)
    else:
        raise ValueError(f"unsupported ServerRequest variant: {kind!r}")


def elicitation_params_from_params(params: Any) -> McpServerElicitationRequestParams:
    """Decode the app-server payload at the Rust protocol owner boundary."""

    if isinstance(params, McpServerElicitationRequestParams):
        return params
    data = dict(params or {}) if isinstance(params, Mapping) else {
        name: getattr(params, name)
        for name in ("thread_id", "turn_id", "server_name", "request")
        if hasattr(params, name)
    }
    nested = data.get("request")
    if nested is not None:
        request_data = nested.to_mapping() if hasattr(nested, "to_mapping") else dict(nested)
        data = {
            "thread_id": data.get("thread_id", data.get("threadId", "")),
            "turn_id": data.get("turn_id", data.get("turnId")),
            "server_name": data.get("server_name", data.get("serverName", "")),
            **request_data,
        }
    return McpServerElicitationRequestParams.from_mapping(data)


def user_input_params_from_params(params: Any) -> ToolRequestUserInputParams:
    """Preserve thread/turn/item identity and typed question options."""

    if isinstance(params, ToolRequestUserInputParams):
        return params
    data = params if isinstance(params, Mapping) else vars(params)
    questions = []
    for raw_question in data.get("questions", ()) or ():
        question = raw_question if isinstance(raw_question, Mapping) else vars(raw_question)
        raw_options = question.get("options")
        options = None
        if raw_options is not None:
            options = tuple(
                option
                if isinstance(option, ToolRequestUserInputOption)
                else ToolRequestUserInputOption(
                    str(_get(option, "label", "")),
                    str(_get(option, "description", "")),
                )
                for option in raw_options
            )
        questions.append(
            ToolRequestUserInputQuestion(
                id=str(question.get("id", "")),
                header=str(question.get("header", "")),
                question=str(question.get("question", "")),
                is_other=bool(question.get("is_other", question.get("isOther", False))),
                is_secret=bool(question.get("is_secret", question.get("isSecret", False))),
                options=options,
            )
        )
    return ToolRequestUserInputParams(
        thread_id=str(data.get("thread_id", data.get("threadId", ""))),
        turn_id=str(data.get("turn_id", data.get("turnId", ""))),
        item_id=str(data.get("item_id", data.get("itemId", ""))),
        questions=tuple(questions),
    )


def handle_skills_list_response(widget: Any, response: Any) -> None:
    _call(widget, "on_list_skills", response)


def on_patch_apply_output_delta(widget: Any, item_id: str, delta: str) -> None:
    """Rust currently ignores patch output deltas in this module."""

    return None


def on_guardian_review_notification(
    widget: Any,
    id: str,
    turn_id: str,
    started_at_ms: int,
    review: Union[Mapping[str, Any], Any],
    completion: Optional[Tuple[int, Any]],
    action: Any,
    target_item_id: Optional[str] = None,
) -> GuardianAssessmentEvent:
    completed_at_ms = None
    decision_source = None
    if completion is not None:
        completed_at_ms, raw_source = completion
        decision_source = _decision_source(raw_source)

    event = GuardianAssessmentEvent(
        id=id,
        target_item_id=target_item_id,
        turn_id=turn_id,
        started_at_ms=started_at_ms,
        completed_at_ms=completed_at_ms,
        status=_assessment_status(_get(review, "status")),
        risk_level=_optional_enum(_get(review, "risk_level", None), GuardianRiskLevel),
        user_authorization=_optional_enum(
            _get(review, "user_authorization", None), GuardianUserAuthorization
        ),
        rationale=_get(review, "rationale", None),
        decision_source=decision_source,
        action=_guardian_action(action),
    )
    _call(widget, "on_guardian_assessment", event)
    return event


def on_shutdown_complete(widget: Any) -> None:
    _call(widget, "request_immediate_exit")


def on_turn_diff(widget: Any, unified_diff: str) -> None:
    _call(widget, "refresh_status_line")


def on_deprecation_notice(widget: Any, summary: str, details: Optional[str]) -> None:
    _call(widget, "add_to_history", {"kind": "deprecation_notice", "summary": summary, "details": details})
    _call(widget, "request_redraw")


def exec_approval_request_from_params(params: Any, fallback_cwd: Any) -> ExecApprovalRequestEvent:
    data = _as_dict(params)
    data.setdefault("call_id", data.get("item_id") or data.get("itemId") or data.get("id") or "")
    data.setdefault("started_at_ms", data.get("startedAtMs", 0))
    data.setdefault("cwd", str(fallback_cwd or "."))
    command = data.get("command", ())
    if isinstance(command, str):
        data["command"] = [command]
    return ExecApprovalRequestEvent.from_mapping(data)


def patch_approval_request_from_params(params: Any) -> ApplyPatchApprovalRequestEvent:
    data = _as_dict(params)
    raw_changes = data.get("changes") or {}
    changes: Dict[Any, FileChange] = {}
    for path, change in raw_changes.items():
        if isinstance(change, FileChange):
            changes[path] = change
            continue
        change_data = _as_dict(change)
        kind = str(change_data.get("type") or change_data.get("kind") or "").lower()
        if kind == "add":
            changes[path] = FileChange.add(str(change_data.get("content") or ""))
        elif kind == "delete":
            changes[path] = FileChange.delete(str(change_data.get("content") or ""))
        elif kind == "update":
            changes[path] = FileChange.update(
                str(change_data.get("unified_diff") or change_data.get("unifiedDiff") or ""),
                change_data.get("move_path") or change_data.get("movePath"),
            )
        else:
            raise ValueError(f"unknown file change type: {kind!r}")
    grant_root = data.get("grant_root") or data.get("grantRoot")
    return ApplyPatchApprovalRequestEvent(
        call_id=str(data.get("call_id") or data.get("item_id") or data.get("itemId") or data.get("id") or ""),
        turn_id=str(data.get("turn_id") or data.get("turnId") or ""),
        started_at_ms=int(data.get("started_at_ms", data.get("startedAtMs", 0))),
        changes=changes,
        reason=data.get("reason"),
        grant_root=grant_root,
    )


def request_permissions_from_params(params: Any) -> RequestPermissionsEvent:
    data = _as_dict(params)
    data.setdefault("call_id", data.get("item_id") or data.get("itemId") or data.get("id") or "")
    data.setdefault("started_at_ms", data.get("startedAtMs", 0))
    return RequestPermissionsEvent.from_mapping(data)


def _as_dict(value: Any) -> Dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"cannot convert params to semantic request dict: {type(value).__name__}")


def _kind(value: Union[ServerRequest, Mapping[str, Any], Any]) -> str:
    raw = _get(value, "kind", _get(value, "type", None))
    if raw is None:
        raise ValueError("request is missing a kind/type discriminator")
    return _enum_name(raw)


def _get(value: Union[Mapping[str, Any], Any], key: str, default: Any = ...):
    if isinstance(value, Mapping):
        if default is ...:
            return value[key]
        return value.get(key, default)
    if default is ...:
        return getattr(value, key)
    return getattr(value, key, default)


def _enum_name(value: Any) -> str:
    if isinstance(value, Enum):
        return str(value.value)
    text = str(value)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text


def _assessment_status(value: Any) -> GuardianAssessmentStatus:
    name = _enum_name(value).replace("-", "_")
    aliases = {
        "InProgress": GuardianAssessmentStatus.IN_PROGRESS,
        "Approved": GuardianAssessmentStatus.APPROVED,
        "Denied": GuardianAssessmentStatus.DENIED,
        "TimedOut": GuardianAssessmentStatus.TIMED_OUT,
        "Aborted": GuardianAssessmentStatus.ABORTED,
    }
    if name in aliases:
        return aliases[name]
    return GuardianAssessmentStatus(name.lower())


def _optional_enum(value: Optional[Any], enum_type: Type[Enum]) -> Optional[Any]:
    if value is None:
        return None
    return enum_type(_enum_name(value).lower())


def _decision_source(value: Any) -> GuardianAssessmentDecisionSource:
    return GuardianAssessmentDecisionSource(_enum_name(value).lower())


def _guardian_action(value: Any) -> GuardianAssessmentAction:
    if isinstance(value, GuardianAssessmentAction):
        return value
    data = _as_dict(value)
    raw_type = data.pop("kind", data.get("type", data.pop("variant", "")))
    action_type = _enum_name(raw_type).replace("-", "_")
    aliases = {
        "Command": "command",
        "Execve": "execve",
        "ApplyPatch": "apply_patch",
        "NetworkAccess": "network_access",
        "McpToolCall": "mcp_tool_call",
        "RequestPermissions": "request_permissions",
    }
    data["type"] = aliases.get(action_type, action_type.lower())
    if "source" in data and data["source"] is not None:
        data["source"] = _enum_name(data["source"]).lower()
    for camel, snake in (
        ("toolName", "tool_name"),
        ("connectorId", "connector_id"),
        ("connectorName", "connector_name"),
        ("toolTitle", "tool_title"),
    ):
        if camel in data and snake not in data:
            data[snake] = data.pop(camel)
    permissions = data.get("permissions")
    to_mapping = getattr(permissions, "to_mapping", None)
    if callable(to_mapping):
        data["permissions"] = to_mapping()
    return GuardianAssessmentAction.from_mapping(data)


def _call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        raise AttributeError(f"protocol request target does not implement {method_name}()")
    return method(*args)
