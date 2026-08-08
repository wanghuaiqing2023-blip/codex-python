from __future__ import annotations

from types import SimpleNamespace

import pytest

from pycodex.app_server_protocol.account import RateLimitSnapshot, RateLimitWindow
from pycodex.protocol import CollaborationMode, CollaborationModeMask, ModeKind, Settings
from pycodex.tui.chatwidget.constructor import PLACEHOLDERS, SIDE_PLACEHOLDERS
from pycodex.tui.bottom_pane.footer import terminal_idle_footer_right_text_from_runtime
from pycodex.tui.history_cell.mcp import McpInventoryLoadingCell, line_text
from pycodex.tui.chatwidget.protocol import (
    ChatWidgetProtocolRuntime,
    ReplayKind,
    ServerNotification,
    ServerRequest,
    TerminalNotificationAction,
    TerminalNotificationEffectPlan,
    TerminalProtocolEventDispatcher,
    TurnStatus,
    agent_message_delta_from_notification,
    handle_item_started_notification,
    handle_server_notification,
    handle_turn_completed_notification,
    run_terminal_app_notification,
    run_terminal_notification,
    run_terminal_notification_action,
    run_terminal_notification_effect_plan,
    terminal_notification_action,
    terminal_notification_effect_plan,
    terminal_turn_close_effect_plan,
)
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, compose_rate_limit_data_many


def test_vim_toggle_uses_bound_bottom_pane_owner() -> None:
    runtime = ChatWidgetProtocolRuntime()
    calls: list[str] = []
    runtime.bind_vim_mode_toggle_sink(lambda: calls.append("toggle") or True)

    assert runtime.toggle_vim_mode_and_notify() == "Vim mode enabled."
    assert runtime.vim_enabled is True
    assert calls == ["toggle"]


def test_file_search_result_uses_bound_bottom_pane_owner_and_redraws() -> None:
    runtime = ChatWidgetProtocolRuntime()
    applied: list[tuple[str, list[object]]] = []
    runtime.bind_file_search_result_sink(
        lambda query, matches: applied.append((query, matches))
    )
    before_redraws = runtime.turn.redraw_requests

    matches = [{"path": "probe-alpha.md", "indices": [0, 1, 2]}]
    runtime.apply_file_search_result("pro", matches)

    assert applied == [("pro", matches)]
    assert runtime.turn.redraw_requests == before_redraws + 1


def test_mcp_inventory_loading_is_transient_and_type_guarded() -> None:
    """Rust ChatWidget clears MCP loading without committing it to history."""

    runtime = ChatWidgetProtocolRuntime()
    previous = object()
    runtime.set_active_history_cell(previous)
    loading = McpInventoryLoadingCell.new(False)

    runtime.begin_mcp_inventory_loading(loading)

    assert runtime.history == [previous]
    assert runtime.active_cell is loading
    assert runtime.transcript.active_cell is loading
    assert runtime.clear_mcp_inventory_loading() is True
    assert runtime.active_cell is None
    assert runtime.transcript.active_cell is None
    assert runtime.history == [previous]

    unrelated = object()
    runtime.set_active_history_cell(unrelated)
    assert runtime.clear_mcp_inventory_loading() is False
    assert runtime.active_cell is unrelated


def test_thread_rate_limits_notification_caches_display_snapshot_at_receipt() -> None:
    # Rust: codex-tui::chatwidget::rate_limits::ChatWidget::on_rate_limit_snapshot
    # converts the protocol RateLimitSnapshot with Local::now() before caching it.
    # This guards the real /side -> ThreadRateLimitsUpdated -> /status path.
    runtime = ChatWidgetProtocolRuntime()
    raw = RateLimitSnapshot(
        limit_id="codex-spark",
        limit_name="GPT-5.3-Codex-Spark",
        primary=RateLimitWindow(25, 300),
    )

    runtime.handle(ServerNotification("ThreadRateLimitsUpdated", {"rate_limits": raw}))

    cached = runtime.rate_limit_snapshots_by_limit_id["codex-spark"]
    assert isinstance(cached, RateLimitSnapshotDisplay)
    assert cached.limit_name == "GPT-5.3-Codex-Spark"
    assert cached.captured_at.tzinfo is not None
    assert cached.primary is not None
    assert cached.primary.used_percent == 25.0
    assert compose_rate_limit_data_many([cached], cached.captured_at).kind == "available"


