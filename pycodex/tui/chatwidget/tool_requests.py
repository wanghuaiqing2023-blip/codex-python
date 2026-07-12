"""Semantic Python port of Rust ``codex-tui::chatwidget::tool_requests``.

Upstream source: ``codex/codex-rs/tui/src/chatwidget/tool_requests.rs``.

This module owns interactive approval, permission, elicitation, guardian, and
user-input request routing. Python records bottom-pane and notification effects
as semantic values instead of constructing concrete ratatui/app-server objects.
"""

from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from .._porting import RustTuiModule
from ...protocol.approvals import (
    ApplyPatchApprovalRequestEvent,
    ExecApprovalRequestEvent,
)
from ...protocol.request_permissions import RequestPermissionsEvent
from ...app_server_protocol.item import ToolRequestUserInputParams, ToolRequestUserInputQuestion
from ...app_server_protocol.mcp import McpServerElicitationRequestParams
from ..auto_review_denials import RecentAutoReviewDenials
from ..history_cell.approvals import (
    ApprovalDecisionActor,
    ApprovalDecisionSubject,
    ReviewDecision,
    new_approval_decision_cell,
    new_guardian_approved_action_request,
    new_guardian_denied_action_request,
    new_guardian_denied_patch_request,
    new_guardian_timed_out_action_request,
    new_guardian_timed_out_patch_request,
)
from .status_state import PendingGuardianReviewStatus, StatusIndicatorState
from .notifications import Notification
from ..bottom_pane.mcp_server_elicitation import McpServerElicitationFormRequest
from ..bottom_pane.app_link_view import AppLinkViewParams

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::tool_requests",
    source="codex/codex-rs/tui/src/chatwidget/tool_requests.rs",
)


class GuardianAssessmentStatus(Enum):
    IN_PROGRESS = "InProgress"
    APPROVED = "Approved"
    TIMED_OUT = "TimedOut"
    DENIED = "Denied"
    OTHER = "Other"


class GuardianAssessmentActionKind(Enum):
    COMMAND = "Command"
    EXECVE = "Execve"
    APPLY_PATCH = "ApplyPatch"
    NETWORK_ACCESS = "NetworkAccess"
    MCP_TOOL_CALL = "McpToolCall"
    REQUEST_PERMISSIONS = "RequestPermissions"


@dataclass(frozen=True)
class GuardianAssessmentAction:
    kind: GuardianAssessmentActionKind
    command: Optional[str] = None
    program: Optional[str] = None
    argv: Tuple[str, ...] = ()
    files: Tuple[Path, ...] = ()
    target: Optional[str] = None
    server: Optional[str] = None
    tool_name: Optional[str] = None
    connector_name: Optional[str] = None
    reason: Optional[str] = None


@dataclass(frozen=True)
class GuardianAssessmentEvent:
    id: str
    status: GuardianAssessmentStatus
    action: GuardianAssessmentAction


ElicitationParams = McpServerElicitationRequestParams
UserInputQuestion = ToolRequestUserInputQuestion


@dataclass
class DeferredToolRequestQueue:
    exec_approvals: List[ExecApprovalRequestEvent] = field(default_factory=list)
    apply_patch_approvals: List[ApplyPatchApprovalRequestEvent] = field(default_factory=list)
    elicitations: List[Tuple[str, ElicitationParams]] = field(default_factory=list)
    user_inputs: List[ToolRequestUserInputParams] = field(default_factory=list)
    permission_requests: List[RequestPermissionsEvent] = field(default_factory=list)

    def push_exec_approval(self, ev: ExecApprovalRequestEvent) -> None:
        self.exec_approvals.append(ev)

    def push_apply_patch_approval(self, ev: ApplyPatchApprovalRequestEvent) -> None:
        self.apply_patch_approvals.append(ev)

    def push_elicitation(self, request_id: str, params: ElicitationParams) -> None:
        self.elicitations.append((request_id, params))

    def push_user_input(self, ev: ToolRequestUserInputParams) -> None:
        self.user_inputs.append(ev)

    def push_request_permissions(self, ev: RequestPermissionsEvent) -> None:
        self.permission_requests.append(ev)


@dataclass(frozen=True)
class ApprovalRequestPlan:
    kind: str
    data: Dict[str, Any]


