"""Semantic approval overlay for Rust ``bottom_pane/approval_overlay.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
import textwrap
from typing import Any, Callable, Dict, Iterable, List, Mapping, Optional, Tuple, Union

from .._porting import RustTuiModule
from ..app_event_sender import AppEventSender
from ..history_cell.approvals import (
    ApprovalDecisionActor,
    ApprovalDecisionSubject,
    ReviewDecision as HistoryReviewDecision,
    new_approval_decision_cell,
)
from ..history_cell.base import PlainHistoryCell
from ..line_truncation import Line
from ...protocol.request_permissions import (
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
)
from .bottom_pane_view import BottomPaneViewDefaults, CancellationEvent, ViewCompletion
from .list_selection_view import ListSelectionView, SelectionItem, SelectionViewParams
from .selection_popup_common import TerminalPopupLine
from ..keymap import RuntimeKeymap

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::approval_overlay",
    source="codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs",
    status="complete",
)


@dataclass(frozen=True)
class ApprovalRequest:
    kind: str
    thread_id: Any
    id: Optional[str] = None
    thread_label: Optional[str] = None
    command: List[str] = field(default_factory=list)
    reason: Optional[str] = None
    available_decisions: List[str] = field(default_factory=list)
    network_approval_context: Any = None
    additional_permissions: Any = None
    call_id: Optional[str] = None
    permissions: Any = None
    cwd: Optional[Path] = None
    changes: Dict[Path, Any] = field(default_factory=dict)
    server_name: Optional[str] = None
    request_id: Any = None
    message: Optional[str] = None

    @classmethod
    def Exec(cls, thread_id: Any, id: str, command: Iterable[str], **kwargs: Any) -> "ApprovalRequest":
        return cls(kind="Exec", thread_id=thread_id, id=id, command=list(command), **kwargs)

    @classmethod
    def Permissions(cls, thread_id: Any, call_id: str, permissions: Any, **kwargs: Any) -> "ApprovalRequest":
        return cls(kind="Permissions", thread_id=thread_id, call_id=call_id, permissions=permissions, **kwargs)

    @classmethod
    def ApplyPatch(cls, thread_id: Any, id: str, cwd: Union[str, Path], changes: Mapping[Any, Any], **kwargs: Any) -> "ApprovalRequest":
        return cls(
            kind="ApplyPatch",
            thread_id=thread_id,
            id=id,
            cwd=Path(cwd),
            changes={Path(path): change for path, change in changes.items()},
            **kwargs,
        )

    @classmethod
    def McpElicitation(cls, thread_id: Any, server_name: str, request_id: Any, message: str, **kwargs: Any) -> "ApprovalRequest":
        return cls(
            kind="McpElicitation",
            thread_id=thread_id,
            server_name=server_name,
            request_id=request_id,
            message=message,
            **kwargs,
        )

    def matches_resolved_request(self, request: Any) -> bool:
        req_kind = _get(request, "kind", _get(request, "type"))
        if self.kind == "Exec" and req_kind in {"ExecApproval", "exec"}:
            return self.id == _get(request, "id")
        if self.kind == "Permissions" and req_kind in {"PermissionsApproval", "permissions"}:
            return self.call_id == _get(request, "id")
        if self.kind == "ApplyPatch" and req_kind in {"FileChangeApproval", "patch"}:
            return self.id == _get(request, "id")
        if self.kind == "McpElicitation" and req_kind in {"McpElicitation", "mcp"}:
            return self.server_name == _get(request, "server_name") and self.request_id == _get(request, "request_id")
        return False


class ApprovalDecision(Enum):
    COMMAND = "Command"
    PERMISSIONS = "Permissions"
    FILE_CHANGE = "FileChange"
    MCP_ELICITATION = "McpElicitation"


class PermissionsDecision(Enum):
    GRANT_FOR_TURN = "GrantForTurn"
    GRANT_FOR_TURN_WITH_STRICT_AUTO_REVIEW = "GrantForTurnWithStrictAutoReview"
    GRANT_FOR_SESSION = "GrantForSession"
    DENY = "Deny"


@dataclass(frozen=True)
class ApprovalOption:
    label: str
    decision_kind: ApprovalDecision
    decision: Any
    shortcuts: Tuple[str, ...] = ()


@dataclass
class ApprovalKeymap:
    approve: Tuple[str, ...] = ("y",)
    approve_for_session: Tuple[str, ...] = ("a",)
    approve_for_prefix: Tuple[str, ...] = ("p",)
    deny: Tuple[str, ...] = ("d",)
    decline: Tuple[str, ...] = ("Esc", "n")
    strict_auto_review: Tuple[str, ...] = ("r",)
    cancel: Tuple[str, ...] = ("c",)
    open_fullscreen: Tuple[str, ...] = ("ctrl+shift+a",)
    open_thread: Tuple[str, ...] = ("o",)


@dataclass
class ApprovalOverlay(BottomPaneViewDefaults):
    current_request: Optional[ApprovalRequest]
    app_event_tx: Any = None
    features: Any = None
    approval_keymap: ApprovalKeymap = field(default_factory=ApprovalKeymap)
    list_keymap: Any = None
    queue: List[ApprovalRequest] = field(default_factory=list)
    options: List[ApprovalOption] = field(default_factory=list)
    current_complete: bool = False
    done: bool = False
    emitted_events: List[Dict[str, Any]] = field(default_factory=list)
    selection_view: Optional[ListSelectionView] = None
    completion_value: Optional[ViewCompletion] = None

    @classmethod
    def new(
        cls,
        request: ApprovalRequest,
        app_event_tx: Any = None,
        features: Any = None,
        approval_keymap: Optional[ApprovalKeymap] = None,
        list_keymap: Any = None,
    ) -> "ApprovalOverlay":
        view = cls(
            current_request=None,
            app_event_tx=app_event_tx,
            features=features,
            approval_keymap=approval_keymap or ApprovalKeymap(),
            list_keymap=list_keymap,
        )
        view.set_current(request)
        return view

    def enqueue_request(self, req: ApprovalRequest) -> None:
        self.queue.append(req)

    def dismiss_resolved_request(self, request: Any) -> bool:
        before = len(self.queue)
        self.queue = [queued for queued in self.queue if not queued.matches_resolved_request(request)]
        if self.current_request is not None and self.current_request.matches_resolved_request(request):
            self.current_complete = True
            self.advance_queue()
            return True
        return len(self.queue) != before

    def set_current(self, request: ApprovalRequest) -> None:
        self.current_complete = False
        self.current_request = request
        self.options, params = self.build_options(
            request,
            build_header(request),
            self.features,
            self.approval_keymap,
            self.list_keymap,
        )
        params.items = [
            SelectionItem(
                name=option.label,
                display_shortcut=_binding_label(option.shortcuts[0]) if option.shortcuts else None,
                actions=[lambda _tx, idx=idx: self.apply_selection(idx)],
            )
            for idx, option in enumerate(self.options)
        ]
        self.selection_view = ListSelectionView.new(params, self.app_event_tx, self.list_keymap)

    @staticmethod
    def build_options(
        request: ApprovalRequest,
        header: Any = None,
        features: Any = None,
        approval_keymap: Optional[ApprovalKeymap] = None,
        list_keymap: Any = None,
    ) -> Tuple[List[ApprovalOption], SelectionViewParams]:
        del features
        keymap = approval_keymap or ApprovalKeymap()
        if request.kind == "Exec":
            options = exec_options(
                request.available_decisions,
                request.network_approval_context,
                request.additional_permissions,
                keymap,
            )
            title = (
                f"Do you want to approve network access to \"{_get(request.network_approval_context, 'host')}\"?"
                if request.network_approval_context is not None
                else "Would you like to run the following command?"
            )
        elif request.kind == "Permissions":
            options = permissions_options(keymap)
            title = "Would you like to grant these permissions?"
        elif request.kind == "ApplyPatch":
            options = patch_options(keymap)
            title = "Would you like to make the following edits?"
        else:
            options = elicitation_options(keymap)
            title = f"{request.server_name} needs your approval."
        return options, SelectionViewParams(
            view_id="approval-overlay",
            header=[title, "", *(header or [])],
            footer_hint=approval_footer_hint(request, keymap, list_keymap),
            initial_selected_idx=0,
        )

    def apply_selection(self, actual_idx: int) -> None:
        if self.current_complete or self.current_request is None:
            return
        if actual_idx < 0 or actual_idx >= len(self.options):
            return
        option = self.options[actual_idx]
        request = self.current_request
        if request.kind == "Exec" and option.decision_kind is ApprovalDecision.COMMAND:
            self.handle_exec_decision(request.id or "", request.command, option.decision)
        elif request.kind == "Permissions" and option.decision_kind is ApprovalDecision.PERMISSIONS:
            self.handle_permissions_decision(request.call_id or "", request.permissions, option.decision)
        elif request.kind == "ApplyPatch" and option.decision_kind is ApprovalDecision.FILE_CHANGE:
            self.handle_patch_decision(request.id or "", option.decision)
        elif request.kind == "McpElicitation" and option.decision_kind is ApprovalDecision.MCP_ELICITATION:
            self.handle_elicitation_decision(request.server_name or "", request.request_id, option.decision)
        self.current_complete = True
        self.completion_value = ViewCompletion.ACCEPTED
        self.advance_queue()

    def handle_exec_decision(self, id: str, command: List[str], decision: str) -> None:
        request = self.current_request
        if request is not None and request.thread_label is None:
            if request.network_approval_context is not None:
                subject = ApprovalDecisionSubject.network_access(
                    network_approval_target(request.network_approval_context, command)
                )
            else:
                command_target = network_approval_command_target(command)
                subject = (
                    ApprovalDecisionSubject.network_access(command_target)
                    if command_target is not None
                    else ApprovalDecisionSubject.command_subject(command)
                )
            self._insert_history_cell(
                new_approval_decision_cell(
                    subject,
                    command_decision_to_review_decision(decision),
                    ApprovalDecisionActor.User,
                )
            )
        if isinstance(self.app_event_tx, AppEventSender):
            self.app_event_tx.exec_approval(
                None if request is None else request.thread_id,
                id,
                decision,
            )
            return
        self._emit(
            "ExecApproval",
            thread_id=None if request is None else request.thread_id,
            id=id,
            command=list(command),
            decision=decision,
        )

    def handle_permissions_decision(self, call_id: str, permissions: Any, decision: PermissionsDecision) -> None:
        scope = "Session" if decision is PermissionsDecision.GRANT_FOR_SESSION else "Turn"
        strict_auto_review = decision is PermissionsDecision.GRANT_FOR_TURN_WITH_STRICT_AUTO_REVIEW
        granted = {} if decision is PermissionsDecision.DENY else permissions
        request = self.current_request
        if request is not None and request.thread_label is None:
            if decision is PermissionsDecision.DENY:
                message = "You did not grant additional permissions"
            elif strict_auto_review:
                message = "You granted additional permissions with strict auto review"
            elif decision is PermissionsDecision.GRANT_FOR_SESSION:
                message = "You granted additional permissions for this session"
            else:
                message = "You granted additional permissions"
            self._insert_history_cell(PlainHistoryCell.new([Line.from_text(message)]))
        if isinstance(self.app_event_tx, AppEventSender):
            response_permissions = (
                RequestPermissionProfile()
                if decision is PermissionsDecision.DENY
                else permissions
            )
            self.app_event_tx.request_permissions_response(
                None if request is None else request.thread_id,
                call_id,
                RequestPermissionsResponse(
                    permissions=response_permissions,
                    scope=(
                        PermissionGrantScope.SESSION
                        if decision is PermissionsDecision.GRANT_FOR_SESSION
                        else PermissionGrantScope.TURN
                    ),
                    strict_auto_review=strict_auto_review,
                ),
            )
            return
        self._emit(
            "RequestPermissionsResponse",
            thread_id=None if request is None else request.thread_id,
            id=call_id,
            permissions=granted,
            scope=scope,
            strict_auto_review=strict_auto_review,
        )

    def handle_patch_decision(self, id: str, decision: str) -> None:
        request = self.current_request
        if isinstance(self.app_event_tx, AppEventSender):
            self.app_event_tx.patch_approval(
                None if request is None else request.thread_id,
                id,
                decision,
            )
            return
        self._emit("PatchApproval", thread_id=None if request is None else request.thread_id, id=id, decision=decision)

    def handle_elicitation_decision(self, server_name: str, request_id: Any, decision: str) -> None:
        request = self.current_request
        if isinstance(self.app_event_tx, AppEventSender):
            self.app_event_tx.resolve_elicitation(
                None if request is None else request.thread_id,
                server_name,
                request_id,
                decision,
                None,
                None,
            )
            return
        self._emit(
            "ResolveElicitation",
            thread_id=None if request is None else request.thread_id,
            server_name=server_name,
            request_id=request_id,
            decision=decision,
            content=None,
            meta=None,
        )

    def advance_queue(self) -> None:
        if self.queue:
            self.set_current(self.queue.pop())
        else:
            self.done = True

    def cancel_current_request(self) -> None:
        if self.done:
            return
        request = self.current_request
        if not self.current_complete and request is not None:
            if request.kind == "Exec":
                self.handle_exec_decision(request.id or "", request.command, "Cancel")
            elif request.kind == "Permissions":
                self.handle_permissions_decision(request.call_id or "", request.permissions, PermissionsDecision.DENY)
            elif request.kind == "ApplyPatch":
                self.handle_patch_decision(request.id or "", "Cancel")
            elif request.kind == "McpElicitation":
                self.handle_elicitation_decision(request.server_name or "", request.request_id, "Cancel")
        self.queue.clear()
        self.done = True
        self.completion_value = ViewCompletion.CANCELLED

    def try_handle_shortcut(self, key_event: Any) -> bool:
        key = _key_name(key_event)
        if any(_binding_matches(binding, key) for binding in self.approval_keymap.open_fullscreen) and self.current_request is not None:
            if isinstance(self.app_event_tx, AppEventSender):
                self.app_event_tx.full_screen_approval_request(self.current_request)
            else:
                self._emit("FullScreenApprovalRequest", request=self.current_request)
            return True
        if any(_binding_matches(binding, key) for binding in self.approval_keymap.open_thread) and self.current_request is not None and self.current_request.thread_label:
            if isinstance(self.app_event_tx, AppEventSender):
                self.app_event_tx.select_agent_thread(self.current_request.thread_id)
            else:
                self._emit("SelectAgentThread", thread_id=self.current_request.thread_id)
            return True
        for idx, option in enumerate(self.options):
            if any(_binding_matches(shortcut, key) for shortcut in option.shortcuts):
                self.apply_selection(idx)
                return True
        return False

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if self.current_request is not None and self.current_request.kind == "McpElicitation" and key == "esc":
            self.cancel_current_request()
            return
        if self.try_handle_shortcut(key_event):
            return
        if key in {"esc", "ctrl+c"}:
            self.cancel_current_request()
        elif self.selection_view is not None:
            self.selection_view.handle_key_event(key)

    def on_ctrl_c(self) -> CancellationEvent:
        self.cancel_current_request()
        return CancellationEvent.HANDLED

    def is_complete(self) -> bool:
        return self.done

    def completion(self) -> ViewCompletion | None:
        return self.completion_value

    def view_id(self) -> str | None:
        return "approval-overlay"

    def selected_index(self) -> int | None:
        return None if self.selection_view is None else self.selection_view.selected_index()

    def terminal_lines(self, *, width: int) -> List[TerminalPopupLine]:
        if self.selection_view is None:
            return []
        width = max(int(width), 1)
        header = _as_text_lines(self.selection_view.active_header())
        lines: List[TerminalPopupLine] = [TerminalPopupLine("", False)]
        for header_line in header:
            lines.extend(
                TerminalPopupLine(line, False)
                for line in _inset_wrap(header_line, width)
            )
        lines.append(TerminalPopupLine("", False))
        selected_idx = self.selection_view.selected_index()
        for idx, option in enumerate(self.options):
            selected = idx == selected_idx
            prefix = "›" if selected else " "
            shortcut = _first_binding_label(option.shortcuts)
            text = f"{prefix} {idx + 1}. {option.label}"
            if shortcut:
                text += f" ({shortcut})"
            lines.extend(
                TerminalPopupLine(line, selected)
                for line in _wrap_approval_option(text, width)
            )
        footer = self.selection_view.active_footer_hint()
        if footer is not None:
            lines.append(TerminalPopupLine("", False))
            for footer_line in _as_text_lines(footer):
                lines.extend(
                    TerminalPopupLine(line, False)
                    for line in _inset_wrap(footer_line, width)
                )
        return lines

    def try_consume_approval_request(self, request: ApprovalRequest) -> None:
        self.enqueue_request(request)
        return None

    def dismiss_app_server_request(self, request: Any) -> bool:
        return self.dismiss_resolved_request(request)

    def terminal_title_requires_action(self) -> bool:
        return not self.done

    def desired_height(self, width: int = 80) -> int:
        return len(self.terminal_lines(width=width))

    def render(self, area: Any = None, buf: Any = None) -> List[str]:
        del area
        width = 80 if area is None else _area_width(area)
        lines = [line.text for line in self.terminal_lines(width=max(width, 1))]
        if isinstance(buf, list):
            buf.extend(lines)
        return lines

    def cursor_pos(self, _area: Any = None) -> None:
        return None

    def _emit(self, event_type: str, **payload: Any) -> None:
        event = {"type": event_type, **payload}
        self.emitted_events.append(event)
        if hasattr(self.app_event_tx, "send"):
            self.app_event_tx.send(event)

    def _insert_history_cell(self, cell: Any) -> None:
        if isinstance(self.app_event_tx, AppEventSender):
            self.app_event_tx.insert_history_cell(cell)
            return
        self._emit("InsertHistoryCell", cell=cell)


def handle_key_event(view: ApprovalOverlay, key_event: Any) -> None:
    view.handle_key_event(key_event)


def on_ctrl_c(view: ApprovalOverlay) -> str:
    return view.on_ctrl_c()


def is_complete(view: ApprovalOverlay) -> bool:
    return view.is_complete()


def try_consume_approval_request(view: ApprovalOverlay) -> Optional[ApprovalRequest]:
    return view.current_request


def dismiss_app_server_request(view: ApprovalOverlay, request: Any) -> bool:
    return view.dismiss_app_server_request(request)


def terminal_title_requires_action(view: ApprovalOverlay) -> bool:
    return view.terminal_title_requires_action()


def desired_height(view: ApprovalOverlay, width: int = 80) -> int:
    return view.desired_height(width)


def render(view: ApprovalOverlay, area: Any = None, buf: Any = None) -> List[str]:
    return view.render(area, buf)


def cursor_pos(view: ApprovalOverlay, area: Any = None) -> None:
    return view.cursor_pos(area)


def approval_footer_hint(request: ApprovalRequest, approval_keymap: Optional[ApprovalKeymap] = None, list_keymap: Any = None) -> str:
    keymap = approval_keymap or ApprovalKeymap()
    runtime_list = list_keymap or RuntimeKeymap.built_in_defaults().list
    accept = _first_binding_label(getattr(runtime_list, "accept", ()))
    cancel = _first_binding_label(getattr(runtime_list, "cancel", ()))
    if accept and cancel:
        base = f"Press {accept} to confirm or {cancel} to cancel"
    elif accept:
        base = f"Press {accept} to confirm"
    elif cancel:
        base = f"Press {cancel} to cancel"
    else:
        base = ""
    if request.thread_label:
        open_thread = _first_binding_label(keymap.open_thread)
        if open_thread:
            return f"{base} or {open_thread} to open thread" if base else f"Press {open_thread} to open thread"
    return base


def network_approval_target(network_approval_context: Any, command: Iterable[str] = ()) -> str:
    host = _get(network_approval_context, "host")
    protocol = str(_get(network_approval_context, "protocol", "")).lower()
    if host:
        return f"{protocol}://{host}" if protocol and not str(host).startswith(f"{protocol}://") else str(host)
    return network_approval_command_target(command) or ""


def network_approval_command_target(command: Iterable[str]) -> Optional[str]:
    parts = list(command)
    if len(parts) >= 2 and parts[0] == "network-access":
        return parts[1]
    return None


def build_header(request: ApprovalRequest) -> List[str]:
    lines: List[str] = []
    if request.thread_label:
        lines.append(f"Thread: {request.thread_label}")
        lines.append("")
    if request.reason:
        lines.append(f"Reason: {request.reason}")
        if request.kind != "ApplyPatch":
            lines.append("")
    if request.kind == "Exec" and request.network_approval_context is None:
        if request.additional_permissions is not None:
            rule = format_additional_permissions_rule(request.additional_permissions)
            if rule:
                lines.append(f"Permission rule: {rule}")
                lines.append("")
        lines.append("$ " + " ".join(request.command))
    elif request.kind == "Permissions":
        rule = format_requested_permissions_rule(request.permissions)
        if rule:
            lines.append(f"Permission rule: {rule}")
    elif request.kind == "McpElicitation" and request.message:
        lines.append(request.message)
    return lines


def command_decision_to_review_decision(decision: Any) -> HistoryReviewDecision:
    name = _command_decision_name(decision)
    if name == "Accept":
        return HistoryReviewDecision.approved()
    if name == "AcceptForSession":
        return HistoryReviewDecision.approved_for_session()
    if name == "AcceptWithExecpolicyAmendment":
        amendment = _get(decision, "proposed_execpolicy_amendment")
        return HistoryReviewDecision.approved_execpolicy_amendment(amendment)
    if name == "ApplyNetworkPolicyAmendment":
        amendment = _get(decision, "network_policy_amendment")
        return HistoryReviewDecision.network_policy_amendment_decision(amendment)
    if name in {"Decline", "Denied"}:
        return HistoryReviewDecision.denied()
    if name == "Cancel":
        return HistoryReviewDecision.abort()
    raise ValueError(f"unsupported command approval decision: {decision!r}")


def exec_options(
    available_decisions: Iterable[str],
    network_approval_context: Any = None,
    additional_permissions: Any = None,
    approval_keymap: Optional[ApprovalKeymap] = None,
) -> List[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    decisions = list(available_decisions) or ["Accept", "Cancel"]
    options: List[ApprovalOption] = []
    for decision in decisions:
        name = _command_decision_name(decision)
        if name == "Accept":
            label = "Yes, just this once" if network_approval_context is not None else "Yes, proceed"
            shortcuts = keymap.approve
        elif name == "AcceptForSession":
            if network_approval_context is not None:
                label = "Yes, and allow this host for this conversation"
            elif additional_permissions is not None:
                label = "Yes, and allow these permissions for this session"
            else:
                label = "Yes, and don't ask again for this command in this session"
            shortcuts = keymap.approve_for_session
        elif name == "AcceptWithExecpolicyAmendment":
            amendment = _get(decision, "execpolicy_amendment", _get(decision, "proposed_execpolicy_amendment", {}))
            prefix = " ".join(_get(amendment, "command", ()) or ())
            if "\n" in prefix or "\r" in prefix:
                continue
            label = f"Yes, and don't ask again for commands that start with `{prefix}`"
            shortcuts = keymap.approve_for_prefix
        elif name == "ApplyNetworkPolicyAmendment":
            amendment = _get(decision, "network_policy_amendment", {})
            action = str(_get(amendment, "action", "Allow")).lower()
            if action == "deny":
                label = "No, and block this host in the future"
                shortcuts = keymap.deny
            else:
                label = "Yes, and allow this host in the future"
                shortcuts = keymap.approve_for_prefix
        elif name == "Decline":
            label = "No, continue without running it"
            shortcuts = keymap.deny
        elif name == "Cancel":
            label = "No, and tell Codex what to do differently"
            shortcuts = keymap.decline
        else:
            label = name
            shortcuts = keymap.deny
        options.append(ApprovalOption(label, ApprovalDecision.COMMAND, decision, tuple(shortcuts)))
    return options


def patch_options(approval_keymap: Optional[ApprovalKeymap] = None) -> List[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    return [
        ApprovalOption("Yes, proceed", ApprovalDecision.FILE_CHANGE, "Accept", keymap.approve),
        ApprovalOption("Yes, and don't ask again for these files", ApprovalDecision.FILE_CHANGE, "AcceptForSession", keymap.approve_for_session),
        ApprovalOption("No, and tell Codex what to do differently", ApprovalDecision.FILE_CHANGE, "Cancel", keymap.decline),
    ]


def permissions_options(approval_keymap: Optional[ApprovalKeymap] = None) -> List[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    return [
        ApprovalOption("Yes, grant these permissions for this turn", ApprovalDecision.PERMISSIONS, PermissionsDecision.GRANT_FOR_TURN, keymap.approve),
        ApprovalOption(
            "Yes, grant for this turn with strict auto review",
            ApprovalDecision.PERMISSIONS,
            PermissionsDecision.GRANT_FOR_TURN_WITH_STRICT_AUTO_REVIEW,
            ("r",),
        ),
        ApprovalOption("Yes, grant these permissions for this session", ApprovalDecision.PERMISSIONS, PermissionsDecision.GRANT_FOR_SESSION, keymap.approve_for_session),
        ApprovalOption("No, continue without permissions", ApprovalDecision.PERMISSIONS, PermissionsDecision.DENY, tuple(binding for binding in keymap.deny if _binding_label(binding).lower() != "esc")),
    ]


def elicitation_options(approval_keymap: Optional[ApprovalKeymap] = None) -> List[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    return [
        ApprovalOption("Yes, provide the requested info", ApprovalDecision.MCP_ELICITATION, "Continue", keymap.approve),
        ApprovalOption("No, but continue without it", ApprovalDecision.MCP_ELICITATION, "Decline", tuple(binding for binding in keymap.decline if _binding_label(binding).lower() != "esc")),
        ApprovalOption("Cancel this request", ApprovalDecision.MCP_ELICITATION, "Cancel", ("Esc", *tuple(binding for binding in keymap.cancel if _binding_label(binding).lower() != "esc"))),
    ]


def format_additional_permissions_rule(additional_permissions: Any) -> Optional[str]:
    parts: List[str] = []
    network = _get(additional_permissions, "network")
    if network and (_get(network, "enabled", network) is True or network == "enabled"):
        parts.append("network")
    file_system = _get(additional_permissions, "file_system", _get(additional_permissions, "filesystem"))
    if file_system:
        entries = tuple(_get(file_system, "entries", ()) or ())
        if entries:
            for access, label in (("read", "read"), ("write", "write"), ("deny", "deny read")):
                paths = [
                    path_label(_get(entry, "path"))
                    for entry in entries
                    if _access_name(_get(entry, "access")) == access
                ]
                if paths:
                    parts.append(f"{label} {', '.join(paths)}")
        else:
            read = _get(file_system, "read", _get(file_system, "read_roots", [])) or []
            write = _get(file_system, "write", _get(file_system, "write_roots", [])) or []
            if read:
                parts.append("read " + format_file_system_entry_paths(read))
            if write:
                parts.append("write " + format_file_system_entry_paths(write))
    return "; ".join(parts) if parts else None


def format_requested_permissions_rule(permissions: Any) -> Optional[str]:
    if not permissions:
        return None
    if _get(permissions, "network") is not None or _get(permissions, "file_system", _get(permissions, "filesystem")) is not None:
        return format_additional_permissions_rule(permissions)
    read = _get(permissions, "read", _get(permissions, "read_roots", [])) or []
    write = _get(permissions, "write", _get(permissions, "write_roots", [])) or []
    entries = _get(permissions, "entries", []) or []
    parts: List[str] = []
    if read:
        parts.append("read " + format_file_system_entry_paths(read))
    if write:
        parts.append("write " + format_file_system_entry_paths(write))
    if entries:
        parts.append(format_file_system_entry_paths(entries))
    return "; ".join(parts) if parts else None


def format_file_system_entry_paths(entries: Iterable[Any]) -> str:
    return ", ".join(path_label(entry) for entry in entries)


def special_path_label(path: Any) -> str:
    value = _get(path, "value", path)
    kind = str(_get(value, "kind", value)).lower()
    subpath = _get(value, "subpath")
    labels = {
        "root": ":root",
        "minimal": ":minimal",
        "project_roots": ":workspace_roots",
        "workspaceroots": ":workspace_roots",
        "workspace_roots": ":workspace_roots",
        ":workspace_roots": ":workspace_roots",
        "tmpdir": ":tmpdir",
        "slash_tmp": "/tmp",
    }
    base = labels.get(kind, str(_get(value, "path", value)))
    return f"{base}/{subpath}" if subpath is not None else base


def path_label(path: Any) -> str:
    if isinstance(path, Mapping):
        if "special" in path:
            return special_path_label(path["special"])
        path = path.get("path", path)
    path_type = str(_get(path, "type", "")).lower()
    if path_type == "special":
        return f"`{special_path_label(_get(path, 'value'))}`"
    if path_type in {"glob_pattern", "globpattern"}:
        return f"glob `{_get(path, 'pattern', '')}`"
    if path_type == "path":
        path = _get(path, "path")
    elif not isinstance(path, (str, Path)):
        special = _get(path, "special")
        if special is not None and not callable(special):
            return special_path_label(special)
    return f"`{path}`"


def _access_name(access: Any) -> str:
    return str(getattr(access, "value", access)).lower().replace("none", "deny")


def absolute_path(path: Union[str, Path]) -> Path:
    return Path(path)


def render_overlay_lines(view: ApprovalOverlay, width: int = 120) -> str:
    return "\n".join(line.text for line in view.terminal_lines(width=width))


@dataclass(frozen=True)
class ApprovalViewProjector:
    """Project ChatWidget approval plans into the shared active-view stack."""

    app_event_sender: AppEventSender
    show_view: Callable[[ApprovalOverlay], Any]
    render: Callable[[], Any]
    approval_keymap: Any = None
    list_keymap: Any = None

    def __call__(self, plan: Any) -> ApprovalOverlay:
        view = ApprovalOverlay.new(
            approval_request_from_plan(plan),
            app_event_tx=self.app_event_sender,
            approval_keymap=self.approval_keymap,
            list_keymap=self.list_keymap,
        )
        self.show_view(view)
        self.render()
        return view


def approval_request_from_plan(plan: Any) -> ApprovalRequest:
    kind = str(_get(plan, "kind", ""))
    data = dict(_get(plan, "data", {}) or {})
    if kind == "exec":
        return ApprovalRequest.Exec(
            data.get("thread_id"),
            str(data.get("id") or ""),
            data.get("command") or (),
            thread_label=data.get("thread_label"),
            reason=data.get("reason"),
            available_decisions=list(data.get("available_decisions") or ()),
            network_approval_context=data.get("network_approval_context"),
            additional_permissions=data.get("additional_permissions"),
        )
    if kind == "apply_patch":
        return ApprovalRequest.ApplyPatch(
            data.get("thread_id"),
            str(data.get("id") or ""),
            data.get("cwd") or ".",
            data.get("changes") or {},
            thread_label=data.get("thread_label"),
            reason=data.get("reason"),
        )
    if kind == "permissions":
        return ApprovalRequest.Permissions(
            data.get("thread_id"),
            str(data.get("call_id") or ""),
            data.get("permissions"),
            thread_label=data.get("thread_label"),
            reason=data.get("reason"),
        )
    if kind == "mcp_elicitation":
        return ApprovalRequest.McpElicitation(
            data.get("thread_id"),
            str(data.get("server_name") or ""),
            data.get("request_id"),
            str(data.get("message") or ""),
            thread_label=data.get("thread_label"),
        )
    raise ValueError(f"unsupported approval request plan: {kind!r}")


def render_history_cell_lines(cell: Any, width: int = 80) -> List[str]:
    del width
    if cell is None:
        return []
    if hasattr(cell, "display_lines"):
        raw_lines = cell.display_lines(width)
        rendered = []
        for line in raw_lines:
            spans = getattr(line, "spans", None)
            if spans is None:
                rendered.append(str(line))
            else:
                rendered.append("".join(str(getattr(span, "content", span)) for span in spans))
        return rendered
    if isinstance(cell, str):
        return cell.splitlines() or [cell]
    if isinstance(cell, Mapping):
        if "message" in cell:
            return str(cell["message"]).splitlines() or [str(cell["message"])]
        if "lines" in cell:
            return [str(line) for line in cell["lines"]]
    if isinstance(cell, Iterable) and not isinstance(cell, (bytes, bytearray, str, Mapping)):
        return [str(line) for line in cell]
    return [str(cell)]


def normalize_snapshot_paths(text: str) -> str:
    return str(text).replace("\\", "/")


def make_overlay(request: ApprovalRequest | None = None, tx: Any = None, features: Any = None) -> ApprovalOverlay:
    return ApprovalOverlay.new(request or make_exec_request(), tx, features)


def make_overlay_with_keymap(
    request: ApprovalRequest,
    tx: Any = None,
    features: Any = None,
    approval_keymap: Optional[ApprovalKeymap] = None,
    list_keymap: Any = None,
) -> ApprovalOverlay:
    return ApprovalOverlay.new(request, tx, features, approval_keymap, list_keymap)


def make_exec_request() -> ApprovalRequest:
    return ApprovalRequest.Exec("thread", "test", ["echo", "hello"], available_decisions=["Accept", "Cancel"])


def make_permissions_request() -> ApprovalRequest:
    return ApprovalRequest.Permissions("thread", "call", {"read": ["/tmp"]})


def make_elicitation_request() -> ApprovalRequest:
    return ApprovalRequest.McpElicitation("thread", "server", "req", "Need approval")


def _get(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, Mapping):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _key_name(key_event: Any) -> str:
    if isinstance(key_event, str):
        return key_event.lower()
    if isinstance(key_event, Mapping):
        return str(key_event.get("key", key_event.get("code", ""))).lower()
    return str(getattr(key_event, "key", getattr(key_event, "code", key_event))).lower()


def _command_decision_name(decision: Any) -> str:
    raw = str(_get(decision, "type", _get(decision, "kind", decision)))
    return {
        "approved": "Accept",
        "accept": "Accept",
        "approved_for_session": "AcceptForSession",
        "accept_for_session": "AcceptForSession",
        "approved_execpolicy_amendment": "AcceptWithExecpolicyAmendment",
        "accept_with_execpolicy_amendment": "AcceptWithExecpolicyAmendment",
        "network_policy_amendment": "ApplyNetworkPolicyAmendment",
        "apply_network_policy_amendment": "ApplyNetworkPolicyAmendment",
        "denied": "Decline",
        "decline": "Decline",
        "abort": "Cancel",
        "cancel": "Cancel",
    }.get(raw, raw)


def _binding_label(binding: Any) -> str:
    if binding is None:
        return ""
    display = getattr(binding, "display_label", None)
    if callable(display):
        return str(display())
    code = getattr(binding, "code", getattr(binding, "key", None))
    modifiers = set(getattr(binding, "modifiers", ()) or ())
    if code is not None:
        prefix = ""
        if "CONTROL" in modifiers:
            prefix += "ctrl+"
        if "SHIFT" in modifiers:
            prefix += "shift+"
        if "ALT" in modifiers:
            prefix += "alt+"
        label = {"Enter": "enter", "Esc": "esc", " ": "space"}.get(str(code), str(code).lower())
        return prefix + label
    return str(binding).lower()


def _first_binding_label(bindings: Any) -> str:
    values = tuple(bindings or ())
    return _binding_label(values[0]) if values else ""


def _binding_matches(binding: Any, key: str) -> bool:
    return _binding_label(binding).lower() == str(key).lower()


def _as_text_lines(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple)):
        return [str(item) for item in value]
    return [str(value)]


def _inset_wrap(text: str, width: int) -> List[str]:
    if not text:
        return [""]
    available = max(int(width) - 4, 1)
    wrapped = textwrap.wrap(
        str(text),
        width=available,
        replace_whitespace=False,
        drop_whitespace=False,
        break_long_words=True,
        break_on_hyphens=False,
    ) or [""]
    return [f"  {line.rstrip()}" for line in wrapped]


def _wrap_approval_option(text: str, width: int) -> List[str]:
    available = max(int(width), 1)
    wrapped = textwrap.wrap(
        text,
        width=available,
        subsequent_indent="    ",
        break_long_words=True,
        break_on_hyphens=False,
    )
    return wrapped or [""]


def _area_width(area: Any) -> int:
    if isinstance(area, int):
        return area
    if isinstance(area, Mapping):
        return int(area.get("width", 80))
    return int(getattr(area, "width", 80))


__all__ = [
    "ApprovalDecision",
    "ApprovalKeymap",
    "ApprovalOption",
    "ApprovalOverlay",
    "ApprovalRequest",
    "ApprovalViewProjector",
    "PermissionsDecision",
    "RUST_MODULE",
    "absolute_path",
    "approval_footer_hint",
    "approval_request_from_plan",
    "build_header",
    "command_decision_to_review_decision",
    "cursor_pos",
    "desired_height",
    "dismiss_app_server_request",
    "elicitation_options",
    "exec_options",
    "format_additional_permissions_rule",
    "format_file_system_entry_paths",
    "format_requested_permissions_rule",
    "handle_key_event",
    "is_complete",
    "make_elicitation_request",
    "make_exec_request",
    "make_overlay",
    "make_overlay_with_keymap",
    "make_permissions_request",
    "network_approval_command_target",
    "network_approval_target",
    "normalize_snapshot_paths",
    "on_ctrl_c",
    "patch_options",
    "path_label",
    "permissions_options",
    "render",
    "render_history_cell_lines",
    "render_overlay_lines",
    "special_path_label",
    "terminal_title_requires_action",
    "try_consume_approval_request",
]
