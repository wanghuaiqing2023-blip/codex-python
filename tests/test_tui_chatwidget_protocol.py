from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.protocol import (
    ReplayKind,
    ServerNotification,
    TurnStatus,
    handle_item_started_notification,
    handle_server_notification,
    handle_turn_completed_notification,
)


class Lifecycle:
    def __init__(self) -> None:
        self.last_turn_id = None
        self.budget_limited = set()

    def take_budget_limited(self, turn_id: str) -> bool:
        if turn_id in self.budget_limited:
            self.budget_limited.remove(turn_id)
            return True
        return False


class Widget:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.active_side_conversation = False
        self.config = SimpleNamespace(show_raw_agent_reasoning=False)
        self.turn_lifecycle = Lifecycle()
        self.last_non_retry_error = None
        self.last_rendered_user_message_display = "prompt"

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder

    def handle_thread_item(self, item, turn_id, source) -> None:
        self.events.append(("handle_thread_item", item, turn_id, source.is_replay()))


def test_handle_server_notification_turn_started_sets_turn_id_and_skips_resume_start() -> None:
    widget = Widget()

    handle_server_notification(widget, ServerNotification("TurnStarted", {"turn": {"id": "t1"}}), None)

    assert widget.turn_lifecycle.last_turn_id == "t1"
    assert widget.last_non_retry_error is None
    assert ("on_task_started",) in widget.events

    widget = Widget()
    handle_server_notification(
        widget,
        ServerNotification("TurnStarted", {"turn": {"id": "t2"}}),
        ReplayKind.RESUME_INITIAL_MESSAGES,
    )
    assert widget.turn_lifecycle.last_turn_id == "t2"
    assert ("on_task_started",) not in widget.events


def test_thread_token_usage_updated_maps_app_server_usage_to_token_info() -> None:
    widget = Widget()

    handle_server_notification(
        widget,
        ServerNotification(
            "ThreadTokenUsageUpdated",
            {
                "token_usage": {
                    "total": {
                        "total_tokens": 100,
                        "input_tokens": 60,
                        "cached_input_tokens": 10,
                        "output_tokens": 30,
                        "reasoning_output_tokens": 5,
                    },
                    "last": {
                        "total_tokens": 20,
                        "input_tokens": 12,
                        "cached_input_tokens": 2,
                        "output_tokens": 8,
                        "reasoning_output_tokens": 1,
                    },
                    "model_context_window": 200000,
                }
            },
        ),
        None,
    )

    _, token_info = widget.events[-1]
    assert token_info.total_token_usage.total_tokens == 100
    assert token_info.total_token_usage.input_tokens == 60
    assert token_info.total_token_usage.cached_input_tokens == 10
    assert token_info.total_token_usage.output_tokens == 30
    assert token_info.total_token_usage.reasoning_output_tokens == 5
    assert token_info.last_token_usage.total_tokens == 20
    assert token_info.last_token_usage.input_tokens == 12
    assert token_info.last_token_usage.cached_input_tokens == 2
    assert token_info.last_token_usage.output_tokens == 8
    assert token_info.last_token_usage.reasoning_output_tokens == 1
    assert token_info.model_context_window == 200000


def test_handle_turn_completed_completed_interrupted_and_failed_paths() -> None:
    widget = Widget()
    handle_turn_completed_notification(widget, {"turn": {"id": "t1", "status": TurnStatus.COMPLETED, "duration_ms": 10}}, None)
    assert widget.last_rendered_user_message_display is None
    assert ("on_task_complete", None, 10, False) in widget.events

    widget = Widget()
    widget.turn_lifecycle.budget_limited.add("t2")
    handle_turn_completed_notification(widget, {"turn": {"id": "t2", "status": TurnStatus.INTERRUPTED}}, None)
    assert ("on_interrupted_turn", "BudgetLimited") in widget.events

    widget = Widget()
    error = {"message": "boom", "codex_error_info": {"code": "x"}}
    handle_turn_completed_notification(widget, {"turn": {"id": "t3", "status": TurnStatus.FAILED, "error": error}}, None)
    assert ("handle_non_retry_error", "boom", {"code": "x"}) in widget.events

    widget = Widget()
    handle_turn_completed_notification(widget, {"turn": {"id": "t4", "status": TurnStatus.FAILED, "error": None}}, None)
    assert ("finalize_turn",) in widget.events
    assert ("request_redraw",) in widget.events
    assert ("maybe_send_next_queued_input",) in widget.events


def test_error_notification_retry_live_only_and_non_retry_records_error() -> None:
    widget = Widget()
    handle_server_notification(
        widget,
        ServerNotification("Error", {"will_retry": True, "error": {"message": "retry", "additional_details": "d"}}),
        None,
    )
    assert ("on_stream_error", "retry", "d") in widget.events

    widget = Widget()
    handle_server_notification(
        widget,
        ServerNotification("Error", {"will_retry": True, "error": {"message": "retry"}}),
        ReplayKind.OTHER,
    )
    assert widget.events == []

    widget = Widget()
    handle_server_notification(
        widget,
        ServerNotification("Error", {"turn_id": "t", "will_retry": False, "error": {"message": "bad", "codex_error_info": None}}),
        None,
    )
    assert widget.last_non_retry_error == ("t", "bad")
    assert ("handle_non_retry_error", "bad", None) in widget.events


def test_reasoning_raw_delta_obeys_config_and_completed_item_uses_replay_source() -> None:
    widget = Widget()
    handle_server_notification(widget, ServerNotification("ReasoningTextDelta", {"delta": "raw"}), None)
    assert widget.events == [("restore_retry_status_header_if_present",)]

    widget = Widget()
    widget.config.show_raw_agent_reasoning = True
    handle_server_notification(widget, ServerNotification("ReasoningTextDelta", {"delta": "raw"}), None)
    assert ("on_agent_reasoning_delta", "raw") in widget.events

    widget = Widget()
    handle_server_notification(
        widget,
        ServerNotification("ItemCompleted", {"item": {"kind": "Plan"}, "turn_id": "t"}),
        ReplayKind.OTHER,
    )
    assert ("handle_thread_item", {"kind": "Plan"}, "t", True) in widget.events


def test_item_started_routes_replay_sensitive_review_and_tool_starts() -> None:
    widget = Widget()
    handle_item_started_notification(widget, {"item": {"kind": "EnteredReviewMode", "review": "r"}}, from_replay=False)
    assert ("enter_review_mode_with_hint", "r", False) in widget.events

    widget = Widget()
    handle_item_started_notification(widget, {"item": {"kind": "EnteredReviewMode", "review": "r"}}, from_replay=True)
    assert widget.events == []

    widget = Widget()
    handle_item_started_notification(widget, {"item": {"kind": "WebSearch", "id": "w"}}, from_replay=False)
    assert ("on_web_search_begin", "w") in widget.events


def test_side_conversation_suppresses_live_mcp_status_and_realtime_suppressed_during_replay() -> None:
    widget = Widget()
    widget.active_side_conversation = True
    handle_server_notification(widget, ServerNotification("McpServerStatusUpdated", {"status": "x"}), None)
    assert widget.events == []

    widget = Widget()
    handle_server_notification(widget, ServerNotification("ThreadRealtimeStarted", {"session": "s"}), ReplayKind.OTHER)
    assert widget.events == []

    handle_server_notification(widget, ServerNotification("ThreadRealtimeStarted", {"session": "s"}), None)
    assert ("on_realtime_conversation_started", {"session": "s"}) in widget.events