@dataclass
class ToolRequestsModel:
    cwd: Path = Path(".")
    thread_id: str = ""
    defer_items: bool = False
    pending_guardian_review_status: PendingGuardianReviewStatus = field(
        default_factory=PendingGuardianReviewStatus
    )
    current_status_kind: str = "working"
    deferred_queue: DeferredToolRequestQueue = field(default_factory=DeferredToolRequestQueue)
    notifications: List[Notification] = field(default_factory=list)
    approval_requests: List[ApprovalRequestPlan] = field(default_factory=list)
    elicitation_forms: List[Any] = field(default_factory=list)
    app_link_views: List[Any] = field(default_factory=list)
    declined_elicitations: List[Tuple[str, str]] = field(default_factory=list)
    user_input_requests: List[ToolRequestUserInputParams] = field(default_factory=list)
    boxed_history: List[Any] = field(default_factory=list)
    recent_auto_review_denials: RecentAutoReviewDenials = field(default_factory=RecentAutoReviewDenials)
    ambient_pet_notifications: List[str] = field(default_factory=list)
    status_updates: List[Dict[str, Any]] = field(default_factory=list)
    status_headers: List[str] = field(default_factory=list)
    approval_request_sink: Optional[Callable[[ApprovalRequestPlan], Any]] = None
    history_sink: Optional[Callable[[Any], Any]] = None
    status_sink: Optional[Callable[[StatusIndicatorState], Any]] = None
    status_header_sink: Optional[Callable[[str], Any]] = None
    redraw_sink: Optional[Callable[[], Any]] = None
    notification_sink: Optional[Callable[[Notification], Any]] = None
    user_input_request_sink: Optional[Callable[[ToolRequestUserInputParams], Any]] = None
    mcp_form_request_sink: Optional[Callable[[McpServerElicitationFormRequest], Any]] = None
    app_link_view_sink: Optional[Callable[[AppLinkViewParams], Any]] = None
    elicitation_resolution_sink: Optional[Callable[[str, str, str], Any]] = None
    answer_stream_flushes: int = 0
    redraw_requests: int = 0
    status_indicator_ensures: int = 0
    interrupt_hint_visible: bool = False

    def on_exec_approval_request(self, id: str, ev: ExecApprovalRequestEvent) -> None:
        self.defer_or_handle(
            lambda q: q.push_exec_approval(ev),
            lambda s: s.handle_exec_approval_now(ev),
        )

    def on_apply_patch_approval_request(
        self,
        id: str,
        ev: ApplyPatchApprovalRequestEvent,
    ) -> None:
        self.defer_or_handle(
            lambda q: q.push_apply_patch_approval(ev),
            lambda s: s.handle_apply_patch_approval_now(ev),
        )

    def on_guardian_assessment(self, ev: GuardianAssessmentEvent) -> None:
        detail = guardian_action_summary(ev.action)
        status_name = _enum_value(ev.status)
        if status_name == "InProgress" and detail is not None:
            self.status_indicator_ensures += 1
            self.interrupt_hint_visible = True
            self.pending_guardian_review_status.start_or_update(ev.id, detail)
            status = self.pending_guardian_review_status.status_indicator_state()
            if status is not None:
                self.set_status(status)
            self.request_redraw()
            return

        if self.pending_guardian_review_status.finish(ev.id):
            status = self.pending_guardian_review_status.status_indicator_state()
            if status is not None:
                self.set_status(status)
            elif self.current_status_kind == "guardian_review":
                self.set_status_header("Working")
        elif self.pending_guardian_review_status.is_empty() and self.current_status_kind == "guardian_review":
            self.set_status_header("Working")

        if status_name == "Approved":
            self.add_boxed_history(guardian_terminal_cell(ev, "Approved"))
            self.request_redraw()
        elif status_name == "TimedOut":
            self.add_boxed_history(guardian_terminal_cell(ev, "TimedOut"))
            self.request_redraw()
        elif status_name == "Denied":
            self.recent_auto_review_denials.push(ev)
            self.add_boxed_history(guardian_terminal_cell(ev, "Denied"))
            self.request_redraw()

    def on_elicitation_request(self, request_id: str, params: McpServerElicitationRequestParams) -> None:
        self.defer_or_handle(
            lambda q: q.push_elicitation(request_id, params),
            lambda s: s.handle_elicitation_request_now(request_id, params),
        )

    def on_request_user_input(self, ev: ToolRequestUserInputParams) -> None:
        self.defer_or_handle(
            lambda q: q.push_user_input(ev),
            lambda s: s.handle_request_user_input_now(ev),
        )

    def on_request_permissions(self, ev: RequestPermissionsEvent) -> None:
        self.defer_or_handle(
            lambda q: q.push_request_permissions(ev),
            lambda s: s.handle_request_permissions_now(ev),
        )

    def handle_exec_approval_now(self, ev: ExecApprovalRequestEvent) -> None:
        self.flush_answer_stream_with_separator()
        command = shell_join(ev.command)
        self.notify(Notification.exec_approval_requested(command))
        self.push_approval_request(
            ApprovalRequestPlan(
                "exec",
                {
                    "thread_id": self.thread_id,
                    "id": ev.effective_approval_id(),
                    "command": ev.command,
                    "reason": ev.reason,
                    "available_decisions": ev.effective_available_decisions(),
                    "network_approval_context": ev.network_approval_context,
                    "additional_permissions": ev.additional_permissions,
                },
            )
        )

    def handle_apply_patch_approval_now(self, ev: ApplyPatchApprovalRequestEvent) -> None:
        self.flush_answer_stream_with_separator()
        self.push_approval_request(
            ApprovalRequestPlan(
                "apply_patch",
                {
                    "thread_id": self.thread_id,
                    "id": ev.call_id,
                    "reason": ev.reason,
                    "changes": ev.changes,
                    "cwd": self.cwd,
                },
            )
        )
        self.notify(
            Notification.edit_approval_requested(self.cwd, list(ev.changes.keys()))
        )

    def handle_elicitation_request_now(self, request_id: str, params: McpServerElicitationRequestParams) -> None:
        self.flush_answer_stream_with_separator()
        self.notify(Notification.elicitation_requested(params.server_name))
        request = params.request
        if request.mode == "url":
            app_link = AppLinkViewParams.from_url_app_server_request(
                params.thread_id or self.thread_id,
                params.server_name,
                request_id,
                request,
            )
            if app_link is not None:
                self.open_app_link_view(app_link)
            else:
                self.declined_elicitations.append((params.server_name, request_id))
                if self.elicitation_resolution_sink is not None:
                    self.elicitation_resolution_sink(params.server_name, request_id, "Decline")
        else:
            form = McpServerElicitationFormRequest.from_parts(
                thread_id=params.thread_id or self.thread_id,
                server_name=params.server_name,
                request_id=str(request_id),
                message=request.message,
                schema=None if request.requested_schema is None else request.requested_schema.to_mapping(),
                meta=request.meta if isinstance(request.meta, Mapping) else None,
            )
            if form is not None:
                self.push_mcp_server_elicitation_request(form)
            else:
                self.push_approval_request(
                    ApprovalRequestPlan(
                        "mcp_elicitation",
                        {
                            "thread_id": params.thread_id or self.thread_id,
                            "server_name": params.server_name,
                            "request_id": request_id,
                            "message": request.message,
                        },
                    )
                )
    def handle_request_user_input_now(self, ev: ToolRequestUserInputParams) -> None:
        self.flush_answer_stream_with_separator()
        count = len(ev.questions)
        summary = user_input_request_summary(ev.questions)
        if count == 1 and summary:
            title = summary
        elif count == 1:
            title = "Question requested"
        else:
            title = f"{count} questions requested"
        self.notify(Notification.plan_mode_prompt(title))
        self.user_input_requests.append(ev)
        if self.user_input_request_sink is not None:
            self.user_input_request_sink(ev)
        self.set_ambient_pet_notification("Waiting")
        self.request_redraw()

    def handle_request_permissions_now(self, ev: RequestPermissionsEvent) -> None:
        self.flush_answer_stream_with_separator()
        self.push_approval_request(
            ApprovalRequestPlan(
                "permissions",
                {
                    "thread_id": self.thread_id,
                    "call_id": ev.call_id,
                    "reason": ev.reason,
                    "permissions": ev.permissions,
                },
            )
        )

    def push_approval_request(self, request: ApprovalRequestPlan) -> None:
        self.approval_requests.append(request)
        if self.approval_request_sink is not None:
            self.approval_request_sink(request)
        self.set_ambient_pet_notification("Waiting")
        self.request_redraw()

    def push_mcp_server_elicitation_request(self, request: McpServerElicitationFormRequest) -> None:
        self.elicitation_forms.append(request)
        if self.mcp_form_request_sink is not None:
            self.mcp_form_request_sink(request)
        self.set_ambient_pet_notification("Waiting")
        self.request_redraw()

    def open_app_link_view(self, params: Any) -> None:
        self.app_link_views.append(params)
        if self.app_link_view_sink is not None:
            self.app_link_view_sink(params)

    def defer_or_handle(self, defer, handle) -> None:
        if self.defer_items:
            defer(self.deferred_queue)
        else:
            handle(self)

    def flush_answer_stream_with_separator(self) -> None:
        self.answer_stream_flushes += 1

    def notify(self, notification: Notification) -> None:
        self.notifications.append(notification)
        if self.notification_sink is not None:
            self.notification_sink(notification)

    def set_ambient_pet_notification(self, kind: str) -> None:
        self.ambient_pet_notifications.append(kind)

    def request_redraw(self) -> None:
        self.redraw_requests += 1
        if self.redraw_sink is not None:
            self.redraw_sink()

    def set_status(self, status: StatusIndicatorState) -> None:
        self.current_status_kind = "guardian_review"
        self.status_updates.append(
            {
                "header": status.header,
                "details": status.details,
                "details_max_lines": status.details_max_lines,
            }
        )
        if self.status_sink is not None:
            self.status_sink(status)

    def set_status_header(self, header: str) -> None:
        self.current_status_kind = "working"
        self.status_headers.append(header)
        if self.status_header_sink is not None:
            self.status_header_sink(header)

    def add_boxed_history(self, cell: Any) -> None:
        self.boxed_history.append(cell)
        if self.history_sink is not None:
            self.history_sink(cell)


