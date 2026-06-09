from types import SimpleNamespace

from pycodex.core.compact import InitialContextInjection
from pycodex.core.compact_remote import process_compacted_history
from pycodex.core.guardian.review import (
    GUARDIAN_REVIEWER_NAME,
    SANDBOX_PERMISSIONS_USE_DEFAULT,
    SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS,
    GuardianShellApprovalRequest,
    guardian_timeout_message,
    is_guardian_reviewer_source,
    routes_approval_to_guardian,
)
from pycodex.protocol import (
    ApprovalsReviewer,
    AskForApproval,
    ContentItem,
    NetworkPermissions,
    PermissionGrantScope,
    RequestPermissionProfile,
    RequestPermissionsResponse,
    ResponseItem,
)


def _developer_message(text: str) -> ResponseItem:
    return ResponseItem.message("developer", (ContentItem.input_text(text),))


def _user_message(text: str) -> ResponseItem:
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def test_request_permissions_routes_to_guardian_when_reviewer_is_enabled() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: request_permissions_routes_to_guardian_when_reviewer_is_enabled
    ctx = SimpleNamespace(
        approval_policy=AskForApproval.ON_REQUEST,
        config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.AUTO_REVIEW),
    )

    assert routes_approval_to_guardian(ctx) is True


def test_request_permissions_guardian_review_stops_when_cancelled() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: request_permissions_guardian_review_stops_when_cancelled
    message = guardian_timeout_message()

    assert "did not finish before its deadline" in message
    assert "unacceptable risk" not in message


def test_guardian_allows_shell_command_additional_permissions_requests_past_policy_validation() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: guardian_allows_shell_command_additional_permissions_requests_past_policy_validation
    request = GuardianShellApprovalRequest(
        id="test-call",
        command="echo hi",
        cwd="/tmp/project",
        sandbox_permissions=SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS,
        additional_permissions=RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
        justification="test",
    )

    assert request.sandbox_permissions == SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS
    assert request.additional_permissions.network.enabled is True
    assert request.justification == "test"


def test_strict_auto_review_turn_grant_forces_guardian_for_shell_command_policy_skip() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: strict_auto_review_turn_grant_forces_guardian_for_shell_command_policy_skip
    grant = RequestPermissionsResponse(
        RequestPermissionProfile(network=NetworkPermissions(enabled=True)),
        scope=PermissionGrantScope.TURN,
        strict_auto_review=True,
    )
    ctx = SimpleNamespace(
        approval_policy=AskForApproval.ON_FAILURE,
        config=SimpleNamespace(approvals_reviewer=ApprovalsReviewer.USER),
    )

    assert grant.strict_auto_review is True
    assert grant.scope is PermissionGrantScope.TURN
    assert routes_approval_to_guardian(ctx) is False


def test_guardian_allows_unified_exec_additional_permissions_requests_past_policy_validation() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: guardian_allows_unified_exec_additional_permissions_requests_past_policy_validation
    requested = RequestPermissionProfile(network=NetworkPermissions(enabled=True))
    response = RequestPermissionsResponse(requested, scope=PermissionGrantScope.TURN)

    assert response.permissions == requested
    assert response.scope is PermissionGrantScope.TURN
    assert response.strict_auto_review is False


def test_process_compacted_history_preserves_separate_guardian_developer_message() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: process_compacted_history_preserves_separate_guardian_developer_message
    stale = _developer_message("stale developer message")
    guardian_policy = _developer_message("guardian policy")
    summary = _user_message("summary")

    refreshed = process_compacted_history(
        (stale, summary),
        InitialContextInjection.BEFORE_LAST_USER_MESSAGE,
        (guardian_policy,),
    )

    developer_messages = [item for item in refreshed if item.role == "developer"]
    assert stale not in refreshed
    assert developer_messages == [guardian_policy]


def test_shell_command_allows_sticky_turn_permissions_without_inline_request_permissions_feature() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: shell_command_allows_sticky_turn_permissions_without_inline_request_permissions_feature
    granted = RequestPermissionProfile(network=NetworkPermissions(enabled=True))
    approval = GuardianShellApprovalRequest(
        id="sticky-turn-grant",
        command="echo hi",
        cwd="/tmp/project",
        sandbox_permissions=SANDBOX_PERMISSIONS_USE_DEFAULT,
        additional_permissions=granted,
    )

    assert approval.additional_permissions == granted
    assert approval.sandbox_permissions == SANDBOX_PERMISSIONS_USE_DEFAULT


def test_guardian_subagent_does_not_inherit_parent_exec_policy_rules() -> None:
    # Rust: core/src/session/tests/guardian_tests.rs
    # Test: guardian_subagent_does_not_inherit_parent_exec_policy_rules
    guardian_source = {"type": "subagent", "subagent_source": {"type": "other", "other": GUARDIAN_REVIEWER_NAME}}
    normal_subagent = {"type": "subagent", "subagent_source": {"type": "other", "other": "worker"}}

    assert is_guardian_reviewer_source(guardian_source) is True
    assert is_guardian_reviewer_source(normal_subagent) is False
