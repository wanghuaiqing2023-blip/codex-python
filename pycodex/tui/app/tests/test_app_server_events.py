from __future__ import annotations

# Rust source: codex/codex-rs/tui/src/app/app_server_events.rs

from types import SimpleNamespace

from pycodex.tui.app.app_server_events import (
    PendingRequests,
    plan_app_server_event,
    plan_server_notification_event,
    plan_server_request_event,
    refresh_mcp_startup_expected_servers_from_config,
)
from pycodex.tui.app.app_server_requests import PendingAppServerRequests, ResolvedAppServerRequest
from pycodex.tui.chatwidget.protocol_requests import ServerRequest


def test_refresh_mcp_expected_servers_filters_enabled_config() -> None:
    config = SimpleNamespace(
        mcp_servers={
            "alpha": SimpleNamespace(enabled=True),
            "beta": SimpleNamespace(enabled=False),
            "gamma": SimpleNamespace(enabled=True),
        }
    )

    assert refresh_mcp_startup_expected_servers_from_config(config) == ["alpha", "gamma"]


def test_lagged_and_disconnected_event_plans() -> None:
    assert plan_app_server_event({"kind": "Lagged"}).actions == (
        "warn_lagged",
        "refresh_mcp_expected_servers",
        "finish_mcp_startup_after_lag",
    )
    disconnected = plan_app_server_event({"kind": "Disconnected", "message": "lost"})
    assert disconnected.actions == ("warn_disconnected", "add_error_message", "fatal_exit_request")
    assert disconnected.message == "lost"


def test_top_level_app_server_event_delegates_notification_and_request() -> None:
    """Rust codex-tui app::app_server_events::handle_app_server_event delegation branches."""

    notification = plan_app_server_event(
        {
            "kind": "ServerNotification",
            "notification": {"kind": "ThreadUpdated", "thread_id": "thread-b"},
        },
        primary_thread_id="thread-a",
    )
    request = plan_app_server_event(
        {
            "kind": "ServerRequest",
            "request": {"kind": "Approval", "thread_id": "thread-a"},
        },
        primary_thread_id="thread-a",
    )

    assert notification.actions == ("enqueue_thread_notification",)
    assert notification.thread_id == "thread-b"
    assert request.actions == ("enqueue_primary_thread_request",)
    assert request.thread_id == "thread-a"


def test_server_request_resolved_dismisses_pending_request_when_found() -> None:
    pending = PendingRequests(resolved={"req-1": "approval"})

    plan = plan_server_notification_event(
        {"kind": "ServerRequestResolved", "request_id": "req-1"},
        pending_requests=pending,
    )

    assert plan.actions == ("resolve_pending_request", "dismiss_app_server_request")
    assert plan.request == "approval"


def test_typed_server_request_uses_params_thread_and_preserves_numeric_request_id() -> None:
    # Fixed Rust commit 1c7832f: RequestId remains typed while
    # CommandExecutionRequestApprovalParams owns thread_id and approval_id.
    pending = PendingAppServerRequests()
    request = ServerRequest(
        "CommandExecutionRequestApproval",
        request_id=41,
        params={"thread_id": "thread-a", "item_id": "call-1", "approval_id": "approval-1"},
    )

    request_plan = plan_server_request_event(
        request,
        primary_thread_id="thread-a",
        pending_requests=pending,
    )
    resolved_plan = plan_server_notification_event(
        {"kind": "ServerRequestResolved", "request_id": 41},
        pending_requests=pending,
    )

    assert request_plan.actions == ("enqueue_primary_thread_request",)
    assert resolved_plan.actions == ("resolve_pending_request", "dismiss_app_server_request")
    assert resolved_plan.request == ResolvedAppServerRequest.ExecApproval("approval-1")


def test_special_notification_branches_short_circuit_global_routing() -> None:
    assert plan_server_notification_event({"kind": "McpServerStatusUpdated"}).actions == (
        "refresh_mcp_expected_servers",
    )
    assert plan_server_notification_event({"kind": "AccountRateLimitsUpdated"}).actions == (
        "update_rate_limit_snapshot",
    )
    assert plan_server_notification_event({"kind": "AccountUpdated"}).actions == ("update_account_state",)
    assert plan_server_notification_event({"kind": "ExternalAgentConfigImportCompleted"}).actions == (
        "refresh_in_memory_config_from_disk",
        "refresh_plugin_mentions",
        "reload_user_config",
        "fetch_plugins_list",
    )
    assert plan_server_notification_event({"kind": "AppListUpdated"}).actions == ("on_connectors_loaded",)


def test_thread_notification_routes_to_primary_or_named_thread() -> None:
    primary = plan_server_notification_event(
        {"kind": "ThreadUpdated", "thread_id": "thread-a"},
        primary_thread_id="thread-a",
    )
    other = plan_server_notification_event(
        {"kind": "ThreadUpdated", "thread_id": "thread-b"},
        primary_thread_id="thread-a",
    )
    global_plan = plan_server_notification_event({"kind": "GlobalNotice"})

    assert primary.actions == ("enqueue_primary_thread_notification",)
    assert other.actions == ("enqueue_thread_notification",)
    assert other.thread_id == "thread-b"
    assert global_plan.actions == ("handle_global_server_notification",)


def test_invalid_thread_notification_is_ignored_with_warning_plan() -> None:
    invalid = plan_server_notification_event({"kind": "ThreadUpdated", "thread_id": ""})

    assert invalid.actions == ("warn_invalid_thread_id",)
    assert invalid.thread_id == ""


def test_server_request_unsupported_threadless_and_thread_routing() -> None:
    unsupported = SimpleNamespace(request_id="req-1", message="unsupported")
    pending = PendingRequests(unsupported=unsupported)

    rejected = plan_server_request_event({"kind": "Approval", "thread_id": "thread-a"}, pending_requests=pending)
    threadless = plan_server_request_event({"kind": "Approval"})
    primary = plan_server_request_event({"kind": "Approval", "thread_id": "thread-a"}, primary_thread_id=None)
    other = plan_server_request_event({"kind": "Approval", "thread_id": "thread-b"}, primary_thread_id="thread-a")

    assert rejected.actions == ("warn_unsupported_request", "add_error_message", "reject_app_server_request")
    assert rejected.rejection == unsupported
    assert threadless.actions == ("warn_threadless_request",)
    assert primary.actions == ("enqueue_primary_thread_request",)
    assert other.actions == ("enqueue_thread_request",)
    assert other.thread_id == "thread-b"