def permission_request_summary(subject: str, reason: Optional[str]) -> str:
    reason = reason.strip() if reason else ""
    return f"{subject}: {reason}" if reason else subject


def guardian_action_summary(action: GuardianAssessmentAction | Mapping[str, Any] | Any) -> Optional[str]:
    kind = _action_kind(action)
    if kind == "Command":
        return str(_field(action, "command", "") or "")
    if kind == "Execve":
        command = tuple(_field(action, "argv", ()) or ()) or ((str(_field(action, "program", "") or "")),)
        return shell_join(command)
    if kind == "ApplyPatch":
        files = tuple(_field(action, "files", ()) or ())
        if len(files) == 1:
            return f"apply_patch touching {files[0]}"
        return f"apply_patch touching {len(files)} files"
    if kind == "NetworkAccess":
        return f"network access to {_field(action, 'target', '')}"
    if kind == "McpToolCall":
        label = _field(action, "connector_name", None) or _field(action, "connectorName", None) or _field(action, "server", "")
        tool_name = _field(action, "tool_name", None) or _field(action, "toolName", "")
        return f"MCP {tool_name} on {label}"
    if kind == "RequestPermissions":
        return permission_request_summary("permission request", _field(action, "reason", None))
    return None


def guardian_command(action: GuardianAssessmentAction | Mapping[str, Any] | Any) -> Optional[Tuple[str, ...]]:
    kind = _action_kind(action)
    if kind == "Command":
        command_text = str(_field(action, "command", "") or "")
        if not command_text:
            return None
        split = shlex.split(command_text)
        return tuple(split or [command_text])
    if kind == "Execve":
        command = tuple(_field(action, "argv", ()) or ()) or ((str(_field(action, "program", "") or "")),)
        command = tuple(part for part in command if part)
        return command or None
    return None


