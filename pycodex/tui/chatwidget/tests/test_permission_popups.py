from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.permission_popups import (
    ActivePermissionProfile,
    AppEvent,
    ApprovalsReviewer,
    AskForApproval,
    PermissionProfile,
    PermissionProfileSelection,
    builtin_approval_presets,
    open_approvals_popup,
    open_auto_review_denials_popup,
    approve_recent_auto_review_denial,
    open_full_access_confirmation,
    open_permissions_popup,
    permission_mode_actions,
    preset_matches_current,
)
from pycodex.tui.app_command import AppCommand


class Features:
    def __init__(self, enabled=()) -> None:
        self.enabled_set = set(enabled)

    def enabled(self, feature: str) -> bool:
        return feature in self.enabled_set


class Pane:
    def __init__(self) -> None:
        self.params = None

    def show_selection_view(self, params) -> None:
        self.params = params


class Widget:
    def __init__(self) -> None:
        cwd = "/repo"
        self.bottom_pane = Pane()
        self.config = SimpleNamespace(
            explicit_permission_profile_mode=False,
            cwd=cwd,
            permissions=SimpleNamespace(
                approval_policy=AskForApproval.ON_REQUEST,
                permission_profile=PermissionProfile.auto(cwd),
            ),
            features=Features(),
            approvals_reviewer=ApprovalsReviewer.USER,
            notices=SimpleNamespace(hide_full_access_warning=False),
        )
        self.info_messages = []
        self.error_messages = []
        self.redraws = 0

    def add_info_message(self, message, hint=None) -> None:
        self.info_messages.append((message, hint))

    def add_error_message(self, message) -> None:
        self.error_messages.append(message)

    def request_redraw(self) -> None:
        self.redraws += 1

    def thread_id(self):
        return "thread-1"


def test_open_permissions_popup_builds_current_agent_and_guardian_auto_review_item() -> None:
    widget = Widget()
    widget.config.features = Features({"GuardianApproval"})

    params = open_permissions_popup(widget, include_read_only=False)

    assert params.title == "Update Model Permissions"
    assert widget.bottom_pane.params is params
    names = [item.name for item in params.items]
    assert names == ["Default", "Auto-review", "Full Access"]
    assert params.items[0].is_current is True
    assert params.items[1].description
    assert params.items[2].actions[0].kind == "OpenFullAccessConfirmation"


def test_open_permissions_popup_includes_read_only_on_windows_product_path() -> None:
    # Rust parity: codex-tui::chatwidget::permission_popups includes the
    # read-only preset on Windows via cfg(target_os = "windows").
    widget = Widget()

    params = open_permissions_popup(widget, include_read_only=True)

    assert [item.name for item in params.items] == ["Read Only", "Default", "Full Access"]


def test_open_approvals_popup_aliases_permissions_popup() -> None:
    widget = Widget()

    params = open_approvals_popup(widget)

    assert params is widget.bottom_pane.params
    assert params.title == "Update Model Permissions"


def test_open_permissions_popup_delegates_explicit_permission_profile_mode() -> None:
    # Rust parity: open_permissions_popup immediately delegates when
    # explicit_permission_profile_mode is enabled.
    widget = Widget()
    widget.config.explicit_permission_profile_mode = True
    expected = object()
    widget.open_permission_profiles_popup = lambda: expected

    assert open_permissions_popup(widget) is expected
    assert widget.bottom_pane.params is None


def test_permission_mode_actions_require_confirmation_for_unacknowledged_full_access() -> None:
    widget = Widget()
    full_access = next(preset for preset in builtin_approval_presets(widget.config.cwd) if preset.id == "full-access")

    actions = permission_mode_actions(
        widget,
        full_access,
        "Full Access",
        ApprovalsReviewer.USER,
        profile_selection=None,
        return_to_permissions=True,
    )

    assert actions == [
        AppEvent(
            "OpenFullAccessConfirmation",
            {
                "preset": full_access,
                "return_to_permissions": True,
                "profile_selection": None,
            },
        )
    ]


def test_permission_mode_actions_apply_selection_when_profile_selection_is_present() -> None:
    widget = Widget()
    preset = builtin_approval_presets(widget.config.cwd)[1]
    selection = PermissionProfileSelection(
        profile=PermissionProfile.read_only(),
        active_profile=ActivePermissionProfile("custom"),
    )

    actions = permission_mode_actions(
        widget,
        preset,
        "Custom",
        ApprovalsReviewer.USER,
        profile_selection=selection,
        return_to_permissions=False,
    )

    assert actions == [AppEvent("SelectPermissionProfile", {"selection": selection})]