def test_warning_notification_is_projected_to_terminal_history() -> None:
    """Rust ``ChatWidget::on_warning`` immediately inserts a warning cell."""

    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(ServerNotification("Warning", {"message": "compact warning"}))

    assert len(runtime.history) == 1
    assert line_text(runtime.history[0].display_lines(80)[0]) == "! compact warning"


def test_settled_mcp_startup_hides_stale_status_indicator() -> None:
    runtime = ChatWidgetProtocolRuntime()
    runtime.mcp_startup.set_mcp_startup_expected_servers(["delayed"])

    runtime.on_mcp_server_status_updated({"name": "delayed", "status": "starting"})
    assert runtime.turn.bottom_pane.task_running is True

    runtime.on_mcp_server_status_updated({"name": "delayed", "status": "ready"})
    assert runtime.turn.bottom_pane.task_running is False
    assert runtime.streaming.task_running is False
    assert runtime.streaming.status_indicator_visible is False


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
    # - Terminal product startup reads these ChatWidget fields instead of
    #   hard-coding a separate composer prompt.
    runtime = ChatWidgetProtocolRuntime()

    assert runtime.normal_placeholder_text in PLACEHOLDERS
    assert runtime.side_placeholder_text in SIDE_PLACEHOLDERS


def test_command_start_restores_shared_status_without_commentary_completion() -> None:
    # Rust chatwidget::{streaming,command_lifecycle}: a streamed commentary
    # tail hides Working, then command start restores the shared BottomPane
    # indicator even when no completed commentary item preceded the tool.
    runtime = ChatWidgetProtocolRuntime()
    handle_server_notification(
        runtime,
        ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}),
    )
    handle_server_notification(
        runtime,
        ServerNotification("AgentMessageDelta", {"delta": "I will check."}),
    )
    assert runtime.streaming.status_indicator_visible is False

    handle_server_notification(
        runtime,
        ServerNotification(
            "ItemStarted",
            {
                "turn_id": "turn-1",
                "item": {
                    "kind": "CommandExecution",
                    "id": "cmd-1",
                    "command": "echo ok",
                    "source": "Agent",
                    "status": "InProgress",
                },
            },
        ),
    )

    assert runtime.command_lifecycle.bottom_pane_task_running is True
    assert runtime.streaming.status_indicator_visible is True


def test_plan_item_completion_opens_rust_plan_implementation_view() -> None:
    # Rust chatwidget::{protocol,replay,turn_runtime,plan_implementation}:
    # a completed proposed Plan item in Plan mode opens the canonical bottom
    # pane selection view only after TurnCompleted.
    runtime = ChatWidgetProtocolRuntime()
    runtime.current_collaboration_mode = CollaborationMode(
        mode=ModeKind.DEFAULT,
        settings=Settings(model="gpt-test"),
    )
    runtime.active_collaboration_mask = CollaborationModeMask(
        name="Plan",
        mode=ModeKind.PLAN,
        model="gpt-test",
    )
    shown: list[object] = []
    runtime.bind_active_view_sink(shown.append)

    handle_server_notification(
        runtime,
        ServerNotification(
            "ItemCompleted",
            {"turn_id": "turn-1", "item": {"kind": "Plan", "text": "- inspect parser"}},
        ),
    )
    assert shown == []

    handle_server_notification(
        runtime,
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "status": "Completed"}},
        ),
    )

    assert len(shown) == 1
    assert shown[0].title == "Implement this plan?"
    assert [item.name for item in shown[0].items] == [
        "Yes, implement this plan",
        "Yes, clear context and implement",
        "No, stay in Plan mode",
    ]


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


