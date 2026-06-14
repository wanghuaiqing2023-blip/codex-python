"""Permission and approval popup semantics for chat widgets.

This ports the Rust ``codex-tui::chatwidget::permission_popups`` behavior into
small Python DTOs.  The Rust code builds ratatui selection views and boxed
``AppEvent`` closures; here we expose equivalent selection items and declarative
event actions so callers can integrate them with a Python UI shell.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Iterable, Protocol

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="chatwidget::permission_popups", source="codex/codex-rs/tui/src/chatwidget/permission_popups.rs")

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
    "approve_recent_auto_review_denial",
    "approval_preset_actions",
    "builtin_approval_presets",
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


class ApprovalsReviewer(str, Enum):
    USER = "User"
    AUTO_REVIEW = "AutoReview"


class PermissionProfileKind(str, Enum):
    DISABLED = "Disabled"
    MANAGED = "Managed"


@dataclass(frozen=True)
class PermissionProfile:
    kind: PermissionProfileKind
    writable_roots: tuple[str, ...] = ()
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

    def get_writable_roots_with_cwd(self, cwd: str) -> tuple[str, ...]:
        return tuple(root for root in self.writable_roots if root != "")

    def network_sandbox_policy(self) -> bool:
        return self.network_access


@dataclass(frozen=True)
class ActivePermissionProfile:
    id: str
    name: str | None = None


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
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SelectionItem:
    name: str
    description: str | None = None
    selected_description: str | None = None
    is_current: bool = False
    is_disabled: bool = False
    disabled_reason: str | None = None
    search_value: str | None = None
    actions: list[AppEvent] = field(default_factory=list)
    dismiss_on_select: bool = False


@dataclass
class SelectionViewParams:
    title: str | None = None
    subtitle: str | None = None
    footer_note: str | None = None
    footer_hint: str | None = "Enter to select, Esc to cancel"
    items: list[SelectionItem] = field(default_factory=list)
    is_searchable: bool = False
    col_width_mode: str | None = None
    header: Any | None = None


class PermissionPopupWidget(Protocol):
    config: Any
    bottom_pane: Any
    review: Any


def builtin_approval_presets(cwd: str = ".") -> list[ApprovalPreset]:
    """Return the built-in permission presets used by the popup."""

    return [
        ApprovalPreset(
            id="read-only",
            label="Read Only",
            description="Can read files and answer questions.",
            approval=AskForApproval.ON_REQUEST,
            permission_profile=PermissionProfile.read_only(network_access=False),
            active_permission_profile=ActivePermissionProfile("read-only", "Read Only"),
        ),
        ApprovalPreset(
            id="auto",
            label="Agent",
            description="Can edit files in the workspace. Runs commands in a sandbox.",
            approval=AskForApproval.ON_REQUEST,
            permission_profile=PermissionProfile.auto(cwd, network_access=False),
            active_permission_profile=ActivePermissionProfile("auto", "Agent"),
        ),
        ApprovalPreset(
            id="full-access",
            label="Full Access",
            description="Can edit files and run commands without sandbox restrictions.",
            approval=AskForApproval.NEVER,
            permission_profile=PermissionProfile.disabled(),
            active_permission_profile=ActivePermissionProfile("full-access", "Full Access"),
        ),
    ]


def open_permissions_popup(widget: Any, include_read_only: bool = False) -> SelectionViewParams:
    """Build and show the generic permissions popup."""

    if bool(getattr(widget.config, "explicit_permission_profile_mode", False)):
        return _call(widget, "open_permission_profiles_popup")

    current_approval = _approval(getattr(widget.config.permissions, "approval_policy", AskForApproval.ON_REQUEST))
    current_profile = widget.config.permissions.permission_profile
    guardian_enabled = bool(widget.config.features.enabled("GuardianApproval"))
    current_reviewer = _reviewer(getattr(widget.config, "approvals_reviewer", ApprovalsReviewer.USER))
    cwd = getattr(widget.config, "cwd", ".")
    items: list[SelectionItem] = []

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


def open_auto_review_denials_popup(widget: Any) -> SelectionViewParams | None:
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
    thread_id = _call(widget, "thread_id")
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
    _call(widget.bottom_pane, "show_selection_view", params)
    _call(widget, "request_redraw")
    return params


def approve_recent_auto_review_denial(widget: Any, thread_id: str, id: str) -> list[AppEvent] | None:
    event = widget.review.recent_auto_review_denials.take(id)
    if event is None:
        _call(widget, "add_error_message", "That auto-review denial is no longer available.")
        return None
    events = [
        AppEvent("SubmitThreadOp", {"thread_id": thread_id, "op": ("approve_guardian_denied_action", event)})
    ]
    _send_events(widget, events)
    _call(
        widget,
        "add_info_message",
        "Approval recorded for one retry of the selected auto-review denial.",
        "The model will see the approval context; the retry still goes through auto-review.",
    )
    return events


def approval_preset_actions(
    approval: AskForApproval | str,
    permission_profile: PermissionProfile,
    active_permission_profile: ActivePermissionProfile,
    label: str,
    approvals_reviewer: ApprovalsReviewer | str,
) -> list[AppEvent]:
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


def permission_profile_selection_actions(selection: PermissionProfileSelection) -> list[AppEvent]:
    return [AppEvent("SelectPermissionProfile", {"selection": selection})]


def permission_mode_actions(
    widget: Any,
    preset: ApprovalPreset,
    label: str,
    approvals_reviewer: ApprovalsReviewer | str,
    profile_selection: PermissionProfileSelection | None,
    return_to_permissions: bool,
) -> list[AppEvent]:
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
    current_approval: AskForApproval | str,
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
    profile_selection: PermissionProfileSelection | None = None,
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


def _approval(value: AskForApproval | str) -> AskForApproval:
    return value if isinstance(value, AskForApproval) else AskForApproval(str(value))


def _reviewer(value: ApprovalsReviewer | str) -> ApprovalsReviewer:
    return value if isinstance(value, ApprovalsReviewer) else ApprovalsReviewer(str(value))


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
