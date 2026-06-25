from pycodex.tui.app.replay_filter import (
    ThreadBufferedEvent,
    ThreadEventSnapshot,
    event_is_notice,
    snapshot_has_pending_interactive_request,
)


def test_snapshot_has_pending_interactive_request_for_all_rust_request_variants():
    for kind in [
        "CommandExecutionRequestApproval",
        "FileChangeRequestApproval",
        "McpServerElicitationRequest",
        "PermissionsRequestApproval",
        "ToolRequestUserInput",
    ]:
        snapshot = ThreadEventSnapshot([ThreadBufferedEvent.request({"kind": kind})])
        assert snapshot_has_pending_interactive_request(snapshot) is True


def test_snapshot_has_pending_interactive_request_ignores_non_request_and_other_request():
    snapshot = ThreadEventSnapshot(
        [
            ThreadBufferedEvent.notification({"kind": "Warning"}),
            ThreadBufferedEvent.request({"kind": "OtherRequest"}),
        ]
    )
    assert snapshot_has_pending_interactive_request(snapshot) is False


def test_event_is_notice_for_warning_guardian_and_config_warnings():
    assert event_is_notice(ThreadBufferedEvent.notification({"kind": "Warning"})) is True
    assert event_is_notice(ThreadBufferedEvent.notification({"kind": "GuardianWarning"})) is True
    assert event_is_notice(ThreadBufferedEvent.notification({"kind": "ConfigWarning"})) is True


def test_event_is_notice_ignores_requests_and_other_notifications():
    assert event_is_notice(ThreadBufferedEvent.request({"kind": "ToolRequestUserInput"})) is False
    assert event_is_notice(ThreadBufferedEvent.notification({"kind": "TurnCompleted"})) is False


def test_dict_and_object_shaped_inputs_are_supported():
    class Request:
        kind = "ToolRequestUserInput"

    class Event:
        kind = "Request"
        payload = Request()

    assert snapshot_has_pending_interactive_request({"events": [Event()]}) is True
    assert event_is_notice({"kind": "Notification", "notification": {"kind": "Warning"}}) is True


def test_enum_like_payload_class_names_match_rust_variants():
    class PermissionsRequestApproval:
        pass

    class GuardianWarning:
        pass

    assert (
        snapshot_has_pending_interactive_request(
            ThreadEventSnapshot(
                [ThreadBufferedEvent.request(PermissionsRequestApproval())]
            )
        )
        is True
    )
    assert event_is_notice(ThreadBufferedEvent.notification(GuardianWarning())) is True