def guardian_terminal_cell(ev: GuardianAssessmentEvent | Any, decision: str) -> Any:
    command = guardian_command(ev.action)
    if command is not None:
        review_decision = {
            "Approved": ReviewDecision.approved(),
            "TimedOut": ReviewDecision.timed_out(),
            "Denied": ReviewDecision.denied(),
        }[decision]
        return new_approval_decision_cell(
            ApprovalDecisionSubject.command_subject(command),
            review_decision,
            ApprovalDecisionActor.Guardian,
        )
    action = ev.action
    kind = _action_kind(action)
    if kind == "ApplyPatch":
        files = tuple(str(path) for path in (_field(action, "files", ()) or ()))
        if decision == "Denied":
            return new_guardian_denied_patch_request(files)
        if decision == "TimedOut":
            return new_guardian_timed_out_patch_request(files)
    summary = guardian_terminal_summary(action, decision)
    if decision == "Approved":
        return new_guardian_approved_action_request(summary)
    if decision == "TimedOut":
        return new_guardian_timed_out_action_request(summary)
    return new_guardian_denied_action_request(summary)


def guardian_terminal_summary(action: GuardianAssessmentAction | Mapping[str, Any] | Any, decision: str) -> str:
    kind = _action_kind(action)
    if kind == "ApplyPatch":
        return guardian_action_summary(action) or "apply_patch"
    if kind == "McpToolCall":
        if decision == "Approved":
            return guardian_action_summary(action) or ""
        server = _field(action, "server", "")
        tool_name = _field(action, "tool_name", None) or _field(action, "toolName", "")
        return f"codex could call MCP tool {server}.{tool_name}" if decision == "TimedOut" else f"codex to call MCP tool {server}.{tool_name}"
    if kind == "NetworkAccess":
        target = _field(action, "target", "")
        if decision == "Approved":
            return guardian_action_summary(action) or ""
        return f"codex could access {target}" if decision == "TimedOut" else f"codex to access {target}"
    if kind == "RequestPermissions":
        subject = {
            "Approved": "permission request",
            "TimedOut": "codex could request permissions",
            "Denied": "codex to request permissions",
        }[decision]
        return permission_request_summary(subject, _field(action, "reason", None))
    return guardian_action_summary(action) or "<unrenderable guardian action>"