def test_thread_goal_updated_notification_drives_footer_state() -> None:
    # Rust module chain:
    # app-server extension event sink -> chatwidget::protocol::ThreadGoalUpdated
    # -> chatwidget::goal_status -> bottom_pane::footer.  The footer must not
    # poll goal persistence or maintain a second Goal state machine.
    runtime = ChatWidgetProtocolRuntime()
    app_runtime = SimpleNamespace(chat_widget=runtime)
    goal = {
        "thread_id": "thread-1",
        "objective": "finish parity",
        "status": "active",
        "token_budget": 1_000,
        "tokens_used": 21,
        "time_used_seconds": 3,
        "created_at": 1,
        "updated_at": 2,
    }

    handle_server_notification(
        runtime,
        ServerNotification("ThreadGoalUpdated", {"turn_id": "turn-1", "goal": goal}),
        None,
    )
    assert terminal_idle_footer_right_text_from_runtime(app_runtime) == "Pursuing goal (21 / 1K)"

    handle_server_notification(
        runtime,
        ServerNotification("ThreadGoalUpdated", {"turn_id": None, "goal": {**goal, "status": "paused"}}),
        None,
    )
    assert terminal_idle_footer_right_text_from_runtime(app_runtime) == "Goal paused (/goal resume)"

    handle_server_notification(
        runtime,
        ServerNotification(
            "ThreadGoalUpdated",
            {"turn_id": "turn-2", "goal": {**goal, "status": "complete", "tokens_used": 35}},
        ),
        None,
    )
    assert terminal_idle_footer_right_text_from_runtime(app_runtime) == "Goal achieved (35 tokens)"


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


