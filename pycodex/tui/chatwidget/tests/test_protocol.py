from __future__ import annotations

from types import SimpleNamespace

from pycodex.tui.chatwidget.constructor import PLACEHOLDERS, SIDE_PLACEHOLDERS
from pycodex.tui.chatwidget.protocol import (
    ChatWidgetProtocolRuntime,
    ReplayKind,
    ServerNotification,
    TerminalNotificationAction,
    TerminalNotificationEffectPlan,
    TerminalProtocolEventDispatcher,
    TurnStatus,
    agent_message_delta_from_notification,
    handle_item_started_notification,
    handle_server_notification,
    handle_turn_completed_notification,
    retry_error_status_from_notification,
    run_terminal_app_notification,
    run_terminal_notification,
    run_terminal_notification_action,
    run_terminal_notification_effect_plan,
    terminal_notification_action,
    terminal_notification_effect_plan,
    terminal_turn_close_effect_plan,
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


def test_protocol_runtime_exposes_constructor_placeholder_fields() -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::constructor initializes
    #   normal_placeholder_text/side_placeholder_text from the Rust placeholder
    #   constant sets.
    # - Textual product startup reads these ChatWidget fields instead of
    #   hard-coding a separate composer prompt.
    runtime = ChatWidgetProtocolRuntime()

    assert runtime.normal_placeholder_text in PLACEHOLDERS
    assert runtime.side_placeholder_text in SIDE_PLACEHOLDERS


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


def test_agent_message_delta_from_notification_supports_payload_shapes() -> None:
    # Rust path: chatwidget::protocol forwards AgentMessageDelta.notification.delta.
    event = ServerNotification("AgentMessageDelta", {"delta": "hello"})
    payload = {"delta": "world"}
    object_payload = type("Payload", (), {"delta": "typed"})()
    empty = ServerNotification("AgentMessageDelta", {})

    assert agent_message_delta_from_notification(event) == "hello"
    assert agent_message_delta_from_notification(payload) == "world"
    assert agent_message_delta_from_notification(object_payload) == "typed"
    assert agent_message_delta_from_notification(empty) == ""


def test_retry_error_status_from_notification_matches_protocol_retry_route() -> None:
    # Rust path: chatwidget::protocol routes retry Error notifications into
    # the transient stream-error/status surface.
    retry = ServerNotification(
        "Error",
        {"will_retry": True, "error": {"message": "retrying", "additional_details": "slow"}},
    )
    fallback = ServerNotification("Error", {"will_retry": True, "error": {}})
    non_retry = ServerNotification("Error", {"will_retry": False, "error": {"message": "fatal"}})

    assert retry_error_status_from_notification(retry) == ("retrying", "slow")
    assert retry_error_status_from_notification(fallback) == ("Request failed", None)
    assert retry_error_status_from_notification(non_retry) is None


def test_terminal_notification_action_plans_scrollback_product_events() -> None:
    # Rust path: chatwidget::protocol owns server-notification dispatch.
    assistant = terminal_notification_action(
        ServerNotification("AgentMessageDelta", {"delta": "hello"})
    )
    assert assistant == TerminalNotificationAction(
        "assistant_delta",
        "hello",
        suppress_turn_status=True,
        hide_live_status=True,
    )

    started = terminal_notification_action(
        ServerNotification("ItemStarted", {"item": {"command": ["echo", "hi"]}})
    )
    assert started == TerminalNotificationAction(
        "command_started",
        "\u2022 Running echo hi",
        suppress_turn_status=True,
        clear_live_status=True,
        finalize_active_stream=True,
    )

    completed = terminal_notification_action(
        ServerNotification("ItemCompleted", {"item": {"command": "rg needle"}})
    )
    assert completed == TerminalNotificationAction(
        "command_completed",
        "\u2022 Ran rg needle",
        suppress_turn_status=True,
        clear_live_status=True,
        finalize_active_stream=True,
    )

    retry = terminal_notification_action(
        ServerNotification("Error", {"will_retry": True, "error": {"message": "retry"}})
    )
    assert retry == TerminalNotificationAction("retry_error", "retry", None, suppress_turn_status=True)

    turn_completed = terminal_notification_action(ServerNotification("TurnCompleted", {}))
    assert turn_completed == TerminalNotificationAction(
        "turn_completed",
        clear_turn_status=True,
        clear_live_status=True,
        finalize_active_stream=True,
    )

    assert terminal_notification_action(ServerNotification("Warning", {"message": "ignored"})) == TerminalNotificationAction(
        "noop"
    )


def test_run_terminal_notification_action_dispatches_protocol_actions() -> None:
    # Rust path: chatwidget::protocol owns terminal notification action
    # dispatch; the terminal runner provides the side-effect callbacks.
    calls: list[tuple[str, str, str | None]] = []

    def record(kind: str, text: str = "", details: str | None = None) -> None:
        calls.append((kind, text, details))

    callbacks = {
        "assistant_delta": lambda text: record("assistant", text),
        "command_started": lambda text: record("started", text),
        "command_completed": lambda text: record("completed", text),
        "retry_error": lambda text, details: record("retry", text, details),
        "turn_completed": lambda: record("turn_completed"),
    }

    run_terminal_notification_action(TerminalNotificationAction("assistant_delta", "hello"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("command_started", "\u2022 Running echo hi"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("command_completed", "\u2022 Ran rg x"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("retry_error", "retry", "slow"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("turn_completed"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("noop"), **callbacks)

    assert calls == [
        ("assistant", "hello", None),
        ("started", "\u2022 Running echo hi", None),
        ("completed", "\u2022 Ran rg x", None),
        ("retry", "retry", "slow"),
        ("turn_completed", "", None),
    ]


def test_terminal_notification_effect_plan_resolves_terminal_state_rules() -> None:
    # Rust path: chatwidget::protocol owns notification dispatch semantics; the
    # terminal runner only applies the prepared terminal-state effects.
    action = TerminalNotificationAction(
        "command_started",
        suppress_turn_status=True,
        clear_turn_status=True,
        hide_live_status=True,
        clear_live_status=True,
        finalize_active_stream=True,
    )

    assert terminal_notification_effect_plan(action, assistant_stream_active=True) == TerminalNotificationEffectPlan(
        suppress_turn_status=True,
        clear_turn_status=True,
        hide_live_status=True,
        clear_live_status=False,
        finalize_active_stream=True,
    )
    assert terminal_notification_effect_plan(action, assistant_stream_active=False).finalize_active_stream is False


def test_terminal_turn_close_effect_plan_matches_terminal_cleanup_boundary() -> None:
    # Rust path: chatwidget::protocol owns turn lifecycle completion semantics;
    # the terminal runner applies this cleanup when the app event stream closes
    # or fails before a TurnCompleted notification is observed.
    assert terminal_turn_close_effect_plan(assistant_stream_active=True) == TerminalNotificationEffectPlan(
        clear_turn_status=True,
        clear_live_status=True,
        finalize_active_stream=True,
    )
    assert terminal_turn_close_effect_plan(assistant_stream_active=False) == TerminalNotificationEffectPlan(
        clear_turn_status=True,
        clear_live_status=True,
        finalize_active_stream=False,
    )


def test_run_terminal_notification_effect_plan_applies_callbacks_in_protocol_order() -> None:
    # Rust path: chatwidget::protocol owns notification effect sequencing; the
    # terminal runner provides side-effect callbacks but does not interpret the
    # effect flags itself.
    calls: list[str] = []

    run_terminal_notification_effect_plan(
        TerminalNotificationEffectPlan(
            suppress_turn_status=True,
            clear_turn_status=True,
            hide_live_status=True,
            clear_live_status=True,
            finalize_active_stream=True,
        ),
        suppress_turn_status=lambda: calls.append("suppress"),
        clear_turn_status=lambda: calls.append("clear_turn"),
        hide_live_status=lambda: calls.append("hide_live"),
        clear_live_status=lambda: calls.append("clear_live"),
        finalize_active_stream=lambda: calls.append("finalize"),
    )

    assert calls == ["suppress", "clear_turn", "hide_live", "clear_live", "finalize"]


def test_run_terminal_notification_dispatches_effects_before_action() -> None:
    # Rust path: chatwidget::protocol owns notification dispatch sequencing;
    # terminal runtime provides side-effect callbacks without interpreting
    # action/effect planning itself.
    calls: list[tuple[str, str]] = []

    action = run_terminal_notification(
        ServerNotification("ItemStarted", {"item": {"command": ["echo", "hi"]}}),
        assistant_stream_active=True,
        apply_effect_plan=lambda plan: calls.append(("effect", str(plan.finalize_active_stream))),
        assistant_delta=lambda text: calls.append(("assistant", text)),
        command_started=lambda text: calls.append(("started", text)),
        command_completed=lambda text: calls.append(("completed", text)),
        retry_error=lambda text, details: calls.append(("retry", text)),
    )

    assert action == TerminalNotificationAction(
        "command_started",
        "\u2022 Running echo hi",
        suppress_turn_status=True,
        clear_live_status=True,
        finalize_active_stream=True,
    )
    assert calls == [("effect", "True"), ("started", "\u2022 Running echo hi")]


def test_run_terminal_app_notification_syncs_app_before_terminal_dispatch() -> None:
    # Rust path: chatwidget::protocol owns server-notification handling order.
    # The terminal runner supplies app synchronization and terminal callbacks.
    calls: list[tuple[str, str]] = []

    action = run_terminal_app_notification(
        ServerNotification("AgentMessageDelta", {"delta": "hello"}),
        handle_notification=lambda event: calls.append(("app", event.kind)),
        assistant_stream_active=False,
        apply_effect_plan=lambda plan: calls.append(("effect", str(plan.clear_live_status))),
        assistant_delta=lambda text: calls.append(("assistant", text)),
        command_started=lambda text: calls.append(("started", text)),
        command_completed=lambda text: calls.append(("completed", text)),
        retry_error=lambda text, details: calls.append(("retry", text)),
    )

    assert action == TerminalNotificationAction(
        "assistant_delta",
        "hello",
        suppress_turn_status=True,
        hide_live_status=True,
    )
    assert calls == [("app", "AgentMessageDelta"), ("effect", "False"), ("assistant", "hello")]


def test_run_terminal_app_notification_continues_when_app_sync_fails() -> None:
    # Terminal notification rendering must still progress if the app-runtime
    # compatibility sync rejects a notification shape.
    calls: list[tuple[str, str]] = []

    def fail_sync(event) -> None:
        calls.append(("app", "fail"))
        raise RuntimeError("unsupported")

    action = run_terminal_app_notification(
        ServerNotification("ItemStarted", {"item": {"command": ["echo", "hi"]}}),
        handle_notification=fail_sync,
        assistant_stream_active=True,
        apply_effect_plan=lambda plan: calls.append(("effect", str(plan.finalize_active_stream))),
        assistant_delta=lambda text: calls.append(("assistant", text)),
        command_started=lambda text: calls.append(("started", text)),
        command_completed=lambda text: calls.append(("completed", text)),
        retry_error=lambda text, details: calls.append(("retry", text)),
    )

    assert action.kind == "command_started"
    assert calls == [("app", "fail"), ("effect", "True"), ("started", "\u2022 Running echo hi")]


def test_terminal_protocol_event_dispatcher_owns_effect_callbacks() -> None:
    # Rust owner: chatwidget/protocol.rs owns notification dispatch and
    # turn-close cleanup semantics.  Terminal runtime should wire callbacks
    # into this boundary instead of interpreting effect plans itself.
    calls: list[tuple[str, str]] = []
    active = [True]

    dispatcher = TerminalProtocolEventDispatcher(
        handle_notification=lambda event: calls.append(("app", event.kind)),
        assistant_stream_active=lambda: active[0],
        assistant_delta=lambda text: calls.append(("assistant", text)),
        command_started=lambda text: calls.append(("started", text)),
        command_completed=lambda text: calls.append(("completed", text)),
        retry_error=lambda text, details: calls.append(("retry", text)),
        suppress_turn_status=lambda: calls.append(("effect", "suppress")),
        clear_turn_status=lambda: calls.append(("effect", "clear_turn")),
        hide_live_status=lambda: calls.append(("effect", "hide_live")),
        clear_live_status=lambda: calls.append(("effect", "clear_live")),
        finalize_active_stream=lambda: calls.append(("effect", "finalize")),
    )

    action = dispatcher.handle_event(ServerNotification("AgentMessageDelta", {"delta": "hello"}))

    assert action == TerminalNotificationAction(
        "assistant_delta",
        "hello",
        suppress_turn_status=True,
        hide_live_status=True,
    )
    assert calls == [
        ("app", "AgentMessageDelta"),
        ("effect", "suppress"),
        ("effect", "hide_live"),
        ("assistant", "hello"),
    ]

    calls.clear()
    dispatcher.close_turn()
    assert calls == [("effect", "clear_turn"), ("effect", "clear_live"), ("effect", "finalize")]

    active[0] = False
    calls.clear()
    dispatcher.close_turn()
    assert calls == [("effect", "clear_turn"), ("effect", "clear_live")]


def test_protocol_runtime_finalizes_reasoning_summary_on_turn_completed() -> None:
    # Rust parity:
    # - codex-tui::chatwidget::protocol routes ReasoningSummaryTextDelta into
    #   chatwidget::streaming::on_agent_reasoning_delta.
    # - chatwidget::streaming::on_agent_reasoning_final records a transcript
    #   reasoning summary block when the turn completes.
    runtime = ChatWidgetProtocolRuntime()
    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "t1"}}))
    runtime.handle(ServerNotification("ReasoningSummaryTextDelta", {"delta": "**Reading** files"}))
    runtime.handle(ServerNotification("ReasoningSummaryPartAdded", {}))
    runtime.handle(ServerNotification("ReasoningSummaryTextDelta", {"delta": "**Planning** answer"}))
    runtime.handle(ServerNotification("ReasoningTextDelta", {"delta": "raw hidden"}))
    runtime.handle(ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed", "duration_ms": 1}}))

    assert runtime.streaming.history == [("reasoning_summary", "**Reading** files\n\n**Planning** answer")]
    assert runtime.streaming.reasoning_buffer == ""
    assert runtime.streaming.full_reasoning_buffer == ""
    assert "raw hidden" not in runtime.streaming.history[0][1]


def test_protocol_runtime_completed_reasoning_item_uses_replay_final_callback() -> None:
    # Rust parity:
    # - codex-tui::chatwidget::protocol ItemCompleted dispatches thread items
    #   through chatwidget::replay::handle_thread_item.
    # - chatwidget::replay Reasoning items call on_agent_reasoning_final on the
    #   ChatWidget target, even for live completed items.
    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(
        ServerNotification(
            "ItemCompleted",
            {
                "item": {"kind": "Reasoning", "summary": ["**Reading** project"], "content": ["raw"]},
                "turn_id": "t1",
            },
        )
    )

    assert runtime.streaming.history == []
    assert runtime.streaming.reasoning_buffer == ""
    assert runtime.streaming.full_reasoning_buffer == ""


def test_protocol_runtime_raw_reasoning_delta_is_config_gated() -> None:
    # Rust parity: codex-tui::chatwidget::protocol only forwards
    # ReasoningTextDelta to streaming when show_raw_agent_reasoning is enabled.
    runtime = ChatWidgetProtocolRuntime()
    runtime.config.show_raw_agent_reasoning = True

    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "t1"}}))
    runtime.handle(ServerNotification("ReasoningTextDelta", {"delta": "raw visible"}))
    runtime.handle(ServerNotification("TurnCompleted", {"turn": {"id": "t1", "status": "Completed", "duration_ms": 1}}))

    assert runtime.streaming.history == [("reasoning_summary", "raw visible")]


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