def _field(value: Mapping[str, Any] | Any, name: str, default: Any = None) -> Any:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _action_kind(action: Mapping[str, Any] | Any) -> str:
    raw = _field(action, "kind", _field(action, "type", _field(action, "variant", "")))
    if isinstance(raw, Enum):
        raw = raw.value
    name = str(raw).rsplit(".", 1)[-1]
    aliases = {
        "command": "Command",
        "execve": "Execve",
        "apply_patch": "ApplyPatch",
        "applypatch": "ApplyPatch",
        "network_access": "NetworkAccess",
        "networkaccess": "NetworkAccess",
        "mcp_tool_call": "McpToolCall",
        "mcptoolcall": "McpToolCall",
        "request_permissions": "RequestPermissions",
        "requestpermissions": "RequestPermissions",
    }
    return aliases.get(name.replace("-", "_").lower(), name)


def _enum_value(value: Any) -> str:
    raw = getattr(value, "value", value)
    name = str(raw).rsplit(".", 1)[-1]
    aliases = {
        "in_progress": "InProgress",
        "approved": "Approved",
        "denied": "Denied",
        "timed_out": "TimedOut",
        "aborted": "Aborted",
    }
    return aliases.get(name.lower(), name)


def user_input_request_summary(questions: Tuple[UserInputQuestion, ...]) -> Optional[str]:
    if not questions:
        return None
    first = questions[0]
    summary = first.header.strip() or first.question.strip()
    if not summary:
        return None
    return summary[:30]


def shell_join(command: Tuple[str, ...]) -> str:
    return shlex.join(command) if command else ""


__all__ = [
    "ApplyPatchApprovalRequestEvent",
    "ApprovalRequestPlan",
    "DeferredToolRequestQueue",
    "ElicitationParams",
    "ExecApprovalRequestEvent",
    "GuardianAssessmentAction",
    "GuardianAssessmentActionKind",
    "GuardianAssessmentEvent",
    "GuardianAssessmentStatus",
    "RUST_MODULE",
    "RequestPermissionsEvent",
    "ToolRequestUserInputParams",
    "ToolRequestsModel",
    "UserInputQuestion",
    "guardian_action_summary",
    "guardian_command",
    "guardian_terminal_cell",
    "permission_request_summary",
    "shell_join",
    "user_input_request_summary",
]
