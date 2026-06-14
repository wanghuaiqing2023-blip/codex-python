from pycodex.tui.app.app_server_event_targets import (
    ServerNotificationThreadTarget,
    guardian_warning_notifications_route_to_threads,
    server_notification_thread_target,
    server_request_thread_id,
    test_thread_settings,
    thread_settings_updated_notifications_route_to_threads,
    warning_notifications_route_to_threads_when_thread_id_is_present,
    warning_notifications_without_threads_are_global,
)


THREAD_ID = "00000000-0000-0000-0000-000000000501"


def test_warning_notifications_without_threads_are_global_matches_rust() -> None:
    # Rust: codex-tui app/app_server_event_targets.rs
    assert warning_notifications_without_threads_are_global()


def test_warning_notifications_route_to_threads_when_thread_id_is_present_matches_rust() -> None:
    # Rust: warning_notifications_route_to_threads_when_thread_id_is_present
    assert warning_notifications_route_to_threads_when_thread_id_is_present()


def test_guardian_warning_notifications_route_to_threads_matches_rust() -> None:
    # Rust: guardian_warning_notifications_route_to_threads
    assert guardian_warning_notifications_route_to_threads()


def test_thread_settings_updated_notifications_route_to_threads_matches_rust() -> None:
    # Rust: thread_settings_updated_notifications_route_to_threads
    assert thread_settings_updated_notifications_route_to_threads()


def test_server_request_thread_id_extracts_only_supported_request_variants() -> None:
    assert (
        server_request_thread_id(
            {"CommandExecutionRequestApproval": {"thread_id": THREAD_ID}}
        )
        == THREAD_ID
    )
    assert (
        server_request_thread_id(
            {"DynamicToolCall": {"thread_id": "not-a-thread-id"}}
        )
        is None
    )
    assert server_request_thread_id({"ExecCommandApproval": {"thread_id": THREAD_ID}}) is None


def test_thread_started_reads_nested_thread_id() -> None:
    notification = {"ThreadStarted": {"thread": {"id": THREAD_ID}}}

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Thread(
        THREAD_ID
    )


def test_invalid_notification_thread_id_is_preserved() -> None:
    notification = {"ThreadClosed": {"thread_id": "bad-thread"}}

    assert server_notification_thread_target(
        notification
    ) == ServerNotificationThreadTarget.InvalidThreadId("bad-thread")


def test_global_notification_variants_are_global() -> None:
    notification = {"SkillsChanged": {"skills": []}}

    assert server_notification_thread_target(notification) == ServerNotificationThreadTarget.Global()


def test_object_shaped_requests_and_notifications_are_supported() -> None:
    class Params:
        thread_id = THREAD_ID

    class Request:
        type = "ToolRequestUserInput"
        params = Params()

    class Notification:
        type = "ThreadSettingsUpdated"
        notification = Params()

    assert server_request_thread_id(Request()) == THREAD_ID
    assert server_notification_thread_target(Notification()) == ServerNotificationThreadTarget.Thread(
        THREAD_ID
    )


def test_thread_settings_fixture_shape_matches_rust_fields() -> None:
    settings = test_thread_settings()

    assert settings["cwd"] == "/tmp/thread-settings"
    assert settings["model"] == "gpt-5.4"
    assert settings["effort"] == "high"
