from pycodex.tui.app.app_server_event_targets import (
    ServerNotificationThreadTarget,
    server_notification_thread_target,
    server_request_thread_id,
    test_thread_settings as make_thread_settings,
)


def test_warning_notifications_without_threads_are_global():
    """Rust codex-tui app::app_server_event_targets::warning_notifications_without_threads_are_global."""

    notification = {"Warning": {"thread_id": None, "message": "warning"}}

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Global()


def test_warning_notifications_route_to_threads_when_thread_id_is_present():
    """Rust codex-tui app::app_server_event_targets::warning_notifications_route_to_threads_when_thread_id_is_present."""

    thread_id = "00000000-0000-0000-0000-000000000401"
    notification = {"Warning": {"thread_id": thread_id, "message": "warning"}}

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(thread_id)


def test_guardian_warning_notifications_route_to_threads():
    """Rust codex-tui app::app_server_event_targets::guardian_warning_notifications_route_to_threads."""

    thread_id = "00000000-0000-0000-0000-000000000402"
    notification = {"GuardianWarning": {"thread_id": thread_id, "message": "warning"}}

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(thread_id)


def test_thread_settings_updated_notifications_route_to_threads():
    """Rust codex-tui app::app_server_event_targets::thread_settings_updated_notifications_route_to_threads."""

    thread_id = "00000000-0000-0000-0000-000000000403"
    notification = {
        "ThreadSettingsUpdated": {
            "thread_id": thread_id,
            "thread_settings": make_thread_settings(),
        }
    }

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(thread_id)


def test_thread_started_notification_routes_from_nested_thread_id():
    """Rust codex-tui app::app_server_event_targets::ThreadStarted uses notification.thread.id."""

    thread_id = "00000000-0000-0000-0000-000000000407"
    notification = {
        "ThreadStarted": {
            "thread": {"id": thread_id},
        }
    }

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(thread_id)


def test_server_request_thread_id_accepts_thread_scoped_request_variants():
    """Rust codex-tui app::app_server_event_targets::server_request_thread_id scoped variants."""

    thread_id = "00000000-0000-0000-0000-000000000404"

    assert server_request_thread_id({"DynamicToolCall": {"thread_id": thread_id}}) == thread_id
    assert server_request_thread_id(
        {"type": "PermissionsRequestApproval", "params": {"thread_id": thread_id}}
    ) == thread_id


def test_server_request_thread_id_rejects_invalid_and_global_request_variants():
    """Rust codex-tui app::app_server_event_targets::server_request_thread_id None branches."""

    assert server_request_thread_id({"DynamicToolCall": {"thread_id": "not-a-thread-id"}}) is None
    assert server_request_thread_id({"ChatgptAuthTokensRefresh": {"thread_id": "00000000-0000-0000-0000-000000000405"}}) is None
    assert server_request_thread_id({"ExecCommandApproval": {"thread_id": "00000000-0000-0000-0000-000000000406"}}) is None


def test_invalid_notification_thread_id_is_reported_not_global():
    """Rust codex-tui app::app_server_event_targets::ServerNotificationThreadTarget::InvalidThreadId."""

    target = server_notification_thread_target(
        {"ThreadSettingsUpdated": {"thread_id": "not-a-thread-id", "thread_settings": make_thread_settings()}}
    )

    assert target == ServerNotificationThreadTarget.InvalidThreadId("not-a-thread-id")
