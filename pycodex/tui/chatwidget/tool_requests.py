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
from typing import Any, Dict, List, Optional, Tuple

from .._porting import RustTuiModule

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


@dataclass(frozen=True)
class ExecApprovalRequestEvent:
    command: Tuple[str, ...]
    approval_id: Optional[str] = None
    reason: Optional[str] = None
    available_decisions: Tuple[str, ...] = ()
    network_approval_context: Optional[Any] = None
    additional_permissions: Optional[Any] = None

    def effective_approval_id(self) -> str:
        return self.approval_id or ""

    def effective_available_decisions(self) -> Tuple[str, ...]:
        return self.available_decisions


@dataclass(frozen=True)
class ApplyPatchApprovalRequestEvent:
    call_id: str
    changes: Dict[Path, Any]
    reason: Optional[str] = None


@dataclass(frozen=True)
class ElicitationParams:
    thread_id: str
    server_name: str
    request: Any
    route: str = "approval"
    message: str = ""


@dataclass(frozen=True)
class UserInputQuestion:
    header: str = ""
    question: str = ""


@dataclass(frozen=True)
class ToolRequestUserInputParams:
    questions: Tuple[UserInputQuestion, ...]


@dataclass(frozen=True)
class RequestPermissionsEvent:
    call_id: str
    reason: Optional[str]
    permissions: Any


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


@dataclass(frozen=True)
class NotificationPlan:
    kind: str
    data: Dict[str, Any]


@dataclass(frozen=True)
class HistoryCellPlan:
    kind: str
    data: Dict[str, Any]


