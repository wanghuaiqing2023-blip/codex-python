from pycodex.tui.chatwidget.permissions_menu import (
    AUTO_REVIEW_DESCRIPTION,
    ApprovalPreset,
    CustomPermissionProfileSummary,
    PermissionMenuConfig,
    TerminalPermissionsPopupController,
    builtin_approval_presets,
    open_permission_profiles_popup,
    permission_profile_selection_item,
)
from types import SimpleNamespace
from pycodex.protocol import ActivePermissionProfile


def test_permission_profiles_popup_orders_builtin_items_and_strips_default_suffix() -> None:
    # Rust parity: ChatWidget::open_permission_profiles_popup builtin item construction.
    result = open_permission_profiles_popup(PermissionMenuConfig(active_profile_id=":workspace"))

    assert result.errors == []
    assert result.view is not None
    assert result.view.title == "Update Model Permissions"
    assert [item.name for item in result.view.items] == ["Default", "Full Access", "Read Only"]
    assert result.view.items[0].description is not None
    assert "(Identical to Agent mode)" not in result.view.items[0].description
    assert result.view.items[0].is_current
    selection = result.view.items[0].actions[0].selection
    assert selection.profile_id == ":workspace"
    assert selection.approval_policy == "on-request"
    assert selection.approvals_reviewer == "user"
    assert selection.display_label == "Default"
    full_access = result.view.items[1].actions[0].selection
    assert full_access.profile_id == ":danger-no-sandbox"
    assert full_access.approval_policy == "never"


def test_permission_profiles_popup_includes_auto_review_when_guardian_enabled() -> None:
    # Rust parity: GuardianApproval inserts Auto-review after Default with workspace profile id.
    result = open_permission_profiles_popup(
        PermissionMenuConfig(
            active_profile_id=":workspace",
            approval_policy="on-request",
            approvals_reviewer="auto-review",
            guardian_approval_enabled=True,
        )
    )

    assert result.view is not None
    assert [item.name for item in result.view.items[:2]] == ["Default", "Auto-review"]
    auto_review = result.view.items[1]
    assert auto_review.description == AUTO_REVIEW_DESCRIPTION
    assert auto_review.is_current
    assert auto_review.actions[0].selection.profile_id == ":workspace"
    assert auto_review.actions[0].selection.approvals_reviewer == "auto-review"


def test_permission_profiles_popup_appends_custom_profiles_with_default_description() -> None:
    # Rust parity: custom permission profiles are appended after builtins.
    result = open_permission_profiles_popup(
        PermissionMenuConfig(
            active_profile_id="locked-down",
            custom_permission_profiles=(
                CustomPermissionProfileSummary(id="locked-down", description=None),
                CustomPermissionProfileSummary(id="team", description="Team profile."),
            ),
        )
    )

    assert result.view is not None
    names = [item.name for item in result.view.items]
    assert names[-2:] == ["locked-down", "team"]
    locked_down = result.view.items[-2]
    assert locked_down.description == "Configured permission profile."
    assert locked_down.is_current
    assert locked_down.actions[0].selection.profile_id == "locked-down"
    assert locked_down.actions[0].selection.approval_policy is None


def test_missing_required_builtin_preset_returns_internal_error() -> None:
    # Rust parity: open_permission_profiles_popup emits a specific internal error and returns.
    presets = [preset for preset in builtin_approval_presets() if preset.id != "auto"]
    result = open_permission_profiles_popup(PermissionMenuConfig(), presets=presets)

    assert result.view is None
    assert result.errors == ["Internal error: missing the 'auto' approval preset."]


def test_builtin_disabled_reason_prefers_profile_id_then_preset_id() -> None:
    # Rust parity: builtin item surfaces can_set errors as disabled_reason.
    result = open_permission_profiles_popup(
        PermissionMenuConfig(disabled_reasons={":read-only": "blocked"})
    )

    assert result.view is not None
    read_only = result.view.items[-1]
    assert read_only.name == "Read Only"
    assert read_only.disabled_reason == "blocked"

    fallback = open_permission_profiles_popup(
        PermissionMenuConfig(disabled_reasons={"read-only": "preset blocked"})
    )
    assert fallback.view is not None
    assert fallback.view.items[-1].disabled_reason == "preset blocked"


def test_permission_profile_selection_item_uses_id_as_display_label() -> None:
    # Rust parity: permission_profile_selection_item action payload uses id for display_label.
    item = permission_profile_selection_item("Label", "profile-id", "Description", "other")

    assert item.name == "Label"
    assert not item.is_current
    assert item.actions[0].selection.display_label == "profile-id"


def test_terminal_full_access_selection_opens_confirmation_with_remember_action() -> None:
    # Rust baseline 1c7832f: permission_popups::open_full_access_confirmation
    # distinguishes one-session acceptance from persisted acknowledgement.
    runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(session_config=SimpleNamespace()),
        chat_widget=SimpleNamespace(
            config=SimpleNamespace(),
            add_error_message=lambda _message: None,
        ),
    )
    controller = TerminalPermissionsPopupController(runtime)
    root = controller.open_view()
    assert root is not None
    full_access = next(item for item in root.items if item.name == "Full Access")

    transition = controller.handle_events(tuple(full_access.actions))

    assert transition is not None
    assert transition.next_view.header == "Enable full access?"
    remember = transition.next_view.items[1]
    assert remember.actions[0].kind == "confirm_permission_profile_remember"


def test_terminal_permissions_popup_reads_typed_active_profile_id() -> None:
    # Fixed Rust baseline 1c7832f: Config permissions expose an
    # ActivePermissionProfile; popup current-item matching uses its id.
    runtime = SimpleNamespace(
        active_thread_runtime=SimpleNamespace(
            active_permission_profile=ActivePermissionProfile.new(":workspace"),
            approval_policy="on-request",
            approvals_reviewer="user",
            session_config=SimpleNamespace(),
        ),
        chat_widget=SimpleNamespace(
            config=SimpleNamespace(),
            add_error_message=lambda _message: None,
        ),
    )

    view = TerminalPermissionsPopupController(runtime).open_view()

    assert view is not None
    assert next(item for item in view.items if item.name == "Default").is_current
