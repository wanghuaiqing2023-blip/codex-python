from pycodex.protocol import EventMsg, WarningEvent
from pycodex.tui.app.runtime import _server_notifications_from_session_event


def test_compact_warning_session_event_reaches_chatwidget_notification() -> None:
    # Rust owners:
    # - codex-core::compact emits EventMsg::Warning after ContextCompaction.
    # - codex-tui::chatwidget handles EventMsg::Warning through on_warning.
    message = "Heads up: Long threads and multiple compactions"

    notifications = _server_notifications_from_session_event(
        EventMsg.with_payload("warning", WarningEvent(message)),
        thread_id="thread-1",
        turn_id="turn-compact",
    )

    assert len(notifications) == 1
    assert notifications[0].kind == "Warning"
    assert notifications[0].payload == {
        "thread_id": "thread-1",
        "turn_id": "turn-compact",
        "message": message,
    }