@dataclass
class PendingGuardianReviewStatus:
    pending: Dict[str, str] = field(default_factory=dict)

    def start_or_update(self, id: str, detail: str) -> None:
        self.pending[id] = detail

    def finish(self, id: str) -> bool:
        return self.pending.pop(id, None) is not None

    def is_empty(self) -> bool:
        return not self.pending

    def status_indicator_state(self) -> Dict[str, Any] | None:
        if not self.pending:
            return None
        details = list(self.pending.values())
        return {
            "header": "Reviewing",
            "details": details,
            "details_max_lines": len(details),
        }


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
    notifications: List[NotificationPlan] = field(default_factory=list)
    approval_requests: List[ApprovalRequestPlan] = field(default_factory=list)
    elicitation_forms: List[Any] = field(default_factory=list)
    app_link_views: List[Any] = field(default_factory=list)
    declined_elicitations: List[Tuple[str, str]] = field(default_factory=list)
    user_input_requests: List[ToolRequestUserInputParams] = field(default_factory=list)
    boxed_history: List[HistoryCellPlan] = field(default_factory=list)
    recent_auto_review_denials: List[GuardianAssessmentEvent] = field(default_factory=list)
    ambient_pet_notifications: List[str] = field(default_factory=list)
    status_updates: List[Dict[str, Any]] = field(default_factory=list)
    status_headers: List[str] = field(default_factory=list)
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
        if ev.status is GuardianAssessmentStatus.IN_PROGRESS and detail is not None:
            self.status_indicator_ensures += 1
            self.interrupt_hint_visible = True
            self.pending_guardian_review_status.start_or_update(ev.id, detail)
            status = self.pending_guardian_review_status.status_indicator_state()
            if status is not None:
                self.set_status(status["header"], status["details"], status["details_max_lines"])
            self.request_redraw()
            return

        if self.pending_guardian_review_status.finish(ev.id):
            status = self.pending_guardian_review_status.status_indicator_state()
            if status is not None:
                self.set_status(status["header"], status["details"], status["details_max_lines"])
            elif self.current_status_kind == "guardian_review":
                self.set_status_header("Working")
        elif self.pending_guardian_review_status.is_empty() and self.current_status_kind == "guardian_review":
            self.set_status_header("Working")

        if ev.status is GuardianAssessmentStatus.APPROVED:
            self.add_boxed_history(guardian_terminal_cell(ev, "Approved"))
            self.request_redraw()
        elif ev.status is GuardianAssessmentStatus.TIMED_OUT:
            self.add_boxed_history(guardian_terminal_cell(ev, "TimedOut"))
            self.request_redraw()
        elif ev.status is GuardianAssessmentStatus.DENIED:
            self.recent_auto_review_denials.append(ev)
            self.add_boxed_history(guardian_terminal_cell(ev, "Denied"))
            self.request_redraw()

    def on_elicitation_request(self, request_id: str, params: ElicitationParams) -> None:
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
        self.notify(NotificationPlan("exec_approval_requested", {"command": command}))
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
            NotificationPlan(
                "edit_approval_requested",
                {"cwd": self.cwd, "changes": list(ev.changes.keys())},
            )
        )

    def handle_elicitation_request_now(self, request_id: str, params: ElicitationParams) -> None:
        self.flush_answer_stream_with_separator()
        self.notify(NotificationPlan("elicitation_requested", {"server_name": params.server_name}))
        if params.route == "app_link":
            self.open_app_link_view({"request_id": request_id, "server_name": params.server_name})
        elif params.route == "form":
            self.push_mcp_server_elicitation_request(
                {"request_id": request_id, "server_name": params.server_name, "request": params.request}
            )
        elif params.route == "url_decline":
            self.declined_elicitations.append((params.server_name, request_id))
        else:
            self.push_approval_request(
                ApprovalRequestPlan(
                    "mcp_elicitation",
                    {
                        "thread_id": params.thread_id or self.thread_id,
                        "server_name": params.server_name,
                        "request_id": request_id,
                        "message": params.message,
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
        self.notify(NotificationPlan("plan_mode_prompt", {"title": title}))
        self.user_input_requests.append(ev)
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
        self.set_ambient_pet_notification("Waiting")
        self.request_redraw()

    def push_mcp_server_elicitation_request(self, request: Any) -> None:
        self.elicitation_forms.append(request)
        self.set_ambient_pet_notification("Waiting")
        self.request_redraw()

    def open_app_link_view(self, params: Any) -> None:
        self.app_link_views.append(params)

    def defer_or_handle(self, defer, handle) -> None:
        if self.defer_items:
            defer(self.deferred_queue)
        else:
            handle(self)

    def flush_answer_stream_with_separator(self) -> None:
        self.answer_stream_flushes += 1

    def notify(self, notification: NotificationPlan) -> None:
        self.notifications.append(notification)

    def set_ambient_pet_notification(self, kind: str) -> None:
        self.ambient_pet_notifications.append(kind)

    def request_redraw(self) -> None:
        self.redraw_requests += 1

    def set_status(self, header: str, details: List[str], details_max_lines: int) -> None:
        self.current_status_kind = "guardian_review"
        self.status_updates.append(
            {"header": header, "details": details, "details_max_lines": details_max_lines}
        )

    def set_status_header(self, header: str) -> None:
        self.current_status_kind = "working"
        self.status_headers.append(header)

    def add_boxed_history(self, cell: HistoryCellPlan) -> None:
        self.boxed_history.append(cell)


def permission_request_summary(subject: str, reason: Optional[str]) -> str:
    reason = reason.strip() if reason else ""
    return f"{subject}: {reason}" if reason else subject


def guardian_action_summary(action: GuardianAssessmentAction) -> Optional[str]:
    if action.kind is GuardianAssessmentActionKind.COMMAND:
        return action.command or ""
    if action.kind is GuardianAssessmentActionKind.EXECVE:
        command = action.argv or ((action.program or ""),)
        return shell_join(command)
    if action.kind is GuardianAssessmentActionKind.APPLY_PATCH:
        if len(action.files) == 1:
            return f"apply_patch touching {action.files[0]}"
        return f"apply_patch touching {len(action.files)} files"
    if action.kind is GuardianAssessmentActionKind.NETWORK_ACCESS:
        return f"network access to {action.target}"
    if action.kind is GuardianAssessmentActionKind.MCP_TOOL_CALL:
        label = action.connector_name or action.server or ""
        return f"MCP {action.tool_name} on {label}"
    if action.kind is GuardianAssessmentActionKind.REQUEST_PERMISSIONS:
        return permission_request_summary("permission request", action.reason)
    return None


def guardian_command(action: GuardianAssessmentAction) -> Optional[Tuple[str, ...]]:
    if action.kind is GuardianAssessmentActionKind.COMMAND:
        if not action.command:
            return None
        split = shlex.split(action.command)
        return tuple(split or [action.command])
    if action.kind is GuardianAssessmentActionKind.EXECVE:
        command = action.argv or ((action.program or ""),)
        command = tuple(part for part in command if part)
        return command or None
    return None


def guardian_terminal_cell(ev: GuardianAssessmentEvent, decision: str) -> HistoryCellPlan:
    command = guardian_command(ev.action)
    if command is not None:
        return HistoryCellPlan(
            "guardian_command_decision",
            {"command": command, "decision": decision},
        )
    summary = guardian_terminal_summary(ev.action, decision)
    return HistoryCellPlan(
        "guardian_action_decision",
        {"summary": summary, "decision": decision},
    )


def guardian_terminal_summary(action: GuardianAssessmentAction, decision: str) -> str:
    prefix = {
        "Approved": "",
        "TimedOut": "codex could ",
        "Denied": "codex to ",
    }[decision]
    if action.kind is GuardianAssessmentActionKind.APPLY_PATCH:
        if decision == "Approved":
            return guardian_action_summary(action) or "apply_patch"
        return f"{prefix}apply_patch touching {len(action.files)} files"
    if action.kind is GuardianAssessmentActionKind.MCP_TOOL_CALL:
        if decision == "Approved":
            return guardian_action_summary(action) or ""
        verb = "call MCP tool"
        return f"{prefix}{verb} {action.server}.{action.tool_name}"
    if action.kind is GuardianAssessmentActionKind.NETWORK_ACCESS:
        if decision == "Approved":
            return guardian_action_summary(action) or ""
        verb = "access"
        return f"{prefix}{verb} {action.target}"
    if action.kind is GuardianAssessmentActionKind.REQUEST_PERMISSIONS:
        subject = {
            "Approved": "permission request",
            "TimedOut": "codex could request permissions",
            "Denied": "codex to request permissions",
        }[decision]
        return permission_request_summary(subject, action.reason)
    return guardian_action_summary(action) or "<unrenderable guardian action>"


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
    "HistoryCellPlan",
    "NotificationPlan",
    "PendingGuardianReviewStatus",
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
