"""Semantic approval overlay for Rust ``bottom_pane/approval_overlay.rs``."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping

from .._porting import RustTuiModule, not_ported

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::approval_overlay",
    source="codex/codex-rs/tui/src/bottom_pane/approval_overlay.rs",
)


@dataclass(frozen=True)
class ApprovalRequest:
    kind: str
    thread_id: Any
    id: str | None = None
    thread_label: str | None = None
    command: list[str] = field(default_factory=list)
    reason: str | None = None
    available_decisions: list[str] = field(default_factory=list)
    network_approval_context: Any = None
    additional_permissions: Any = None
    call_id: str | None = None
    permissions: Any = None
    cwd: Path | None = None
    changes: dict[Path, Any] = field(default_factory=dict)
    server_name: str | None = None
    request_id: Any = None
    message: str | None = None

    @classmethod
    def Exec(cls, thread_id: Any, id: str, command: Iterable[str], **kwargs: Any) -> "ApprovalRequest":
        return cls(kind="Exec", thread_id=thread_id, id=id, command=list(command), **kwargs)

    @classmethod
    def Permissions(cls, thread_id: Any, call_id: str, permissions: Any, **kwargs: Any) -> "ApprovalRequest":
        return cls(kind="Permissions", thread_id=thread_id, call_id=call_id, permissions=permissions, **kwargs)

    @classmethod
    def ApplyPatch(cls, thread_id: Any, id: str, cwd: str | Path, changes: Mapping[Any, Any], **kwargs: Any) -> "ApprovalRequest":
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
    shortcuts: tuple[str, ...] = ()


@dataclass
class ApprovalKeymap:
    approve: tuple[str, ...] = ("y",)
    approve_for_session: tuple[str, ...] = ("a",)
    deny: tuple[str, ...] = ("n",)
    strict_auto_review: tuple[str, ...] = ("r",)
    cancel: tuple[str, ...] = ("Esc",)
    open_fullscreen: tuple[str, ...] = ("ctrl+shift+a",)
    open_thread: tuple[str, ...] = ("o",)


@dataclass
class ApprovalOverlay:
    current_request: ApprovalRequest | None
    app_event_tx: Any = None
    features: Any = None
    approval_keymap: ApprovalKeymap = field(default_factory=ApprovalKeymap)
    list_keymap: Any = None
    queue: list[ApprovalRequest] = field(default_factory=list)
    options: list[ApprovalOption] = field(default_factory=list)
    current_complete: bool = False
    done: bool = False
    emitted_events: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def new(
        cls,
        request: ApprovalRequest,
        app_event_tx: Any = None,
        features: Any = None,
        approval_keymap: ApprovalKeymap | None = None,
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
        self.options, _params = self.build_options(request, build_header(request), self.features, self.approval_keymap, self.list_keymap)

    @staticmethod
    def build_options(
        request: ApprovalRequest,
        header: Any = None,
        features: Any = None,
        approval_keymap: ApprovalKeymap | None = None,
        list_keymap: Any = None,
    ) -> tuple[list[ApprovalOption], dict[str, Any]]:
        del features, list_keymap
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
        return options, {"title": title, "header": header, "footer_hint": approval_footer_hint(request, keymap, list_keymap)}

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
        self.advance_queue()

    def handle_exec_decision(self, id: str, command: list[str], decision: str) -> None:
        request = self.current_request
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
        self._emit("PatchApproval", thread_id=None if request is None else request.thread_id, id=id, decision=decision)

    def handle_elicitation_decision(self, server_name: str, request_id: Any, decision: str) -> None:
        request = self.current_request
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

    def try_handle_shortcut(self, key_event: Any) -> bool:
        key = _key_name(key_event)
        if key in self.approval_keymap.open_fullscreen and self.current_request is not None:
            self._emit("FullScreenApprovalRequest", request=self.current_request)
            return True
        if key in self.approval_keymap.open_thread and self.current_request is not None and self.current_request.thread_label:
            self._emit("OpenThread", thread_id=self.current_request.thread_id)
            return True
        for idx, option in enumerate(self.options):
            if key in option.shortcuts:
                self.apply_selection(idx)
                return True
        return False

    def handle_key_event(self, key_event: Any) -> None:
        key = _key_name(key_event)
        if self.current_request is not None and self.current_request.kind == "McpElicitation" and key == "Esc":
            self.cancel_current_request()
            return
        if self.try_handle_shortcut(key_event):
            return
        if key in {"Esc", "ctrl+c"}:
            self.cancel_current_request()
        elif key == "Enter":
            self.apply_selection(0)

    def on_ctrl_c(self) -> str:
        self.cancel_current_request()
        return "Handled"

    def is_complete(self) -> bool:
        return self.done

    def try_consume_approval_request(self) -> ApprovalRequest | None:
        return self.current_request

    def dismiss_app_server_request(self, request: Any) -> bool:
        return self.dismiss_resolved_request(request)

    def terminal_title_requires_action(self) -> bool:
        return not self.done

    def desired_height(self, width: int = 80) -> int:
        del width
        return len(render_overlay_lines(self))

    def render(self, area: Any = None, buf: Any = None) -> list[str]:
        del area
        lines = render_overlay_lines(self)
        if isinstance(buf, list):
            buf.extend(lines)
        return lines

    def cursor_pos(self) -> None:
        return None

    def _emit(self, event_type: str, **payload: Any) -> None:
        event = {"type": event_type, **payload}
        self.emitted_events.append(event)
        if hasattr(self.app_event_tx, "send"):
            self.app_event_tx.send(event)


def handle_key_event(view: ApprovalOverlay, key_event: Any) -> None:
    view.handle_key_event(key_event)


def on_ctrl_c(view: ApprovalOverlay) -> str:
    return view.on_ctrl_c()


def is_complete(view: ApprovalOverlay) -> bool:
    return view.is_complete()


def try_consume_approval_request(view: ApprovalOverlay) -> ApprovalRequest | None:
    return view.try_consume_approval_request()


def dismiss_app_server_request(view: ApprovalOverlay, request: Any) -> bool:
    return view.dismiss_app_server_request(request)


def terminal_title_requires_action(view: ApprovalOverlay) -> bool:
    return view.terminal_title_requires_action()


def desired_height(view: ApprovalOverlay, width: int = 80) -> int:
    return view.desired_height(width)


def render(view: ApprovalOverlay, area: Any = None, buf: Any = None) -> list[str]:
    return view.render(area, buf)


def cursor_pos(view: ApprovalOverlay) -> None:
    return view.cursor_pos()


def approval_footer_hint(request: ApprovalRequest, approval_keymap: ApprovalKeymap | None = None, list_keymap: Any = None) -> str:
    del list_keymap
    keymap = approval_keymap or ApprovalKeymap()
    base = f"Press {keymap.approve[0]} to confirm or {keymap.cancel[0]} to cancel"
    if request.thread_label:
        return f"{base}; {keymap.open_thread[0]} to open thread"
    return base


def network_approval_target(network_approval_context: Any, command: Iterable[str] = ()) -> str:
    host = _get(network_approval_context, "host")
    protocol = str(_get(network_approval_context, "protocol", "")).lower()
    if host:
        return f"{protocol}://{host}" if protocol and not str(host).startswith(f"{protocol}://") else str(host)
    return network_approval_command_target(command) or ""


def network_approval_command_target(command: Iterable[str]) -> str | None:
    parts = list(command)
    if len(parts) >= 2 and parts[0] == "network-access":
        return parts[1]
    return None


def build_header(request: ApprovalRequest) -> list[str]:
    lines: list[str] = []
    if request.thread_label:
        lines.append(f"Thread: {request.thread_label}")
    if request.reason:
        lines.append(f"Reason: {request.reason}")
    if request.kind == "Exec" and request.network_approval_context is None:
        lines.append("$ " + " ".join(request.command))
    elif request.kind == "Permissions":
        rule = format_requested_permissions_rule(request.permissions)
        if rule:
            lines.append(f"Permission rule: {rule}")
    elif request.kind == "ApplyPatch":
        lines.extend(str(path) for path in request.changes)
    elif request.kind == "McpElicitation" and request.message:
        lines.append(request.message)
    if request.additional_permissions is not None:
        rule = format_additional_permissions_rule(request.additional_permissions)
        if rule:
            lines.append(f"Permission rule: {rule}")
    return lines


def command_decision_to_review_decision(decision: str) -> str:
    return {
        "Accept": "Approved",
        "AcceptForSession": "ApprovedForSession",
        "Denied": "Denied",
        "Cancel": "Denied",
    }.get(str(decision), str(decision))


def exec_options(
    available_decisions: Iterable[str],
    network_approval_context: Any = None,
    additional_permissions: Any = None,
    approval_keymap: ApprovalKeymap | None = None,
) -> list[ApprovalOption]:
    del additional_permissions
    keymap = approval_keymap or ApprovalKeymap()
    decisions = list(available_decisions) or ["Accept", "Cancel"]
    labels = {
        "Accept": "Yes, allow once",
        "AcceptForSession": "Yes, and don't ask again this session",
        "Denied": "No, deny",
        "Cancel": "No, cancel",
        "ApplyNetworkPolicyAmendment": "Yes, allow network access",
    }
    options: list[ApprovalOption] = []
    for decision in decisions:
        if network_approval_context is not None and decision == "AcceptForSession":
            continue
        shortcuts = keymap.approve if decision in {"Accept", "ApplyNetworkPolicyAmendment"} else (
            keymap.approve_for_session if decision == "AcceptForSession" else keymap.deny
        )
        options.append(ApprovalOption(labels.get(str(decision), str(decision)), ApprovalDecision.COMMAND, decision, tuple(shortcuts)))
    return options


def patch_options(approval_keymap: ApprovalKeymap | None = None) -> list[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    return [
        ApprovalOption("Yes, apply changes", ApprovalDecision.FILE_CHANGE, "Accept", keymap.approve),
        ApprovalOption("No, cancel", ApprovalDecision.FILE_CHANGE, "Cancel", keymap.deny),
    ]


def permissions_options(approval_keymap: ApprovalKeymap | None = None) -> list[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    return [
        ApprovalOption("Allow for this turn", ApprovalDecision.PERMISSIONS, PermissionsDecision.GRANT_FOR_TURN, keymap.approve),
        ApprovalOption(
            "Allow for this turn with strict auto review",
            ApprovalDecision.PERMISSIONS,
            PermissionsDecision.GRANT_FOR_TURN_WITH_STRICT_AUTO_REVIEW,
            keymap.strict_auto_review,
        ),
        ApprovalOption("Allow for this session", ApprovalDecision.PERMISSIONS, PermissionsDecision.GRANT_FOR_SESSION, keymap.approve_for_session),
        ApprovalOption("Deny", ApprovalDecision.PERMISSIONS, PermissionsDecision.DENY, keymap.deny),
    ]


def elicitation_options(approval_keymap: ApprovalKeymap | None = None) -> list[ApprovalOption]:
    keymap = approval_keymap or ApprovalKeymap()
    return [
        ApprovalOption("Continue", ApprovalDecision.MCP_ELICITATION, "Continue", keymap.approve),
        ApprovalOption("Decline", ApprovalDecision.MCP_ELICITATION, "Decline", keymap.deny),
        ApprovalOption("Cancel", ApprovalDecision.MCP_ELICITATION, "Cancel", keymap.cancel),
    ]


def format_additional_permissions_rule(additional_permissions: Any) -> str | None:
    parts: list[str] = []
    network = _get(additional_permissions, "network")
    if network and (_get(network, "enabled", network) is True or network == "enabled"):
        parts.append("network")
    file_system = _get(additional_permissions, "file_system", _get(additional_permissions, "filesystem"))
    if file_system:
        fs_text = format_requested_permissions_rule(file_system)
        if fs_text:
            parts.append(fs_text)
    return "; ".join(parts) if parts else None


def format_requested_permissions_rule(permissions: Any) -> str | None:
    if not permissions:
        return None
    read = _get(permissions, "read", _get(permissions, "read_roots", [])) or []
    write = _get(permissions, "write", _get(permissions, "write_roots", [])) or []
    entries = _get(permissions, "entries", []) or []
    parts: list[str] = []
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
    value = str(_get(path, "value", path))
    if value in {"WorkspaceRoots", "workspace_roots", ":workspace_roots"}:
        return ":workspace_roots"
    return value


def path_label(path: Any) -> str:
    if isinstance(path, Mapping):
        if "special" in path:
            return special_path_label(path["special"])
        path = path.get("path", path)
    special = _get(path, "special")
    if special is not None:
        return special_path_label(special)
    return f"`{path}`"


def absolute_path(path: str | Path) -> Path:
    return Path(path)


def render_overlay_lines(view: ApprovalOverlay, width: int = 120) -> str:
    del width
    if view.current_request is None:
        return ""
    _options, params = ApprovalOverlay.build_options(view.current_request, build_header(view.current_request), view.features, view.approval_keymap, view.list_keymap)
    lines = [params["title"], ""]
    lines.extend(params["header"])
    lines.extend(option.label for option in view.options)
    lines.append(params["footer_hint"])
    return "\n".join(line for line in lines if line is not None)


def render_history_cell_lines(*args: Any, **kwargs: Any) -> Any:
    return not_ported(RUST_MODULE, "render_history_cell_lines")


def normalize_snapshot_paths(text: str) -> str:
    return str(text).replace("\\", "/")


def make_overlay(request: ApprovalRequest | None = None, tx: Any = None, features: Any = None) -> ApprovalOverlay:
    return ApprovalOverlay.new(request or make_exec_request(), tx, features)


def make_overlay_with_keymap(
    request: ApprovalRequest,
    tx: Any = None,
    features: Any = None,
    approval_keymap: ApprovalKeymap | None = None,
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
        return key_event
    if isinstance(key_event, Mapping):
        return str(key_event.get("key", key_event.get("code", "")))
    return str(getattr(key_event, "key", getattr(key_event, "code", key_event)))


__all__ = [
    "ApprovalDecision",
    "ApprovalKeymap",
    "ApprovalOption",
    "ApprovalOverlay",
    "ApprovalRequest",
    "PermissionsDecision",
    "RUST_MODULE",
    "absolute_path",
    "approval_footer_hint",
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
