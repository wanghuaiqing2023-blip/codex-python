from pycodex.tui.chatwidget.protocol import ChatWidgetProtocolRuntime, ServerNotification


def test_protocol_turn_notifications_drive_status_streaming_and_ready_state() -> None:
    # Rust composition contract:
    # - chatwidget/protocol.rs routes TurnStarted, AgentMessageDelta, TurnCompleted.
    # - chatwidget/turn_runtime.rs::on_task_started marks the turn running.
    # - chatwidget/streaming.rs::on_agent_message_delta requests live redraw.
    # - chatwidget/status_surfaces.rs::run_state_status_text maps running to Working
    #   and idle to Ready.
    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))

    assert runtime.turn_lifecycle.last_turn_id == "turn-1"
    assert runtime.turn.bottom_pane.task_running is True
    assert runtime.streaming.task_running is True
    assert runtime.run_state_status_text() == "Working"

    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "hello\n"}))

    assert runtime.streaming.stream_controller is not None
    assert runtime.streaming.active_cell_kind == "streaming_agent_tail"
    assert runtime.streaming.redraw_requests >= 1

    runtime.handle(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "status": "Completed", "duration_ms": 1200}},
        )
    )

    assert runtime.turn.bottom_pane.task_running is False
    assert runtime.streaming.task_running is False
    assert runtime.run_state_status_text() == "Ready"
    assert runtime.assistant_text() == "hello"
    assert ("agent_message", "hello") in runtime.streaming.consolidation_events


def test_protocol_multiple_deltas_complete_as_one_streamed_message() -> None:
    # Source: Rust test
    # Rust crate: codex-tui
    # Rust module: chatwidget::{protocol,streaming,turn_runtime}
    # Rust test: status_and_layout.rs::deltas_then_same_final_message_are_rendered_snapshot
    # Contract: AgentMessageDelta chunks are ordered stream state, and
    # TurnCompleted finalizes the stream without duplicating the final answer
    # through the turn-completion last_agent_message path.
    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "Here is the "}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "result."}))

    assert runtime.assistant_text() == "Here is the result."
    assert runtime.streaming.stream_controller is not None
    assert runtime.run_state_status_text() == "Working"

    runtime.handle(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "status": "Completed", "duration_ms": 42}},
        )
    )

    assert runtime.run_state_status_text() == "Ready"
    assert runtime.assistant_text() == "Here is the result."
    assert runtime.streaming.consolidation_events == [("agent_message", "Here is the result.")]
    assert [
        item for item in runtime.turn.history if item.get("kind") == "agent_markdown"
    ] == []


def test_protocol_completion_without_deltas_does_not_invent_message() -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust module: chatwidget::protocol
    # Rust anchor: handle_turn_completed_notification calls
    # on_task_complete(/*last_agent_message*/ None, ...) for Completed turns.
    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "status": "Completed", "duration_ms": 42}},
        )
    )

    assert runtime.run_state_status_text() == "Ready"
    assert runtime.assistant_text() == ""
    assert runtime.streaming.consolidation_events == []
    assert [
        item for item in runtime.turn.history if item.get("kind") == "agent_markdown"
    ] == []


def test_protocol_command_execution_lifecycle_updates_runtime_state() -> None:
    # Source: Rust test
    # Rust crate: codex-tui
    # Rust modules: chatwidget::protocol and chatwidget::command_lifecycle
    # Rust test: app_server.rs::live_app_server_command_execution_strips_shell_wrapper
    # Contract: ItemStarted/ItemCompleted(CommandExecution) are routed into
    # command lifecycle state while the turn is running.
    runtime = ChatWidgetProtocolRuntime()
    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))

    runtime.handle(
        ServerNotification(
            "ItemStarted",
            {
                "turn_id": "turn-1",
                "item": {
                    "kind": "CommandExecution",
                    "id": "cmd-1",
                    "command": "Get-Content README.md",
                    "source": "Agent",
                    "status": "InProgress",
                    "command_actions": [],
                },
            },
        )
    )

    assert runtime.command_lifecycle.active_exec_cell is not None
    assert runtime.command_lifecycle.active_exec_cell.calls[0].call_id == "cmd-1"
    assert runtime.streaming.had_work_activity is True

    runtime.handle(
        ServerNotification(
            "ItemCompleted",
            {
                "turn_id": "turn-1",
                "item": {
                    "kind": "CommandExecution",
                    "id": "cmd-1",
                    "command": "Get-Content README.md",
                    "source": "Agent",
                    "status": "Completed",
                    "command_actions": [],
                    "aggregated_output": "README",
                    "exit_code": 0,
                    "duration_ms": 5,
                },
            },
        )
    )

    assert runtime.command_lifecycle.active_exec_cell is None
    assert len(runtime.command_lifecycle.history_cells) == 1
    assert runtime.command_lifecycle.history_cells[0].calls[0].output.aggregated_output == "README"