def test_terminal_notification_action_plans_scrollback_product_events() -> None:
    # Rust path: chatwidget::protocol owns server-notification dispatch.
    assistant = terminal_notification_action(
        ServerNotification("AgentMessageDelta", {"delta": "hello"})
    )
    assert assistant == TerminalNotificationAction(
        "assistant_delta",
        "hello",
    )

    started = terminal_notification_action(
        ServerNotification("ItemStarted", {"item": {"command": ["echo", "hi"]}})
    )
    assert started == TerminalNotificationAction(
        "structured_history",
        finalize_active_stream=True,
        ensure_turn_status=True,
    )

    completed = terminal_notification_action(
        ServerNotification("ItemCompleted", {"item": {"command": "rg needle"}})
    )
    assert completed == TerminalNotificationAction(
        "structured_history",
        finalize_active_stream=True,
    )

    patch_started = terminal_notification_action(
        ServerNotification("ItemStarted", {"item": {"kind": "FileChange", "changes": []}})
    )
    patch_completed = terminal_notification_action(
        ServerNotification("ItemCompleted", {"item": {"kind": "FileChange", "status": "Completed"}})
    )
    assert patch_started == TerminalNotificationAction("noop")
    assert patch_completed == TerminalNotificationAction("noop")

    commentary = terminal_notification_action(
        ServerNotification(
            "ItemCompleted",
            {
                "item": {
                    "kind": "AgentMessage",
                    "phase": "Commentary",
                    "content": [{"type": "text", "text": "still working"}],
                }
            },
        )
    )
    assert commentary.restore_turn_status_after_action is True

    retry = terminal_notification_action(
        ServerNotification("Error", {"will_retry": True, "error": {"message": "retry"}})
    )
    assert retry == TerminalNotificationAction("noop")

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
        "assistant_completed": lambda text: record("assistant_completed", text),
        "turn_completed": lambda: record("turn_completed"),
    }

    run_terminal_notification_action(TerminalNotificationAction("assistant_delta", "hello"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("assistant_completed", "done"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("structured_history"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("turn_completed"), **callbacks)
    run_terminal_notification_action(TerminalNotificationAction("noop"), **callbacks)

    assert calls == [
        ("assistant", "hello", None),
        ("assistant_completed", "done", None),
        ("turn_completed", "", None),
    ]


def test_terminal_notification_effect_plan_resolves_terminal_state_rules() -> None:
    # Rust path: chatwidget::protocol owns notification dispatch semantics; the
    # terminal runner only applies the prepared terminal-state effects.
    action = TerminalNotificationAction(
        "structured_history",
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
        assistant_completed=lambda text: calls.append(("assistant_completed", text)),
    )

    assert action == TerminalNotificationAction(
        "structured_history",
        finalize_active_stream=True,
        ensure_turn_status=True,
    )
    assert calls == [("effect", "True")]


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
        assistant_completed=lambda text: calls.append(("assistant_completed", text)),
        project_status=lambda: calls.append(("project", "status")),
    )

    assert action == TerminalNotificationAction(
        "assistant_delta",
        "hello",
    )
    assert calls == [
        ("effect", "False"),
        ("app", "AgentMessageDelta"),
        ("assistant", "hello"),
        ("project", "status"),
    ]


def test_turn_completion_keeps_status_for_core_created_successor() -> None:
    # Rust module collaboration:
    # codex-core::tasks publishes TurnComplete and immediately schedules the
    # next active-goal turn; codex-tui must not render the transient idle state.
    calls: list[tuple[str, object]] = []

    def apply(plan: TerminalNotificationEffectPlan) -> None:
        calls.append(("effect", plan))

    action = run_terminal_app_notification(
        ServerNotification("TurnCompleted", {}),
        handle_notification=lambda event: calls.append(("app", event.kind)) or True,
        assistant_stream_active=True,
        apply_effect_plan=apply,
        assistant_delta=lambda _text: None,
        assistant_completed=lambda _text: None,
        project_status=lambda: calls.append(("project", "status")),
        immediate_follow_up_pending=lambda: True,
    )

    assert action.kind == "turn_completed"
    assert calls == [
        ("effect", TerminalNotificationEffectPlan(ensure_turn_status=True)),
        ("effect", TerminalNotificationEffectPlan(finalize_active_stream=True)),
        ("effect", TerminalNotificationEffectPlan(ensure_turn_status=True)),
        ("app", "TurnCompleted"),
    ]


def test_turn_completion_clears_status_without_successor() -> None:
    calls: list[tuple[str, object]] = []

    def apply(plan: TerminalNotificationEffectPlan) -> None:
        calls.append(("effect", plan))

    run_terminal_app_notification(
        ServerNotification("TurnCompleted", {}),
        handle_notification=lambda event: calls.append(("app", event.kind)) or False,
        assistant_stream_active=True,
        apply_effect_plan=apply,
        assistant_delta=lambda _text: None,
        assistant_completed=lambda _text: None,
        project_status=lambda: calls.append(("project", "status")),
    )

    assert calls == [
        ("effect", TerminalNotificationEffectPlan(finalize_active_stream=True)),
        ("app", "TurnCompleted"),
        (
            "effect",
            TerminalNotificationEffectPlan(
                clear_turn_status=True,
                clear_live_status=True,
            ),
        ),
        ("project", "status"),
    ]


def test_run_terminal_app_notification_surfaces_owner_dispatch_failures() -> None:
    # Rust owner failures must not be hidden by the terminal adapter.
    calls: list[tuple[str, str]] = []

    def fail_sync(event) -> None:
        calls.append(("app", "fail"))
        raise RuntimeError("unsupported")

    with pytest.raises(RuntimeError, match="unsupported"):
        run_terminal_app_notification(
            ServerNotification("ItemStarted", {"item": {"command": ["echo", "hi"]}}),
            handle_notification=fail_sync,
            assistant_stream_active=True,
            apply_effect_plan=lambda plan: calls.append(("effect", str(plan.finalize_active_stream))),
            assistant_delta=lambda text: calls.append(("assistant", text)),
            assistant_completed=lambda text: calls.append(("assistant_completed", text)),
            project_status=lambda: calls.append(("project", "status")),
        )
    assert calls == [("effect", "True"), ("app", "fail")]


def test_terminal_protocol_event_dispatcher_owns_effect_callbacks() -> None:
    # Rust owner: chatwidget/protocol.rs owns notification dispatch and
    # turn-close cleanup semantics.  Terminal runtime should wire callbacks
    # into this boundary instead of interpreting effect plans itself.
    calls: list[tuple[str, str]] = []
    active = [True]

    dispatcher = TerminalProtocolEventDispatcher(
        handle_notification=lambda event: calls.append(("app", event.kind)),
        handle_request=lambda event: calls.append(("request", event.kind)),
        assistant_stream_active=lambda: active[0],
        assistant_delta=lambda text: calls.append(("assistant", text)),
        assistant_completed=lambda text: calls.append(("assistant_completed", text)),
        project_status=lambda: calls.append(("project", "status")),
        suppress_turn_status=lambda: calls.append(("effect", "suppress")),
        clear_turn_status=lambda: calls.append(("effect", "clear_turn")),
        hide_live_status=lambda: calls.append(("effect", "hide_live")),
        clear_live_status=lambda: calls.append(("effect", "clear_live")),
        finalize_active_stream=lambda: calls.append(("effect", "finalize")),
        ensure_turn_status=lambda: calls.append(("effect", "ensure")),
        restore_turn_status=lambda: calls.append(("effect", "restore")),
    )

    action = dispatcher.handle_event(ServerNotification("AgentMessageDelta", {"delta": "hello"}))

    assert action == TerminalNotificationAction(
        "assistant_delta",
        "hello",
    )
    assert calls == [
        ("app", "AgentMessageDelta"),
        ("assistant", "hello"),
        ("project", "status"),
    ]

    calls.clear()
    request_action = dispatcher.handle_event(
        ServerRequest(
            "CommandExecutionRequestApproval",
            id="approval-1",
            params={"command": ["echo hi"]},
        )
    )

    assert request_action == TerminalNotificationAction("request")
    assert calls == [("request", "CommandExecutionRequestApproval")]

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


def test_protocol_runtime_renders_completed_mcp_tool_call() -> None:
    # Rust: chatwidget::protocol routes MCP item lifecycle through
    # chatwidget::tool_lifecycle and commits a completed MCP history cell.
    runtime = ChatWidgetProtocolRuntime()
    started = {
        "kind": "McpToolCall",
        "id": "call-github-login",
        "server": "codex_apps",
        "tool": "github_get_user_login",
        "arguments": {},
        "status": "InProgress",
    }
    completed = {
        **started,
        "status": "Completed",
        "durationMs": 7,
        "result": {
            "content": [{"type": "text", "text": "fixture-github-user"}],
        },
    }

    runtime.handle(ServerNotification("ItemStarted", {"item": started, "turn_id": "turn-1"}))
    runtime.handle(ServerNotification("ItemCompleted", {"item": completed, "turn_id": "turn-1"}))

    assert runtime.active_cell is None
    cell = runtime.history[-1]
    rendered = "\n".join(line_text(line) for line in cell.display_lines(120))
    assert "Called codex_apps.github_get_user_login({})" in rendered
    assert "fixture-github-user" in rendered


def test_protocol_runtime_renders_completed_web_search() -> None:
    # Rust: chatwidget::protocol routes WebSearch item lifecycle through
    # chatwidget::tool_lifecycle and commits the completed search history cell.
    runtime = ChatWidgetProtocolRuntime()
    started = {
        "kind": "WebSearch",
        "id": "web-search-1",
        "query": "",
        "status": "InProgress",
    }
    completed = {
        **started,
        "query": "pycodex deterministic web search marker",
        "status": "Completed",
        "action": {
            "type": "search",
            "query": "pycodex deterministic web search marker",
        },
    }

    runtime.handle(ServerNotification("ItemStarted", {"item": started, "turn_id": "turn-1"}))
    runtime.handle(ServerNotification("ItemCompleted", {"item": completed, "turn_id": "turn-1"}))

    assert runtime.active_cell is None
    rendered = "\n".join(line_text(line) for line in runtime.history[-1].display_lines(120))
    assert "Searched pycodex deterministic web search marker" in rendered


def test_protocol_runtime_renders_completed_image_generation(tmp_path) -> None:
    # Rust: chatwidget::protocol and chatwidget::replay route ImageGeneration
    # lifecycle through chatwidget::tool_lifecycle into a completed history cell.
    runtime = ChatWidgetProtocolRuntime()
    started = {
        "kind": "ImageGeneration",
        "id": "image-generation-1",
        "status": "InProgress",
    }
    completed = {
        **started,
        "status": "Completed",
        "revised_prompt": "A deterministic tiny orange cat icon",
        "saved_path": str(tmp_path / "generated.png"),
    }

    runtime.handle(ServerNotification("ItemStarted", {"item": started, "turn_id": "turn-1"}))
    runtime.handle(ServerNotification("ItemCompleted", {"item": completed, "turn_id": "turn-1"}))

    rendered = "\n".join(line_text(line) for line in runtime.history[-1].display_lines(120))
    assert "Generated Image:" in rendered
    assert "A deterministic tiny orange cat icon" in rendered
    assert "Saved to:" in rendered


def test_protocol_runtime_renders_completed_view_image(tmp_path) -> None:
    # Rust: chatwidget::replay routes ThreadItem::ImageView through
    # chatwidget::tool_lifecycle::on_view_image_tool_call.
    runtime = ChatWidgetProtocolRuntime()
    runtime.config.cwd = str(tmp_path)
    image_path = tmp_path / "tmp" / "pdfs" / "page-1.png"

    runtime.handle(
        ServerNotification(
            "ItemCompleted",
            {
                "item": {
                    "kind": "ImageView",
                    "id": "view-image-1",
                    "path": str(image_path),
                },
                "turn_id": "turn-1",
            },
        )
    )

    rendered = "\n".join(line_text(line) for line in runtime.history[-1].display_lines(120))
    assert "Viewed Image" in rendered
    assert "tmp/pdfs/page-1.png" in rendered


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
