"""App-server request dispatch for chat-widget semantic models.

Rust ``codex-tui::chatwidget::protocol_requests`` translates app-server
requests and a few related notifications into focused ``ChatWidget`` flows.
This Python port keeps the same behavior boundary using lightweight DTOs and
widget callback hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Mapping, Protocol

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::protocol_requests", source="codex/codex-rs/tui/src/chatwidget/protocol_requests.rs")

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


class GuardianAssessmentStatus(str, Enum):
    IN_PROGRESS = "InProgress"
    APPROVED = "Approved"
    DENIED = "Denied"
    TIMED_OUT = "TimedOut"
    ABORTED = "Aborted"


class GuardianRiskLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class GuardianUserAuthorization(str, Enum):
    UNKNOWN = "Unknown"
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class GuardianAssessmentDecisionSource(str, Enum):
    AGENT = "Agent"


@dataclass(frozen=True)
class ServerRequest:
    kind: str
    id: str | None = None
    params: Any = None
    request_id: str | None = None


@dataclass(frozen=True)
class GuardianAssessmentEvent:
    id: str
    target_item_id: str | None
    turn_id: str
    started_at_ms: int
    completed_at_ms: int | None
    status: GuardianAssessmentStatus
    risk_level: GuardianRiskLevel | None
    user_authorization: GuardianUserAuthorization | None
    rationale: str | None
    decision_source: GuardianAssessmentDecisionSource | None
    action: Any


class ProtocolRequestsWidget(Protocol):
    config: Any


def handle_server_request(
    widget: Any,
    request: ServerRequest | Mapping[str, Any] | Any,
    replay_kind: Any | None = None,
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
        _call(widget, "on_elicitation_request", _get(request, "request_id", request_id), params)
    elif kind == "PermissionsRequestApproval":
        _call(widget, "on_request_permissions", request_permissions_from_params(params))
    elif kind == "ToolRequestUserInput":
        _call(widget, "on_request_user_input", params)
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
    review: Mapping[str, Any] | Any,
    completion: tuple[int, Any] | None,
    action: Any,
) -> GuardianAssessmentEvent:
    completed_at_ms = None
    decision_source = None
    if completion is not None:
        completed_at_ms, raw_source = completion
        decision_source = _decision_source(raw_source)

    event = GuardianAssessmentEvent(
        id=id,
        target_item_id=None,
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
        action=action,
    )
    _call(widget, "on_guardian_assessment", event)
    return event


def on_shutdown_complete(widget: Any) -> None:
    _call(widget, "request_immediate_exit")


def on_turn_diff(widget: Any, unified_diff: str) -> None:
    _call(widget, "refresh_status_line")


def on_deprecation_notice(widget: Any, summary: str, details: str | None) -> None:
    _call(widget, "add_to_history", {"kind": "deprecation_notice", "summary": summary, "details": details})
    _call(widget, "request_redraw")


def exec_approval_request_from_params(params: Any, fallback_cwd: Any) -> dict[str, Any]:
    data = _as_dict(params)
    data.setdefault("cwd", fallback_cwd)
    return data


def patch_approval_request_from_params(params: Any) -> dict[str, Any]:
    return _as_dict(params)


def request_permissions_from_params(params: Any) -> dict[str, Any]:
    return _as_dict(params)


def _as_dict(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    raise TypeError(f"cannot convert params to semantic request dict: {type(value).__name__}")


def _kind(value: ServerRequest | Mapping[str, Any] | Any) -> str:
    raw = _get(value, "kind", _get(value, "type", None))
    if raw is None:
        raise ValueError("request is missing a kind/type discriminator")
    return _enum_name(raw)


def _get(value: Mapping[str, Any] | Any, key: str, default: Any = ...):
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
    name = _enum_name(value)
    if name == "TimedOut":
        return GuardianAssessmentStatus.TIMED_OUT
    if name == "InProgress":
        return GuardianAssessmentStatus.IN_PROGRESS
    return GuardianAssessmentStatus(name)


def _optional_enum(value: Any | None, enum_type: type[Enum]) -> Any | None:
    if value is None:
        return None
    return enum_type(_enum_name(value))


def _decision_source(value: Any) -> GuardianAssessmentDecisionSource:
    return GuardianAssessmentDecisionSource(_enum_name(value))


def _call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        raise AttributeError(f"protocol request target does not implement {method_name}()")
    return method(*args)