def test_protocol_non_retry_error_consolidates_streamed_answer_before_failure() -> None:
    # Source: Rust test
    # Rust crate: codex-tui
    # Rust modules: chatwidget::{protocol,streaming,turn_runtime}
    # Rust test: app_server.rs::live_app_server_failed_turn_consolidates_streamed_answer
    # Contract: a failed live turn preserves the already-streamed assistant
    # source via consolidation before the stream controller is cleared.
    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "```diff\n+ streamed patch\n```\n"}))
    assert runtime.streaming.stream_controller is not None

    runtime.handle(
        ServerNotification(
            "Error",
            {
                "turn_id": "turn-1",
                "will_retry": False,
                "error": {"message": "stream disconnected before completion", "codex_error_info": None},
            },
        )
    )

    assert runtime.streaming.stream_controller is None
    assert runtime.assistant_text() == "```diff\n+ streamed patch\n```"
    assert runtime.streaming.consolidation_events == [("agent_message", "```diff\n+ streamed patch\n```")]
    assert runtime.turn.bottom_pane.task_running is False
    assert {"kind": "error", "message": "stream disconnected before completion"} in runtime.turn.history


def test_protocol_rate_limit_error_consolidates_streamed_answer_like_on_error() -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::{protocol,turn_runtime}
    # Rust anchor: turn_runtime.rs::on_rate_limit_error routes Generic/UsageLimit
    # branches through on_error, which flushes the answer stream.
    runtime = ChatWidgetProtocolRuntime()
    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "partial rate limit answer"}))

    runtime.handle(
        ServerNotification(
            "Error",
            {
                "turn_id": "turn-1",
                "will_retry": False,
                "error": {"message": "rate limit", "codex_error_info": {"rate_limit_kind": "generic"}},
            },
        )
    )

    assert runtime.streaming.consolidation_events == [("agent_message", "partial rate limit answer")]
    assert {"kind": "error", "message": "rate limit"} in runtime.turn.history


def test_protocol_server_overloaded_error_does_not_consolidate_stream() -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::{protocol,turn_runtime}
    # Rust anchor: turn_runtime.rs::on_server_overloaded_error calls
    # finalize_turn directly, not flush_answer_stream_with_separator.
    runtime = ChatWidgetProtocolRuntime()
    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "partial overloaded answer"}))

    runtime.handle(
        ServerNotification(
            "Error",
            {
                "turn_id": "turn-1",
                "will_retry": False,
                "error": {"message": "busy", "codex_error_info": {"rate_limit_kind": "server_overloaded"}},
            },
        )
    )

    assert runtime.streaming.stream_controller is None
    assert runtime.streaming.consolidation_events == []
    assert {"kind": "warning", "message": "busy"} in runtime.turn.history


def test_protocol_cyber_policy_error_does_not_consolidate_stream() -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::{protocol,turn_runtime}
    # Rust anchor: turn_runtime.rs::on_cyber_policy_error calls finalize_turn
    # directly, not flush_answer_stream_with_separator.
    runtime = ChatWidgetProtocolRuntime()
    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "partial cyber answer"}))

    runtime.handle(
        ServerNotification(
            "Error",
            {
                "turn_id": "turn-1",
                "will_retry": False,
                "error": {"message": "blocked", "codex_error_info": {"cyber_policy": True}},
            },
        )
    )

    assert runtime.streaming.stream_controller is None
    assert runtime.streaming.consolidation_events == []
    assert {"kind": "cyber_policy_error"} in runtime.turn.history


def test_protocol_interrupted_turn_finalizes_without_stream_consolidation() -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::protocol and chatwidget::input_restore
    # Rust anchors:
    # - protocol.rs::handle_turn_completed_notification maps TurnStatus::Interrupted
    #   to on_interrupted_turn.
    # - input_restore.rs::on_interrupted_turn calls finalize_turn, not
    #   flush_answer_stream_with_separator.
    runtime = ChatWidgetProtocolRuntime()

    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-1"}}))
    runtime.handle(ServerNotification("AgentMessageDelta", {"delta": "partial answer"}))
    assert runtime.streaming.stream_controller is not None

    runtime.handle(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-1", "status": "Interrupted", "duration_ms": 10}},
        )
    )

    assert runtime.turn.bottom_pane.task_running is False
    assert runtime.streaming.task_running is False
    assert runtime.streaming.stream_controller is None
    assert runtime.streaming.consolidation_events == []
    assert runtime.assistant_text() == "partial answer"
    assert {
        "kind": "error",
        "message": (
            "Conversation interrupted - tell the model what to do differently. "
            "Something went wrong? Hit `/feedback` to report the issue."
        ),
    } in runtime.turn.history


def test_protocol_budget_limited_interrupted_turn_uses_budget_message() -> None:
    # Source: Rust source contract
    # Rust crate: codex-tui
    # Rust modules: chatwidget::protocol and chatwidget::turn_runtime
    # Rust anchors:
    # - protocol.rs takes the budget-limited flag from turn_lifecycle.
    # - turn_runtime.rs::interrupted_turn_message maps BudgetLimited to
    #   "Goal budget reached - the turn was stopped."
    runtime = ChatWidgetProtocolRuntime()
    runtime.handle(ServerNotification("TurnStarted", {"turn": {"id": "turn-budget"}}))
    runtime.turn_lifecycle.budget_limited.add("turn-budget")

    runtime.handle(
        ServerNotification(
            "TurnCompleted",
            {"turn": {"id": "turn-budget", "status": "Interrupted", "duration_ms": 10}},
        )
    )

    assert {"kind": "error", "message": "Goal budget reached - the turn was stopped."} in runtime.turn.history
    assert runtime.turn.bottom_pane.task_running is False
