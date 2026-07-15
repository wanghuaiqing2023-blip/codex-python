"""Permission and approval popup semantics for chat widgets.

This ports the Rust ``codex-tui::chatwidget::permission_popups`` behavior into
small Python DTOs.  The Rust code builds ratatui selection views and boxed
``AppEvent`` closures; here we expose equivalent selection items and declarative
event actions so callers can integrate them with a Python UI shell.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from enum import Enum
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional, Tuple, Union

from pycodex.features import Feature
from pycodex.protocol import ApprovalsReviewer

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="chatwidget::permission_popups",
    source="codex/codex-rs/tui/src/chatwidget/permission_popups.rs",
    status="complete",
)

__all__ = [
    "AUTO_REVIEW_DESCRIPTION",
    "ActivePermissionProfile",
    "AppEvent",
    "ApprovalPreset",
    "ApprovalsReviewer",
    "AskForApproval",
    "PermissionProfile",
    "PermissionProfileSelection",
    "RUST_MODULE",
    "SelectionItem",
    "SelectionViewParams",
    "TerminalAutoReviewDenialsPopupController",
    "TerminalPermissionsPopupController",
    "approve_recent_auto_review_denial",
    "approval_preset_actions",
    "builtin_approval_presets",
    "open_approvals_popup",
    "open_auto_review_denials_popup",
    "open_full_access_confirmation",
    "open_permissions_popup",
    "permission_mode_actions",
    "permission_profile_selection_actions",
    "preset_matches_current",
]


AUTO_REVIEW_DESCRIPTION = "Let auto-review decide whether commands and edits are allowed."


class AskForApproval(str, Enum):
    NEVER = "never"
    ON_REQUEST = "on-request"
    ON_FAILURE = "on-failure"
    UNLESS_TRUSTED = "unless-trusted"


class PermissionProfileKind(str, Enum):
    DISABLED = "Disabled"
    MANAGED = "Managed"


@dataclass(frozen=True)
class PermissionProfile:
    kind: PermissionProfileKind
    writable_roots: Tuple[str, ...] = ()
    full_disk_write_access: bool = False
    network_access: bool = False

    @classmethod
    def disabled(cls) -> "PermissionProfile":
        return cls(PermissionProfileKind.DISABLED, full_disk_write_access=True, network_access=True)

    @classmethod
    def read_only(cls, network_access: bool = False) -> "PermissionProfile":
        return cls(PermissionProfileKind.MANAGED, writable_roots=(), network_access=network_access)

    @classmethod
    def auto(cls, cwd: str = ".", network_access: bool = False) -> "PermissionProfile":
        return cls(PermissionProfileKind.MANAGED, writable_roots=(cwd,), network_access=network_access)

    def has_full_disk_write_access(self) -> bool:
        return self.full_disk_write_access

    def can_write_path_with_cwd(self, path: str, cwd: str) -> bool:
        if self.full_disk_write_access:
            return True
        return path == cwd and cwd in self.writable_roots

    def get_writable_roots_with_cwd(self, cwd: str) -> Tuple[str, ...]:
        return tuple(root for root in self.writable_roots if root != "")

    def network_sandbox_policy(self) -> bool:
        return self.network_access


@dataclass(frozen=True)
class ActivePermissionProfile:
    id: str
    name: Optional[str] = None


@dataclass(frozen=True)
class PermissionProfileSelection:
    profile: PermissionProfile
    active_profile: ActivePermissionProfile


@dataclass(frozen=True)
class ApprovalPreset:
    id: str
    label: str
    description: str
    approval: AskForApproval
    permission_profile: PermissionProfile
    active_permission_profile: ActivePermissionProfile


@dataclass(frozen=True)
class AppEvent:
    kind: str
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionItem:
    name: str
    description: Optional[str] = None
    selected_description: Optional[str] = None
    is_current: bool = False
    is_disabled: bool = False
    disabled_reason: Optional[str] = None
    search_value: Optional[str] = None
    actions: List[AppEvent] = field(default_factory=list)
    dismiss_on_select: bool = False


@dataclass
class SelectionViewParams:
    title: Optional[str] = None
    subtitle: Optional[str] = None
    footer_note: Optional[str] = None
    footer_hint: Optional[str] = "Enter to select, Esc to cancel"
    items: List[SelectionItem] = field(default_factory=list)
    is_searchable: bool = False
    col_width_mode: Optional[str] = None
    header: Optional[Any] = None


class PermissionPopupWidget:
    config: Any
    bottom_pane: Any
    review: Any


def builtin_approval_presets(cwd: str = ".") -> List[ApprovalPreset]:
    """Return the built-in permission presets used by the popup."""

    return [
        ApprovalPreset(
            id="read-only",
            label="Read Only",
            description="Codex can read files in the current workspace. Approval is required to edit files or access the internet.",
            approval=AskForApproval.ON_REQUEST,
            permission_profile=PermissionProfile.read_only(network_access=False),
            active_permission_profile=ActivePermissionProfile(":read-only", "Read Only"),
        ),
        ApprovalPreset(
            id="auto",
            label="Default",
            description="Codex can read and edit files in the current workspace, and run commands. Approval is required to access the internet or edit other files. (Identical to Agent mode)",
            approval=AskForApproval.ON_REQUEST,
            permission_profile=PermissionProfile.auto(cwd, network_access=False),
            active_permission_profile=ActivePermissionProfile(":workspace", "Default"),
        ),
        ApprovalPreset(
            id="full-access",
            label="Full Access",
            description="Codex can edit files outside this workspace and access the internet without asking for approval. Exercise caution when using.",
            approval=AskForApproval.NEVER,
            permission_profile=PermissionProfile.disabled(),
            active_permission_profile=ActivePermissionProfile(":danger-no-sandbox", "Full Access"),
        ),
    ]


def open_approvals_popup(widget: Any, include_read_only: bool | None = None) -> SelectionViewParams:
    return open_permissions_popup(widget, include_read_only=include_read_only)


def open_permissions_popup(widget: Any, include_read_only: bool | None = None) -> SelectionViewParams:
    """Build and show the generic permissions popup."""

    if bool(getattr(widget.config, "explicit_permission_profile_mode", False)):
        return _call(widget, "open_permission_profiles_popup")

    if include_read_only is None:
        include_read_only = os.name == "nt"

    current_approval = _approval(getattr(widget.config.permissions, "approval_policy", AskForApproval.ON_REQUEST))
    current_profile = widget.config.permissions.permission_profile
    guardian_enabled = bool(widget.config.features.enabled(Feature.GUARDIAN_APPROVAL))
    current_reviewer = _reviewer(getattr(widget.config, "approvals_reviewer", ApprovalsReviewer.USER))
    cwd = getattr(widget.config, "cwd", ".")
    items = []  # type: List[SelectionItem]

    for preset in builtin_approval_presets(cwd):
        if not include_read_only and preset.id == "read-only":
            continue
        base_description = preset.description.replace(" (Identical to Agent mode)", "")
        default_actions = permission_mode_actions(
            widget,
            preset,
            preset.label,
            ApprovalsReviewer.USER,
            profile_selection=None,
            return_to_permissions=not include_read_only,
        )
        if preset.id == "auto":
            items.append(
                SelectionItem(
                    name=preset.label,
                    description=base_description,
                    is_current=current_reviewer is ApprovalsReviewer.USER
                    and preset_matches_current(current_approval, current_profile, cwd, preset),
                    actions=default_actions,
                    dismiss_on_select=True,
                )
            )
            if guardian_enabled:
                items.append(
                    SelectionItem(
                        name="Auto-review",
                        description=AUTO_REVIEW_DESCRIPTION,
                        is_current=current_reviewer is ApprovalsReviewer.AUTO_REVIEW
                        and preset_matches_current(current_approval, current_profile, cwd, preset),
                        actions=permission_mode_actions(
                            widget,
                            preset,
                            "Auto-review",
                            ApprovalsReviewer.AUTO_REVIEW,
                            profile_selection=None,
                            return_to_permissions=not include_read_only,
                        ),
                        dismiss_on_select=True,
                    )
                )
        else:
            items.append(
                SelectionItem(
                    name=preset.label,
                    description=base_description,
                    is_current=preset_matches_current(current_approval, current_profile, cwd, preset),
                    actions=default_actions,
                    dismiss_on_select=True,
                )
            )

    params = SelectionViewParams(
        title="Update Model Permissions",
        items=items,
        footer_hint="Enter to select, Esc to cancel",
    )
    _call(widget.bottom_pane, "show_selection_view", params)
    return params


def open_auto_review_denials_popup(
    widget: Any,
    *,
    thread_id: str | None = None,
    show_view: bool = True,
) -> Optional[SelectionViewParams]:
    denials = getattr(widget.review, "recent_auto_review_denials", None)
    entries = list(_denial_entries(denials))
    if not entries:
        _call(
            widget,
            "add_info_message",
            "No recent auto-review denials in this thread.",
            "Denials are recorded after auto-review rejects an action.",
        )
        return None
    thread_id = thread_id if thread_id is not None else _call(widget, "thread_id")
    if thread_id is None:
        _call(widget, "add_error_message", "That thread is no longer available.")
        return None

    items = [
        SelectionItem(
            name="Command",
            description="Rationale",
            is_disabled=True,
            search_value="",
        )
    ]
    for event in entries:
        summary = action_summary(getattr(event, "action", None))
        rationale = getattr(event, "rationale", None) or "Auto-review did not include a rationale."
        event_id = getattr(event, "id")
        items.append(
            SelectionItem(
                name=summary,
                description=rationale,
                selected_description=rationale,
                search_value=f"{summary} {rationale}",
                actions=[
                    AppEvent(
                        "ApproveRecentAutoReviewDenial",
                        {"thread_id": thread_id, "id": event_id},
                    )
                ],
                dismiss_on_select=True,
            )
        )

    params = SelectionViewParams(
        title="Auto-review Denials",
        subtitle="Select a denied action to approve.",
        items=items,
        is_searchable=True,
        col_width_mode="AutoAllRows",
    )
    if show_view:
        _call(widget.bottom_pane, "show_selection_view", params)
    _call(widget, "request_redraw")
    return params


def approve_recent_auto_review_denial(widget: Any, thread_id: str, id: str) -> Optional[List[AppEvent]]:
    event = widget.review.recent_auto_review_denials.take(id)
    if event is None:
        _call(widget, "add_error_message", "That auto-review denial is no longer available.")
        return None
    from ..app_command import AppCommand

    events = [
        AppEvent(
            "SubmitThreadOp",
            {
                "thread_id": thread_id,
                "op": AppCommand.approve_guardian_denied_action(event),
            },
        )
    ]
    _send_events(widget, events)
    _call(
        widget,
        "add_info_message",
        "Approval recorded for one retry of the selected auto-review denial.",
        "The model will see the approval context; the retry still goes through auto-review.",
    )
    return events


class TerminalAutoReviewDenialsPopupController:
    """Terminal product adapter for Rust ``SlashCommand::AutoReview``."""

    def __init__(self, app_runtime: Any) -> None:
        self.app_runtime = app_runtime

    def open_view(self) -> Optional[SelectionViewParams]:
        thread_id = str(
            self.app_runtime.routing_state.active_thread_id
            or self.app_runtime.thread_id
        )
        return open_auto_review_denials_popup(
            self.app_runtime.chat_widget,
            thread_id=thread_id,
            show_view=False,
        )

    def handle_events(self, events: tuple[object, ...]) -> Any:
        from ..bottom_pane.list_selection_view import TerminalSelectionTransition

        for event in events:
            if getattr(event, "kind", None) != "ApproveRecentAutoReviewDenial":
                continue

            def apply(selected: Any = event) -> None:
                self.app_runtime.handle_bottom_pane_app_event(selected)

            return TerminalSelectionTransition(after_pop=apply)
        return None


class TerminalPermissionsPopupController:
    """Terminal adapter for Rust ``ChatWidget::open_permissions_popup``.

    The generic permission popup belongs to ``permission_popups``. Only the
    explicit profile mode delegates to ``permissions_menu``, matching the Rust
    module boundary instead of making the profile menu the unconditional slash
    command entry point.
    """

    def __init__(self, app_runtime: Any) -> None:
        self.app_runtime = app_runtime
        self._profile_controller: Any = None
        self._explicit_profile_mode = False
        self._widget: Any = None

    def open_view(self) -> Any:
        from ..bottom_pane.list_selection_view import coerce_selection_view_params

        self._explicit_profile_mode = bool(
            _runtime_value(self.app_runtime, "explicit_permission_profile_mode", False)
        )
        if self._explicit_profile_mode:
            from .permissions_menu import TerminalPermissionsPopupController as ProfileController

            if self._profile_controller is None:
                self._profile_controller = ProfileController(self.app_runtime)
            return self._profile_controller.open_view()

        self._widget = _terminal_permission_popup_widget(self.app_runtime)
        return coerce_selection_view_params(open_permissions_popup(self._widget))

    def handle_events(self, events: tuple[object, ...]) -> Any:
        from ..app_event import PermissionProfileSelection as RuntimePermissionProfileSelection
        from ..bottom_pane.list_selection_view import coerce_selection_view_params
        from ..bottom_pane.view_stack import TerminalSelectionTransition

        if self._explicit_profile_mode and self._profile_controller is not None:
            return self._profile_controller.handle_events(events)

        for event in events:
            kind = getattr(event, "kind", None)
            payload = dict(getattr(event, "payload", {}) or {})
            if kind == "OpenFullAccessConfirmation":
                widget = self._widget or _terminal_permission_popup_widget(self.app_runtime)
                next_view = open_full_access_confirmation(
                    widget,
                    payload["preset"],
                    bool(payload.get("return_to_permissions", False)),
                    payload.get("profile_selection"),
                )
                return TerminalSelectionTransition(
                    next_view=coerce_selection_view_params(next_view)
                )
            if kind in {"OpenPermissionsPopup", "OpenApprovalsPopup"}:
                return TerminalSelectionTransition(next_view=self.open_view())

        selection = _runtime_permission_selection(events)
        if selection is None:
            for event in events:
                self.app_runtime.dispatch_app_event(event)
            return None

        runtime_selection = RuntimePermissionProfileSelection(
            profile_id=selection["profile_id"],
            approval_policy=selection["approval_policy"],
            approvals_reviewer=selection["approvals_reviewer"],
            display_label=selection["display_label"],
        )
        acknowledge = any(
            getattr(event, "kind", None) == "UpdateFullAccessWarningAcknowledged"
            for event in events
        )
        remember = any(
            getattr(event, "kind", None) == "PersistFullAccessWarningAcknowledged"
            for event in events
        )

        def apply() -> None:
            try:
                self.app_runtime.apply_permission_profile_selection(runtime_selection)
                if acknowledge:
                    _set_full_access_warning_acknowledged(self.app_runtime)
                if remember:
                    self.app_runtime.persist_full_access_warning_acknowledged()
            except Exception as exc:
                self.app_runtime.chat_widget.add_error_message(
                    f"Failed to save permissions: {exc}"
                )

        return TerminalSelectionTransition(after_pop=apply)


def approval_preset_actions(
    approval: Union[AskForApproval, str],
    permission_profile: PermissionProfile,
    active_permission_profile: ActivePermissionProfile,
    label: str,
    approvals_reviewer: Union[ApprovalsReviewer, str],
) -> List[AppEvent]:
    approval = _approval(approval)
    approvals_reviewer = _reviewer(approvals_reviewer)
    return [
        AppEvent(
            "CodexOp",
            {
                "op": "override_turn_context",
                "approval_policy": approval,
                "approvals_reviewer": approvals_reviewer,
                "permission_profile": permission_profile,
                "active_permission_profile": active_permission_profile,
            },
        ),
        AppEvent("UpdateAskForApprovalPolicy", {"approval": approval}),
        AppEvent("UpdateActivePermissionProfile", {"active_permission_profile": active_permission_profile}),
        AppEvent("UpdateApprovalsReviewer", {"approvals_reviewer": approvals_reviewer}),
        AppEvent("InsertHistoryCell", {"message": f"Permissions updated to {label}", "hint": None}),
    ]


def permission_profile_selection_actions(selection: PermissionProfileSelection) -> List[AppEvent]:
    return [AppEvent("SelectPermissionProfile", {"selection": selection})]


def permission_mode_actions(
    widget: Any,
    preset: ApprovalPreset,
    label: str,
    approvals_reviewer: Union[ApprovalsReviewer, str],
    profile_selection: Optional[PermissionProfileSelection],
    return_to_permissions: bool,
) -> List[AppEvent]:
    approvals_reviewer = _reviewer(approvals_reviewer)
    hide_warning = bool(getattr(widget.config.notices, "hide_full_access_warning", False))
    if approvals_reviewer is ApprovalsReviewer.USER and preset.id == "full-access" and not hide_warning:
        return [
            AppEvent(
                "OpenFullAccessConfirmation",
                {
                    "preset": preset,
                    "return_to_permissions": return_to_permissions,
                    "profile_selection": profile_selection,
                },
            )
        ]
    if approvals_reviewer is ApprovalsReviewer.USER and preset.id == "auto":
        if _windows_sandbox_disabled(widget):
            if _elevated_sandbox_nux_enabled(widget) and _sandbox_setup_is_complete(widget):
                return [
                    AppEvent(
                        "EnableWindowsSandboxForAgentMode",
                        {
                            "preset": preset,
                            "mode": "Elevated",
                            "profile_selection": profile_selection,
                        },
                    )
                ]
            return [
                AppEvent(
                    "OpenWindowsSandboxEnablePrompt",
                    {
                        "preset": preset,
                        "profile_selection": profile_selection,
                    },
                )
            ]
        details = _world_writable_warning_details(widget)
        if details is not None:
            sample_paths, extra_count, failed_scan = details
            return [
                AppEvent(
                    "OpenWorldWritableWarningConfirmation",
                    {
                        "preset": preset,
                        "profile_selection": profile_selection,
                        "sample_paths": sample_paths,
                        "extra_count": extra_count,
                        "failed_scan": failed_scan,
                    },
                )
            ]
    if profile_selection is not None:
        return permission_profile_selection_actions(profile_selection)
    return approval_preset_actions(
        AskForApproval(preset.approval),
        preset.permission_profile,
        preset.active_permission_profile,
        label,
        approvals_reviewer,
    )


def preset_matches_current(
    current_approval: Union[AskForApproval, str],
    current_permission_profile: PermissionProfile,
    cwd: str,
    preset: ApprovalPreset,
) -> bool:
    if _approval(current_approval) != _approval(preset.approval):
        return False
    if preset.id == "full-access":
        return current_permission_profile.kind is PermissionProfileKind.DISABLED
    if preset.id == "read-only":
        return (
            current_permission_profile.kind is PermissionProfileKind.MANAGED
            and not current_permission_profile.has_full_disk_write_access()
            and current_permission_profile.get_writable_roots_with_cwd(cwd) == ()
            and current_permission_profile.network_sandbox_policy()
            == preset.permission_profile.network_sandbox_policy()
        )
    if preset.id == "auto":
        return (
            current_permission_profile.kind is PermissionProfileKind.MANAGED
            and current_permission_profile.can_write_path_with_cwd(cwd, cwd)
            and not current_permission_profile.has_full_disk_write_access()
            and current_permission_profile.network_sandbox_policy()
            == preset.permission_profile.network_sandbox_policy()
        )
    return current_permission_profile == preset.permission_profile


def open_full_access_confirmation(
    widget: Any,
    preset: ApprovalPreset,
    return_to_permissions: bool,
    profile_selection: Optional[PermissionProfileSelection] = None,
) -> SelectionViewParams:
    selected_name = preset.label
    approval = _approval(preset.approval)
    accept_actions = (
        permission_profile_selection_actions(profile_selection)
        if profile_selection is not None
        else approval_preset_actions(
            approval,
            preset.permission_profile,
            preset.active_permission_profile,
            selected_name,
            ApprovalsReviewer.USER,
        )
    )
    accept_actions = [*accept_actions, AppEvent("UpdateFullAccessWarningAcknowledged", {"acknowledged": True})]

    remember_actions = (
        permission_profile_selection_actions(profile_selection)
        if profile_selection is not None
        else approval_preset_actions(
            approval,
            preset.permission_profile,
            preset.active_permission_profile,
            selected_name,
            ApprovalsReviewer.USER,
        )
    )
    remember_actions = [
        *remember_actions,
        AppEvent("UpdateFullAccessWarningAcknowledged", {"acknowledged": True}),
        AppEvent("PersistFullAccessWarningAcknowledged"),
    ]

    deny_event = "OpenPermissionsPopup" if return_to_permissions else "OpenApprovalsPopup"
    params = SelectionViewParams(
        header="Enable full access?",
        items=[
            SelectionItem(
                name="Yes, continue anyway",
                description="Apply full access for this session",
                actions=accept_actions,
                dismiss_on_select=True,
            ),
            SelectionItem(
                name="Yes, and don't ask again",
                description="Enable full access and remember this choice",
                actions=remember_actions,
                dismiss_on_select=True,
            ),
            SelectionItem(
                name="Cancel",
                description="Go back without enabling full access",
                actions=[AppEvent(deny_event)],
                dismiss_on_select=True,
            ),
        ],
    )
    _call(widget.bottom_pane, "show_selection_view", params)
    return params


def action_summary(action: Any) -> str:
    if action is None:
        return "Action"
    if isinstance(action, str):
        return action
    return getattr(action, "summary", None) or getattr(action, "command", None) or str(action)


def _approval(value: Union[AskForApproval, str]) -> AskForApproval:
    if isinstance(value, AskForApproval):
        return value
    raw = getattr(value, "value", value)
    text = str(raw)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    key = text.strip().lower().replace("_", "-")
    aliases = {
        "never": AskForApproval.NEVER,
        "on-request": AskForApproval.ON_REQUEST,
        "onrequest": AskForApproval.ON_REQUEST,
        "on-failure": AskForApproval.ON_FAILURE,
        "onfailure": AskForApproval.ON_FAILURE,
        "unless-trusted": AskForApproval.UNLESS_TRUSTED,
        "unlesstrusted": AskForApproval.UNLESS_TRUSTED,
    }
    if key in aliases:
        return aliases[key]
    return AskForApproval(key)


def _reviewer(value: Union[ApprovalsReviewer, str]) -> ApprovalsReviewer:
    if isinstance(value, ApprovalsReviewer):
        return value
    raw = getattr(value, "value", value)
    text = str(raw)
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    key = text.strip().lower().replace("_", "-")
    aliases = {
        "user": ApprovalsReviewer.USER,
        "auto": ApprovalsReviewer.AUTO_REVIEW,
        "auto-review": ApprovalsReviewer.AUTO_REVIEW,
        "autoreview": ApprovalsReviewer.AUTO_REVIEW,
    }
    if key in aliases:
        return aliases[key]
    return ApprovalsReviewer(key)


def _call(target: Any, method_name: str, *args: Any) -> Any:
    method = getattr(target, method_name, None)
    if method is None:
        raise AttributeError(f"target does not implement {method_name}()")
    return method(*args)


def _send_events(widget: Any, events: Iterable[AppEvent]) -> None:
    tx = getattr(widget, "app_event_tx", None)
    if tx is None:
        return
    for event in events:
        tx.send(event)


def _denial_entries(denials: Any) -> Iterable[Any]:
    if denials is None:
        return ()
    entries = getattr(denials, "entries", None)
    if entries is not None:
        return entries()
    return tuple(denials)


def _windows_sandbox_disabled(widget: Any) -> bool:
    level = getattr(widget.config, "windows_sandbox_level", None)
    if level is None:
        return False
    return str(level).split(".")[-1] == "Disabled"


def _elevated_sandbox_nux_enabled(widget: Any) -> bool:
    return bool(getattr(widget.config, "elevated_sandbox_nux_enabled", False))


def _sandbox_setup_is_complete(widget: Any) -> bool:
    checker = getattr(widget, "sandbox_setup_is_complete", None)
    return bool(checker()) if callable(checker) else False


def _world_writable_warning_details(widget: Any) -> Optional[Tuple[Any, Any, Any]]:
    details = getattr(widget, "world_writable_warning_details", None)
    if not callable(details):
        return None
    value = details()
    if value is None:
        return None
    sample_paths, extra_count, failed_scan = value
    return sample_paths, extra_count, failed_scan


def _runtime_value(app_runtime: Any, name: str, default: Any = None) -> Any:
    runtime = getattr(app_runtime, "active_thread_runtime", None)
    for source in (
        runtime,
        getattr(runtime, "session_config", None),
        getattr(runtime, "config", None),
        getattr(getattr(app_runtime, "chat_widget", None), "config", None),
    ):
        value = getattr(source, name, None) if source is not None else None
        if value is not None:
            return value
    return default


class _TerminalPopupPane:
    def __init__(self) -> None:
        self.params: Any = None

    def show_selection_view(self, params: Any) -> None:
        self.params = params


class _DisabledFeatures:
    def enabled(self, _feature: Any) -> bool:
        return False


def _terminal_permission_popup_widget(app_runtime: Any) -> Any:
    cwd = str(_runtime_value(app_runtime, "cwd", getattr(app_runtime, "cwd", ".")))
    active = _runtime_value(app_runtime, "active_permission_profile", None)
    profile = _popup_permission_profile(
        _runtime_value(app_runtime, "permission_profile", None),
        active,
        cwd,
    )
    raw_notices = _runtime_value(app_runtime, "notices", None)
    hide_full_access_warning = bool(
        getattr(
            raw_notices,
            "hide_full_access_warning",
            _runtime_value(app_runtime, "hide_full_access_warning", False),
        )
    )
    config = SimpleNamespace(
        explicit_permission_profile_mode=False,
        cwd=cwd,
        permissions=SimpleNamespace(
            approval_policy=_runtime_value(
                app_runtime, "approval_policy", AskForApproval.ON_REQUEST
            ),
            permission_profile=profile,
        ),
        features=_runtime_value(app_runtime, "features", _DisabledFeatures()),
        approvals_reviewer=_runtime_value(
            app_runtime, "approvals_reviewer", ApprovalsReviewer.USER
        ),
        notices=SimpleNamespace(
            hide_full_access_warning=hide_full_access_warning,
        ),
        windows_sandbox_level=_runtime_value(app_runtime, "windows_sandbox_level", None),
    )
    return SimpleNamespace(
        config=config,
        bottom_pane=_TerminalPopupPane(),
        review=getattr(getattr(app_runtime, "chat_widget", None), "review", None),
    )


def _popup_permission_profile(profile: Any, active: Any, cwd: str) -> PermissionProfile:
    active_id = str(getattr(active, "id", active) or "")
    if active_id == ":read-only":
        return PermissionProfile.read_only()
    if active_id == ":workspace":
        return PermissionProfile.auto(cwd)
    if active_id == ":danger-full-access":
        return PermissionProfile.disabled()

    profile_type = str(getattr(profile, "type", "")).lower()
    if profile_type == "disabled":
        return PermissionProfile.disabled()
    if profile_type == "managed":
        policy_getter = getattr(profile, "file_system_sandbox_policy", None)
        policy = policy_getter() if callable(policy_getter) else None
        can_write = getattr(policy, "can_write_path_with_cwd", None)
        if callable(can_write) and bool(can_write(cwd, cwd)):
            return PermissionProfile.auto(cwd)
        return PermissionProfile.read_only()
    if isinstance(profile, PermissionProfile):
        return profile
    return PermissionProfile.auto(cwd)


def _runtime_permission_selection(events: tuple[object, ...]) -> Optional[Dict[str, Any]]:
    label: Optional[str] = None
    for event in events:
        if getattr(event, "kind", None) != "InsertHistoryCell":
            continue
        message = str(dict(getattr(event, "payload", {}) or {}).get("message") or "")
        prefix = "Permissions updated to "
        if message.startswith(prefix):
            label = message[len(prefix) :]

    for event in events:
        kind = getattr(event, "kind", None)
        payload = dict(getattr(event, "payload", {}) or {})
        if kind == "SelectPermissionProfile":
            selection = payload.get("selection")
            profile_id = getattr(selection, "profile_id", None)
            if profile_id is not None:
                return {
                    "profile_id": str(profile_id),
                    "approval_policy": getattr(selection, "approval_policy", None),
                    "approvals_reviewer": getattr(selection, "approvals_reviewer", None),
                    "display_label": str(getattr(selection, "display_label", profile_id)),
                }
        if kind != "CodexOp":
            continue
        active = payload.get("active_permission_profile")
        profile_id = getattr(active, "id", None)
        if profile_id is None:
            continue
        reviewer = payload.get("approvals_reviewer", ApprovalsReviewer.USER)
        display_label = label or getattr(active, "name", None) or str(profile_id)
        if _reviewer(reviewer) is ApprovalsReviewer.AUTO_REVIEW:
            display_label = "Auto-review"
        return {
            "profile_id": str(profile_id),
            "approval_policy": payload.get("approval_policy"),
            "approvals_reviewer": reviewer,
            "display_label": str(display_label),
        }
    return None


def _set_full_access_warning_acknowledged(app_runtime: Any) -> None:
    config = getattr(getattr(app_runtime, "chat_widget", None), "config", None)
    if config is None:
        return
    notices = getattr(config, "notices", None)
    if notices is None:
        notices = SimpleNamespace()
        setattr(config, "notices", notices)
    setattr(notices, "hide_full_access_warning", True)