def test_permission_mode_actions_route_windows_auto_mode_confirmations() -> None:
    widget = Widget()
    widget.config.windows_sandbox_level = "Disabled"
    preset = builtin_approval_presets(widget.config.cwd)[1]

    actions = permission_mode_actions(
        widget,
        preset,
        "Default",
        ApprovalsReviewer.USER,
        profile_selection=None,
        return_to_permissions=True,
    )

    assert actions[0].kind == "OpenWindowsSandboxEnablePrompt"

    widget.config.windows_sandbox_level = None
    widget.world_writable_warning_details = lambda: (["/repo"], 2, False)
    actions = permission_mode_actions(
        widget,
        preset,
        "Default",
        ApprovalsReviewer.USER,
        profile_selection=None,
        return_to_permissions=True,
    )

    assert actions == [
        AppEvent(
            "OpenWorldWritableWarningConfirmation",
            {
                "preset": preset,
                "profile_selection": None,
                "sample_paths": ["/repo"],
                "extra_count": 2,
                "failed_scan": False,
            },
        )
    ]


def test_preset_matches_current_special_cases_full_read_only_and_auto() -> None:
    cwd = "/repo"
    presets = {preset.id: preset for preset in builtin_approval_presets(cwd)}

    assert preset_matches_current(AskForApproval.NEVER, PermissionProfile.disabled(), cwd, presets["full-access"])
    assert preset_matches_current(AskForApproval.ON_REQUEST, PermissionProfile.read_only(), cwd, presets["read-only"])
    assert preset_matches_current(AskForApproval.ON_REQUEST, PermissionProfile.auto(cwd), cwd, presets["auto"])
    assert not preset_matches_current(AskForApproval.ON_REQUEST, PermissionProfile.read_only(), cwd, presets["auto"])


def test_open_full_access_confirmation_builds_accept_remember_and_cancel_actions() -> None:
    widget = Widget()
    preset = next(preset for preset in builtin_approval_presets(widget.config.cwd) if preset.id == "full-access")

    params = open_full_access_confirmation(widget, preset, return_to_permissions=True)

    assert widget.bottom_pane.params is params
    assert [item.name for item in params.items] == [
        "Yes, continue anyway",
        "Yes, and don't ask again",
        "Cancel",
    ]
    assert params.items[0].actions[-1].kind == "UpdateFullAccessWarningAcknowledged"
    assert params.items[1].actions[-1].kind == "PersistFullAccessWarningAcknowledged"
    assert params.items[2].actions == [AppEvent("OpenPermissionsPopup")]


class Denials:
    def __init__(self, events) -> None:
        self._events = events

    def entries(self):
        return tuple(self._events)


class MutableDenials:
    def __init__(self, events) -> None:
        self._events = {event.id: event for event in events}

    def take(self, id):
        return self._events.pop(id, None)


class Tx:
    def __init__(self) -> None:
        self.events = []

    def send(self, event) -> None:
        self.events.append(event)


def test_open_auto_review_denials_popup_empty_and_nonempty_paths() -> None:
    widget = Widget()
    widget.review = SimpleNamespace(recent_auto_review_denials=Denials(()))

    assert open_auto_review_denials_popup(widget) is None
    assert widget.info_messages[0][0] == "No recent auto-review denials in this thread."

    event = SimpleNamespace(id="d1", action="rm -rf", rationale=None)
    widget.review = SimpleNamespace(recent_auto_review_denials=Denials((event,)))
    params = open_auto_review_denials_popup(widget)

    assert params is not None
    assert params.title == "Auto-review Denials"
    assert params.is_searchable is True
    assert params.items[0].is_disabled is True
    assert params.items[1].actions == [
        AppEvent("ApproveRecentAutoReviewDenial", {"thread_id": "thread-1", "id": "d1"})
    ]
    assert widget.redraws == 1


def test_approve_recent_auto_review_denial_consumes_event_and_reports_missing() -> None:
    # Rust parity: approve_recent_auto_review_denial removes the denial, submits the
    # approval op, and reports an error when the id is stale.
    widget = Widget()
    widget.app_event_tx = Tx()
    denial = SimpleNamespace(id="d1", action="rm -rf", rationale="unsafe")
    widget.review = SimpleNamespace(recent_auto_review_denials=MutableDenials((denial,)))

    events = approve_recent_auto_review_denial(widget, "thread-1", "d1")

    assert events == widget.app_event_tx.events
    assert events == [
        AppEvent(
            "SubmitThreadOp",
            {
                "thread_id": "thread-1",
                    "op": AppCommand.approve_guardian_denied_action(denial),
            },
        )
    ]
    assert widget.info_messages[-1][0] == (
        "Approval recorded for one retry of the selected auto-review denial."
    )

    assert approve_recent_auto_review_denial(widget, "thread-1", "d1") is None
    assert widget.error_messages[-1] == "That auto-review denial is no longer available."
