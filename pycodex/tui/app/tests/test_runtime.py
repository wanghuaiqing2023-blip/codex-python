import asyncio
import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from pycodex.core.session.turn.runtime import UserTurnSamplingResult
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    CommandExecutionItem,
    ContentItem,
    FunctionCallOutputPayload,
    ResponseItem,
    ReviewTarget,
    TurnItem,
)
from pycodex.tui.app.runtime import (
    CoreExecActiveThreadRuntime,
    ExecFunctionActiveThreadRuntime,
    QueueActiveThreadEventStream,
    TuiAppRuntime,
    _server_notifications_from_session_event,
    app_command_for_prompt,
    exec_run_plan_for_app_command,
    user_inputs_for_app_command,
    user_turn_prompt,
)
from pycodex.tui.app.agent_navigation import AgentNavigationDirection
from pycodex.tui.app_command import AppCommand
from pycodex.tui.app_event import AppEvent, RateLimitRefreshOrigin
from pycodex.tui.chatwidget.protocol import ServerNotification
from pycodex.tui.status.card import new_status_output_with_rate_limits_handle
from pycodex.tui.status.rate_limits import RateLimitSnapshotDisplay, RateLimitWindowDisplay


def test_tui_app_runtime_submits_user_turn_through_active_thread_routing() -> None:
    # Rust composition contract:
    # - codex-tui::chatwidget::input_submission builds AppCommand::UserTurn.
    # - codex-tui::app::thread_routing submits active-thread ops via submit_thread_op.
    # - codex-tui::app event loop consumes active-thread notifications.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "pong\n")))

    stream = runtime.submit_user_turn("ping")

    assert runtime.submitted_ops[-1].kind == "UserTurn"
    assert user_turn_prompt(runtime.submitted_ops[-1]) == "ping"
    assert runtime.routing_plans[-1].action == "submit_thread_op"
    assert runtime.routing_plans[-1].app_server_call == (
        "submit_thread_op",
        {"thread_id": "primary", "op": runtime.submitted_ops[-1]},
    )

    notifications = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        notifications.append(event.kind)
        runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert notifications == ["TurnStarted", "AgentMessageDelta", "TurnCompleted"]
    assert runtime.chat_widget.run_state_status_text() == "Ready"
    assert runtime.chat_widget.assistant_text() == "pong"


def test_tui_app_runtime_submits_interrupt_without_empty_user_turn() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::interaction::on_ctrl_c submits
    #   AppCommand::Interrupt when work is cancellable and double-press quit is
    #   disabled.
    # - codex-tui::app::thread_routing routes non-UserTurn active-thread ops
    #   through the same submit_thread_op boundary.
    calls: list[tuple[str, AppCommand]] = []

    class Runtime:
        def submit_thread_op(self, thread_id: str, op: AppCommand):
            calls.append((thread_id, op))
            return ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unexpected")).submit_thread_op(thread_id, op)

    runtime = TuiAppRuntime(active_thread_runtime=Runtime())

    stream = runtime.submit_op(AppCommand.interrupt())

    assert calls == [("primary", AppCommand.interrupt())]
    assert runtime.submitted_ops == [AppCommand.interrupt()]
    assert runtime.routing_plans[-1].action == "submit_thread_op"
    assert stream.next_event(timeout=0.01) is None


def test_core_exec_active_thread_runtime_cleans_background_terminals_without_user_turn() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::slash_dispatch::SlashCommand::Stop submits
    #   AppCommand::CleanBackgroundTerminals.
    # - codex-tui::app::thread_routing forwards it to the active thread as
    #   Op::CleanBackgroundTerminals.
    # - codex-core::session::handlers::clean_background_terminals terminates
    #   unified exec processes; it is not a model UserTurn.
    calls: list[str] = []

    class Manager:
        def terminate_all_processes(self):
            calls.append("terminate_all_processes")
            return ()

    runtime = CoreExecActiveThreadRuntime(
        session_config=SimpleNamespace(services=SimpleNamespace(unified_exec_manager=Manager())),
        model_client=SimpleNamespace(),
        provider=SimpleNamespace(),
        model_info=SimpleNamespace(),
    )

    stream = runtime.submit_thread_op("primary", AppCommand.clean_background_terminals())

    assert calls == ["terminate_all_processes"]
    assert stream.next_event(timeout=0.01) is None


def test_core_exec_active_thread_runtime_lists_resume_threads_from_local_rollouts(tmp_path) -> None:
    # Rust-derived contract:
    # - codex-tui::chatwidget::slash_dispatch maps /resume to
    #   AppEvent::OpenResumePicker.
    # - codex-tui::resume_picker asks the app/runtime for prior sessions.
    # - codex-thread-store::local::list_threads reads rollout
    #   sessions/YYYY/MM/DD/rollout-<ts>-<uuid>.jsonl files whose first line is
    #   session_meta and whose user_message line supplies the preview.
    thread_id = "11111111-2222-4333-8444-555555555555"
    ts = "2025-01-03T10-11-12"
    day_dir = tmp_path / "sessions" / "2025" / "01" / "03"
    day_dir.mkdir(parents=True)
    rollout_path = day_dir / f"rollout-{ts}-{thread_id}.jsonl"
    rollout_path.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "timestamp": ts,
                        "type": "session_meta",
                        "payload": {
                            "id": thread_id,
                            "forked_from_id": None,
                            "timestamp": ts,
                            "cwd": str(tmp_path),
                            "originator": "test_originator",
                            "cli_version": "test_version",
                            "source": "cli",
                            "model_provider": "openai",
                            "git": {
                                "commit_hash": "abcdef",
                                "branch": "main",
                                "repository_url": "https://example.com/repo.git",
                            },
                        },
                    },
                    separators=(",", ":"),
                ),
                json.dumps(
                    {
                        "timestamp": ts,
                        "type": "event_msg",
                        "payload": {
                            "type": "user_message",
                            "message": "Seeded resume picker prompt",
                            "kind": "plain",
                        },
                    },
                    separators=(",", ":"),
                ),
            )
        )
        + "\n",
        encoding="utf-8",
    )
    runtime = CoreExecActiveThreadRuntime(
        session_config=SimpleNamespace(codex_home=tmp_path, default_model_provider_id="openai"),
        model_client=SimpleNamespace(),
        provider=SimpleNamespace(),
        model_info=SimpleNamespace(),
    )

    rows = runtime.list_resume_threads()

    assert len(rows) == 1
    assert str(rows[0].thread_id) == thread_id
    assert Path(rows[0].rollout_path) == rollout_path
    assert rows[0].preview == "Seeded resume picker prompt"
    assert rows[0].cwd == tmp_path


def test_core_exec_active_thread_runtime_message_history_metadata_lookup_and_append(tmp_path) -> None:
    # Rust-derived contract:
    # - codex-message-history::history_metadata returns the log id and line
    #   count for history.jsonl.
    # - codex-message-history::lookup returns HistoryEntry by log id + offset.
    # - codex-tui runtime uses this boundary for composer persistent history.
    runtime = CoreExecActiveThreadRuntime(
        session_config=SimpleNamespace(codex_home=tmp_path),
        model_client=SimpleNamespace(thread_id="thread-1"),
        provider=SimpleNamespace(),
        model_info=SimpleNamespace(),
        codex_home=tmp_path,
    )

    runtime.append_message_history_entry("first prompt")
    runtime.append_message_history_entry("second prompt")

    metadata = runtime.message_history_metadata()
    assert metadata is not None
    log_id, entry_count = metadata
    assert log_id != 0
    assert entry_count == 2
    assert runtime.lookup_message_history_entry("thread-1", log_id, 1).text == "second prompt"


def test_tui_app_runtime_syncs_message_history_metadata_from_active_runtime(tmp_path) -> None:
    # Rust source: codex-tui::app_server_session::thread_session_state_from_thread_response
    # computes MessageHistoryMetadata during session configuration and
    # chatwidget::session_flow installs it into bottom-pane history.
    active = CoreExecActiveThreadRuntime(
        session_config=SimpleNamespace(codex_home=tmp_path),
        model_client=SimpleNamespace(thread_id="thread-1"),
        provider=SimpleNamespace(),
        model_info=SimpleNamespace(),
        codex_home=tmp_path,
    )
    active.append_message_history_entry("seeded prompt")

    runtime = TuiAppRuntime(active, thread_id="thread-1")

    assert runtime.chat_widget.bottom_history_metadata is not None
    thread_id, log_id, entry_count = runtime.chat_widget.bottom_history_metadata
    assert thread_id == "thread-1"
    assert log_id != 0
    assert entry_count == 1


def test_tui_app_runtime_mcp_startup_notification_refreshes_expected_servers_before_widget() -> None:
    # Rust source/test contract:
    # - codex-tui::app::app_server_events::handle_server_notification_event
    #   refreshes MCP expected servers from config before forwarding
    #   ServerNotification::McpServerStatusUpdated to chatwidget.
    # - chatwidget/tests/mcp_startup.rs::app_server_mcp_startup_failure_renders_warning_history
    #   depends on the expected set to emit the final startup summary after all
    #   configured servers settle.
    active_runtime = SimpleNamespace(
        session_config=SimpleNamespace(
            mcp_servers={
                "alpha": SimpleNamespace(enabled=True),
                "beta": SimpleNamespace(enabled=True),
                "disabled": SimpleNamespace(enabled=False),
            }
        )
    )
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    plan = runtime.handle_app_server_event(
        {
            "kind": "ServerNotification",
            "notification": {"kind": "McpServerStatusUpdated", "name": "alpha", "status": "Starting"},
        }
    )

    assert plan.actions == ("refresh_mcp_expected_servers",)
    assert runtime.chat_widget.mcp_startup.expected_servers == {"alpha", "beta"}
    assert runtime.chat_widget.mcp_startup.status_header == "Booting MCP server: alpha"

    runtime.handle_app_server_event(
        {
            "kind": "ServerNotification",
            "notification": {
                "kind": "McpServerStatusUpdated",
                "name": "alpha",
                "status": "Failed",
                "error": "MCP client for `alpha` failed to start: handshake failed",
            },
        }
    )
    runtime.handle_app_server_event(
        {
            "kind": "ServerNotification",
            "notification": {"kind": "McpServerStatusUpdated", "name": "beta", "status": "Ready"},
        }
    )

    warnings = [entry["message"] for entry in runtime.chat_widget.turn.history if entry.get("kind") == "warning"]
    assert warnings == [
        "MCP client for `alpha` failed to start: handshake failed",
        "MCP startup incomplete (failed: alpha)",
    ]


def test_core_exec_active_thread_runtime_projects_configured_mcp_startup_events() -> None:
    # Rust source/test contract:
    # - codex-tui::app::App::run polls app_server.next_event during startup.
    # - codex-tui::app::app_server_events routes McpServerStatusUpdated
    #   through chatwidget::mcp_startup.
    # - chatwidget/tests/mcp_startup.rs::app_server_mcp_startup_failure_renders_warning_history
    #   proves configured startup failures are visible history/status content.
    runtime = CoreExecActiveThreadRuntime(
        session_config=SimpleNamespace(
            mcp_servers={
                "alpha": {"command": "cmd"},
                "disabled": {"command": "cmd", "enabled": False},
            }
        ),
        model_client=SimpleNamespace(),
        provider=SimpleNamespace(),
        model_info=SimpleNamespace(),
    )

    first = runtime.next_app_server_event(timeout=0)
    second = runtime.next_app_server_event(timeout=0)
    assert runtime.next_app_server_event(timeout=0) is None

    assert first == {
        "kind": "ServerNotification",
        "notification": ServerNotification("McpServerStatusUpdated", {"name": "alpha", "status": "Starting"}),
    }
    assert second is not None
    notification = second["notification"]
    assert notification.kind == "McpServerStatusUpdated"
    assert notification.payload["name"] == "alpha"
    assert notification.payload["status"] == "Failed"
    assert "MCP client for `alpha` failed to start" in notification.payload["error"]


def test_tui_app_runtime_update_model_event_updates_widget_and_session_config() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::model_popups::model_selection_actions emits
    #   AppEvent::UpdateModel before PersistModelSelection.
    # - codex-tui::app::event_dispatch handles UpdateModel by calling
    #   chat_widget.set_model and syncing the active-thread model setting.
    # - codex-tui::chatwidget::settings::set_model refreshes model-dependent
    #   surfaces including the session header/status surfaces.
    active_runtime = SimpleNamespace(model="gpt-old", session_config=SimpleNamespace(model="gpt-old"))
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    plan = runtime.handle_app_event(AppEvent.update_model("gpt-new"))

    assert plan.action == "update_model"
    assert runtime.chat_widget.selected_model == "gpt-new"
    assert runtime.chat_widget.config.model == "gpt-new"
    assert active_runtime.model == "gpt-new"
    assert active_runtime.session_config.model == "gpt-new"


def test_tui_app_runtime_update_reasoning_effort_event_updates_widget_and_session_config() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::model_popups::model_selection_actions emits
    #   AppEvent::UpdateReasoningEffort between UpdateModel and
    #   PersistModelSelection.
    # - codex-tui::app::config_persistence::on_update_reasoning_effort updates
    #   the app config and chat_widget reasoning setting.
    active_runtime = SimpleNamespace(
        model_reasoning_effort="medium",
        session_config=SimpleNamespace(model_reasoning_effort="medium"),
    )
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    plan = runtime.handle_app_event(AppEvent.update_reasoning_effort("high"))

    assert plan.action == "update_reasoning_effort"
    assert runtime.chat_widget.config.model_reasoning_effort == "high"
    assert active_runtime.model_reasoning_effort == "high"
    assert active_runtime.session_config.model_reasoning_effort == "high"


def test_tui_app_runtime_update_reasoning_effort_ignores_frozen_session_config_snapshot() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::model_popups::model_selection_actions emits
    #   AppEvent::UpdateReasoningEffort between UpdateModel and
    #   PersistModelSelection.
    # - codex-tui::app::event_dispatch updates live app/chatwidget state; a
    #   read-only session-config snapshot must not crash the TUI event path.
    @dataclass(frozen=True)
    class FrozenSessionConfig:
        model_reasoning_effort: str = "medium"
        reasoning_effort: str = "medium"

    active_runtime = SimpleNamespace(
        model_reasoning_effort="medium",
        session_config=FrozenSessionConfig(),
    )
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    plan = runtime.handle_app_event(AppEvent.update_reasoning_effort("high"))

    assert plan.action == "update_reasoning_effort"
    assert runtime.chat_widget.config.model_reasoning_effort == "high"
    assert active_runtime.model_reasoning_effort == "high"
    assert active_runtime.session_config.model_reasoning_effort == "medium"


def test_tui_app_runtime_diff_result_completes_chatwidget_diff_cell() -> None:
    # Rust source contract:
    # - codex-tui::chatwidget::slash_dispatch handles /diff locally by first
    #   calling add_diff_in_progress.
    # - codex-tui::app::event_dispatch applies AppEvent::DiffResult by
    #   completing that diff cell through ChatWidget::on_diff_complete.
    runtime = TuiAppRuntime(active_thread_runtime=SimpleNamespace())
    runtime.chat_widget.add_diff_in_progress()

    plan = runtime.handle_app_event(AppEvent.diff_result("diff --git a/a b/a\n"))

    assert plan.action == "diff_result"
    assert runtime.chat_widget.active_cell is None
    assert runtime.chat_widget.history[-1] == {"diff_complete": "diff --git a/a b/a\n"}


def test_tui_app_runtime_persist_model_selection_writes_config_batch_request() -> None:
    # Rust source/test contract:
    # - codex-tui::chatwidget::model_popups::model_selection_actions emits
    #   AppEvent::PersistModelSelection after AppEvent::UpdateModel.
    # - codex-tui::app::event_dispatch handles PersistModelSelection by calling
    #   config_update::write_config_batch(build_model_selection_edits(...)).
    requests = []

    class RequestHandle:
        def request_typed(self, request):
            requests.append(request)
            return SimpleNamespace(ok=True)

    active_runtime = SimpleNamespace(request_handle=RequestHandle())
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    plan = runtime.handle_app_event(AppEvent.persist_model_selection("gpt-new", "high"))

    assert plan.action == "persist_model_selection"
    assert len(requests) == 1
    assert requests[0].kind == "ConfigBatchWrite"
    edits = requests[0].params.edits
    assert [(edit.key_path, edit.value) for edit in edits] == [
        ("model", "gpt-new"),
        ("model_reasoning_effort", "high"),
    ]
    assert runtime.chat_widget.info_messages == [("Model changed to gpt-new high", None)]
    assert runtime.chat_widget.error_messages == []


def test_tui_app_runtime_persist_model_selection_falls_back_to_local_config(tmp_path) -> None:
    # Rust module boundary:
    # - Rust TUI persists through the app-server request handle.
    # - The Python terminal product path may run without that embedded
    #   app-server, so the runtime adapter uses the same core config edit
    #   contract against the resolved user config file.
    config = SimpleNamespace(codex_home=tmp_path, config_layer_stack=None)
    active_runtime = SimpleNamespace(session_config=config)
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    ok = runtime.persist_model_selection("gpt-local", "medium")

    assert ok is True
    text = (tmp_path / "config.toml").read_text(encoding="utf-8")
    assert 'model = "gpt-local"' in text
    assert 'model_reasoning_effort = "medium"' in text
    assert runtime.chat_widget.info_messages == [("Model changed to gpt-local medium", None)]


def test_tui_app_runtime_persist_model_selection_reports_write_failure() -> None:
    # Rust source contract:
    # codex-tui::app::event_dispatch logs failure and adds
    # "Failed to save default model: {err}" to chatwidget errors.
    class RequestHandle:
        def request_typed(self, _request):
            raise RuntimeError("disk denied")

    runtime = TuiAppRuntime(active_thread_runtime=SimpleNamespace(request_handle=RequestHandle()))

    ok = runtime.persist_model_selection("gpt-new", None)

    assert ok is False
    assert runtime.chat_widget.info_messages == []
    assert runtime.chat_widget.error_messages == ["Failed to save default model: disk denied"]


def test_tui_app_runtime_persist_model_selection_suppresses_auto_reasoning_label() -> None:
    # Rust source contract:
    # codex-tui::app::config_persistence::reasoning_label_for returns None for
    # codex-auto-* models, so PersistModelSelection reports only model changed.
    requests = []

    class RequestHandle:
        def request_typed(self, request):
            requests.append(request)
            return SimpleNamespace(ok=True)

    runtime = TuiAppRuntime(active_thread_runtime=SimpleNamespace(request_handle=RequestHandle()))

    ok = runtime.persist_model_selection("codex-auto-5", "high")

    assert ok is True
    assert runtime.chat_widget.info_messages == [("Model changed to codex-auto-5", None)]


def test_tui_app_runtime_shutdown_uses_shutdown_boundary_without_submitting_op() -> None:
    # Rust source/test contract:
    # - codex-tui::app::event_dispatch::handle_exit_mode(ShutdownFirst) calls
    #   shutdown_current_thread and then exits.
    # - codex-rs/tui/src/app/tests.rs::
    #   shutdown_first_exit_uses_app_server_shutdown_without_submitting_op
    #   asserts shutdown does not submit Op::Shutdown through the active op
    #   channel.
    calls: list[str] = []
    submitted_ops: list[AppCommand] = []

    class Runtime:
        def submit_thread_op(self, thread_id: str, op: AppCommand) -> QueueActiveThreadEventStream:
            submitted_ops.append(op)
            return ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unexpected")).submit_thread_op(thread_id, op)

        def shutdown_thread(self, thread_id: str) -> QueueActiveThreadEventStream:
            calls.append(thread_id)
            return ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")).shutdown_thread(thread_id)

    runtime = TuiAppRuntime(active_thread_runtime=Runtime())

    assert runtime.shutdown_current_thread(timeout_seconds=0.5) is True

    assert calls == ["primary"]
    assert submitted_ops == []
    assert runtime.submitted_ops == []
    assert runtime.routing_plans[-2].action == "shutdown_current_thread"
    assert runtime.routing_plans[-2].app_server_call == ("thread_shutdown", "primary")
    assert runtime.routing_plans[-1].action == "handle_thread_event_now"
    assert runtime.routing_state.pending_shutdown_exit_thread_id is None


def test_tui_app_runtime_close_releases_active_runtime_resources() -> None:
    # Rust source contract:
    # codex-tui::app owns the active thread runtime. Exiting the app drops that
    # runtime, which releases websocket receive tasks and other session-owned
    # resources instead of leaving them alive after ThreadClosed is rendered.
    calls: list[str] = []

    class Runtime:
        def submit_thread_op(self, thread_id: str, op: AppCommand) -> QueueActiveThreadEventStream:
            raise AssertionError("close should not submit ops")

        def shutdown_thread(self, thread_id: str) -> QueueActiveThreadEventStream:
            return ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")).shutdown_thread(thread_id)

        def close(self) -> None:
            calls.append("close")

    runtime = TuiAppRuntime(active_thread_runtime=Runtime())

    runtime.close()

    assert calls == ["close"]


def test_tui_app_runtime_thread_closed_failover_does_not_request_app_exit() -> None:
    # Rust source/test contract:
    # - codex-tui::app::thread_routing::handle_active_thread_event checks
    #   active_non_primary_shutdown_target before forwarding ThreadClosed to
    #   chatwidget::protocol.
    # - app/tests.rs::active_non_primary_shutdown_target_returns_ids_for_non_primary_shutdown
    #   proves unexpected active non-primary shutdown should switch back to the
    #   primary thread instead of becoming a user-requested app exit.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")))
    runtime.routing_state.active_thread_id = "agent"
    runtime.routing_state.primary_thread_id = "primary"

    runtime.handle_notification(ServerNotification("ThreadClosed", {"thread_id": "agent"}))

    assert runtime.routing_plans[-1].action == "failover_to_primary_thread"
    assert runtime.routing_plans[-1].thread_id == "agent"
    assert runtime.routing_plans[-1].target_thread_id == "primary"
    assert runtime.routing_state.active_thread_id == "primary"
    assert runtime.chat_widget.immediate_exit_requested is False
    assert runtime.chat_widget.shutdown_complete is False
    assert runtime.chat_widget.info_messages == [
        ("Agent thread agent closed. Switched back to main thread.", None)
    ]


def test_tui_app_runtime_rate_limits_loaded_updates_cache_and_finishes_status_handle() -> None:
    # Rust source/test contract:
    # - codex-tui::app::event_dispatch handles RateLimitsLoaded Ok by calling
    #   chat_widget.on_rate_limit_snapshot for each snapshot.
    # - For RateLimitRefreshOrigin::StatusCommand it then calls
    #   finish_status_rate_limit_refresh(request_id).
    # - chatwidget/tests/status_command_tests.rs::status_command_refresh_updates_cached_limits_for_future_status_outputs.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")))
    output, handle = new_status_output_with_rate_limits_handle(
        model_name="gpt-5",
        directory="C:/repo",
        rate_limits=[],
        refreshing_rate_limits=False,
    )
    runtime.register_status_rate_limit_handle(7, handle)
    snapshot = RateLimitSnapshotDisplay("codex", datetime.now().astimezone(), primary=RateLimitWindowDisplay(92.0, "soon", 300))

    runtime.handle_app_event(AppEvent.rate_limits_loaded(RateLimitRefreshOrigin.status_command(7), [snapshot]))

    assert runtime.chat_widget.rate_limit_snapshots_by_limit_id["codex"] == snapshot
    assert runtime.chat_widget.refreshing_status_outputs == []
    assert output.card.rate_limit_state.rate_limits.kind == "available"
    assert output.card.rate_limit_state.rate_limits.rows[0].value.percent_used == 92.0


def test_tui_app_runtime_rate_limits_loaded_error_finishes_status_handle_without_cache() -> None:
    # Rust source contract:
    # codex-tui::app::event_dispatch handles RateLimitsLoaded Err by warning
    # and still finishing the status-command refresh handle, without storing
    # new snapshots.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")))
    output, handle = new_status_output_with_rate_limits_handle(
        model_name="gpt-5",
        directory="C:/repo",
        rate_limits=[],
        refreshing_rate_limits=False,
    )
    runtime.register_status_rate_limit_handle(7, handle)

    runtime.handle_app_event(AppEvent.rate_limits_loaded(RateLimitRefreshOrigin.status_command(7), RuntimeError("boom")))

    assert runtime.chat_widget.rate_limit_snapshots_by_limit_id == {}
    assert runtime.chat_widget.refreshing_status_outputs == []
    assert output.card.rate_limit_state.rate_limits.kind == "missing"


def test_tui_app_runtime_selects_adjacent_agent_thread_and_syncs_label() -> None:
    # Rust source/test contract:
    # - codex-tui/src/app/agent_navigation.rs::
    #   adjacent_thread_id_wraps_in_spawn_order defines stable traversal.
    # - codex-tui/src/app/thread_routing.rs::sync_active_agent_label projects
    #   AgentNavigationState::active_agent_label into chat_widget.
    primary = "00000000-0000-0000-0000-000000000101"
    first = "00000000-0000-0000-0000-000000000102"
    second = "00000000-0000-0000-0000-000000000103"
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")))
    runtime.routing_state.active_thread_id = primary
    runtime.routing_state.primary_thread_id = primary
    runtime.upsert_agent_picker_thread(primary)
    runtime.upsert_agent_picker_thread(first, agent_nickname="Robie", agent_role="explorer")
    runtime.upsert_agent_picker_thread(second, agent_nickname="Bob", agent_role="worker")

    plan = runtime.select_adjacent_agent_thread(AgentNavigationDirection.Next)

    assert plan.action == "select_agent_thread"
    assert plan.thread_id == first
    assert runtime.routing_state.active_thread_id == first
    assert runtime.chat_widget.active_agent_label == "Robie [explorer]"

    previous = runtime.select_adjacent_agent_thread(AgentNavigationDirection.Previous)

    assert previous.thread_id == primary
    assert runtime.routing_state.active_thread_id == primary
    assert runtime.chat_widget.active_agent_label == "Main [default]"


def test_tui_app_runtime_thread_closed_pending_shutdown_still_completes_exit() -> None:
    # Rust source contract:
    # codex-tui::app::thread_routing clears pending_shutdown_exit_thread_id for
    # the tracked shutdown thread, then forwards ThreadClosed through
    # chatwidget::protocol so shutdown completion can request immediate exit.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "unused")))
    runtime.routing_state.active_thread_id = "agent"
    runtime.routing_state.primary_thread_id = "primary"
    runtime.routing_state.pending_shutdown_exit_thread_id = "agent"

    runtime.handle_notification(ServerNotification("ThreadClosed", {"thread_id": "agent"}))

    assert runtime.routing_plans[-1].action == "handle_thread_event_now"
    assert runtime.routing_state.pending_shutdown_exit_thread_id is None
    assert runtime.routing_state.active_thread_id == "agent"
    assert runtime.chat_widget.immediate_exit_requested is True
    assert runtime.chat_widget.shutdown_complete is True


def test_core_exec_active_thread_runtime_interrupts_active_turn_and_suppresses_late_completion(monkeypatch) -> None:
    # Rust source/test contract:
    # - codex-core/src/session/handlers.rs routes Op::Interrupt to
    #   Session::interrupt_task.
    # - codex-core/src/session/mod.rs::interrupt_task calls
    #   abort_all_tasks(TurnAbortReason::Interrupted).
    # - codex-rs/core/tests/suite/abort_tasks.rs::
    #   interrupt_long_running_tool_emits_turn_aborted expects an abort event
    #   soon after Op::Interrupt while work is active.
    started = threading.Event()
    release = threading.Event()
    seen_tokens = []

    class ModelInfo:
        slug = "gpt-test"

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_tokens.append(kwargs.get("cancellation_token"))
        started.set()
        await asyncio.to_thread(release.wait, 2.0)
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("late completion"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=ModelInfo(),
    )
    op = AppCommand.user_turn(
        [{"kind": "Text", "text": "start long turn"}],
        cwd=".",
        approval_policy=None,
        active_permission_profile=None,
        model="",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )

    stream = runtime.submit_thread_op("primary", op)

    first = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert started.wait(1.0)

    runtime.submit_thread_op("primary", AppCommand.interrupt())

    assert seen_tokens and seen_tokens[0] is not None
    assert seen_tokens[0].is_cancelled()
    interrupted = stream.next_event(timeout=0.2)
    assert interrupted is not None
    assert interrupted.kind == "TurnCompleted"
    assert interrupted.payload["turn"]["status"] == "Interrupted"
    assert stream.next_event(timeout=0.2) is None
    assert stream.closed is True

    release.set()
    time.sleep(0.05)
    assert stream.next_event(timeout=0.01) is None

def test_terminal_prompt_uses_input_submission_user_input_shape() -> None:
    # Rust composition contract:
    # - codex-tui::chatwidget::input_submission builds AppCommand::UserTurn.
    # - codex-tui::app routes that command through the active thread.
    # Product terminal input must not hand-roll a parallel UserTurn item shape,
    # because that bypass previously hid gaps between module tests and runtime.
    op = app_command_for_prompt("hello from terminal", cwd="C:/repo")

    assert op.kind == "UserTurn"
    assert type(op.payload["items"][0]).__name__ == "UserInput"
    assert user_turn_prompt(op) == "hello from terminal"
    assert tuple(item.text for item in user_inputs_for_app_command(op)) == ("hello from terminal",)


def test_tui_app_runtime_accepts_response_started_without_text() -> None:
    # Rust-derived composition contract:
    # codex-core/src/client.rs streams response.created before text deltas; the
    # TUI app must treat that as a live turn status/redraw signal, not as a
    # second assistant-delta lane and not as an unsupported notification.
    runtime = TuiAppRuntime(active_thread_runtime=ExecFunctionActiveThreadRuntime(lambda _prompt: (0, "")))

    runtime.handle_notification(ServerNotification("TurnStarted", {"turn": {"id": "turn-1", "thread_id": "primary"}}))
    runtime.handle_notification(ServerNotification("ResponseStarted", {"thread_id": "primary", "turn_id": "turn-1"}))

    assert runtime.chat_widget.assistant_text() == ""
    assert runtime.chat_widget.run_state_status_text() == "Working"


def test_core_exec_active_thread_runtime_maps_live_function_call_item_to_command(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core emits completed function_call output items before tool
    # execution/follow-up text; codex-tui::app maps them to
    # ServerNotification::ItemStarted so the terminal can render command
    # progress before the first assistant text delta.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="response_output_item_done",
                payload={
                    "item": ResponseItem.function_call(
                        "exec_command",
                        '{"cmd":"Get-Location","workdir":"C:\\\\repo"}',
                        "call-1",
                        id="item-1",
                    ).to_mapping()
                },
            )
        )
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == ["TurnStarted", "ItemStarted", "TurnCompleted"]
    item = events[1].payload["item"]
    assert item["kind"] == "CommandExecution"
    assert item["command"] == "Get-Location"


def test_core_exec_active_thread_runtime_preserves_reasoning_summary_config(monkeypatch) -> None:
    # Rust source/test contract:
    # - codex-core/src/config/mod.rs loads Config.model_reasoning_summary.
    # - codex-core/src/session/turn_context.rs copies
    #   SessionConfiguration.model_reasoning_summary into the turn context,
    #   falling back to ModelInfo.default_reasoning_summary only when unset.
    # - codex-core/src/client.rs::build_reasoning serializes
    #   ReasoningSummary::None as an absent request summary field.
    #
    # TUI composition contract:
    # codex-tui submits AppCommand::UserTurn through the active thread. The
    # Python Textual product path must not overwrite a config.toml
    # `model_reasoning_summary = "none"` with a local UI default such as
    # "auto"; otherwise the live session can request visible reasoning
    # summaries even though the user disabled them in config.
    seen: dict[str, object] = {}

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen["model_reasoning_summary"] = getattr(session_config, "model_reasoning_summary", None)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=SimpleNamespace(model_reasoning_summary="none"),
        model_client=object(),
        provider=object(),
        model_info=SimpleNamespace(default_reasoning_summary="auto"),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        if event.kind == "TurnCompleted":
            break

    assert seen["model_reasoning_summary"] == "none"


def test_core_exec_active_thread_runtime_maps_done_only_assistant_item_to_chatwidget(monkeypatch) -> None:
    # Rust source/test contract:
    # - codex-rs/core/src/session/turn.rs::ResponseEvent::OutputItemDone
    #   calls handle_output_item_done, which emits a completed
    #   TurnItem::AgentMessage for assistant messages.
    # - tests/test_core_stream_events_utils.py::
    #   test_handle_output_item_done_records_non_tool_item_and_emits_turn_items
    #   proves the Rust-derived core contract in Python.
    # - codex-tui::app must project that same response_output_item_done event
    #   into ItemCompleted(AgentMessage), not only into tool lifecycle events.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="response_output_item_done",
                payload={
                    "item": ResponseItem.message(
                        "assistant",
                        (ContentItem.output_text("done-only assistant answer"),),
                        id="msg-1",
                    ).to_mapping()
                },
            )
        )
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    app_runtime = TuiAppRuntime(
        active_thread_runtime=CoreExecActiveThreadRuntime(
            session_config=object(),
            model_client=object(),
            provider=object(),
            model_info=object(),
            auth=None,
        )
    )

    stream = app_runtime.submit_user_turn("ping")
    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        app_runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == ["TurnStarted", "ItemCompleted", "TurnCompleted"]
    assert events[1].payload["item"]["kind"] == "AgentMessage"
    assert events[1].payload["item"]["content"][0]["text"] == "done-only assistant answer"
    assert app_runtime.chat_widget.assistant_text() == "done-only assistant answer"


def test_core_exec_active_thread_runtime_exposes_model_client_thread_identity() -> None:
    # Rust source contract:
    # codex-tui::app::AppExitInfo collects the resumable thread id from the
    # active app/chatwidget state, while codex-core owns the underlying session
    # identity.  The Python CoreExec active-thread adapter must expose the
    # model-client thread id to the TUI app boundary without inventing a TUI id.
    model_client = SimpleNamespace(
        state=SimpleNamespace(
            thread_id="123e4567-e89b-12d3-a456-426614174000",
            session_id="123e4567-e89b-12d3-a456-426614174111",
        )
    )
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=model_client,
        provider=object(),
        model_info=object(),
        auth=None,
    )

    assert runtime.thread_id == "123e4567-e89b-12d3-a456-426614174000"
    assert runtime.conversation_id == "123e4567-e89b-12d3-a456-426614174000"
    assert runtime.session_id == "123e4567-e89b-12d3-a456-426614174111"


def test_exec_function_active_thread_runtime_reports_failed_turn_without_throwing_to_tui() -> None:
    runtime = ExecFunctionActiveThreadRuntime(lambda _prompt: (7, "bad auth"))
    op = AppCommand.user_turn(
        [{"kind": "Text", "text": "hello"}],
        cwd=".",
        approval_policy=None,
        active_permission_profile=None,
        model="",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )

    stream = runtime.submit_thread_op("primary", op)
    events = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == ["TurnStarted", "AgentMessageDelta", "TurnCompleted"]
    assert events[-1].payload["turn"]["status"] == "Failed"
    assert events[-1].payload["turn"]["error"]["message"] == "bad auth"
    assert events[-1].payload["turn"]["error"]["exit_code"] == 7


def test_app_command_user_turn_builds_core_exec_plan() -> None:
    # Rust composition contract:
    # - codex-tui::chatwidget::input_submission sends AppCommand::UserTurn.
    # - codex-tui::app submits that op to the active thread as the turn boundary.
    # - codex-core/session/turn owns UserInput sampling.
    op = AppCommand.user_turn(
        [{"kind": "Text", "text": "hello"}],
        cwd=".",
        approval_policy=None,
        active_permission_profile=None,
        model="",
        effort=None,
        summary=None,
        service_tier=None,
        final_output_json_schema=None,
        collaboration_mode=None,
        personality=None,
    )

    plan = exec_run_plan_for_app_command(op)

    assert plan.initial_operation.kind == "user_turn"
    assert plan.initial_operation.items[0].text == "hello"
    assert plan.prompt_summary == "hello"


def test_app_command_review_builds_core_exec_review_plan() -> None:
    # Rust composition contract:
    # - codex-tui::chatwidget::slash_dispatch submits AppCommand::Review for
    #   `/review <instructions>`.
    # - codex-tui::app::thread_routing routes AppCommand::Review to the active
    #   thread review boundary rather than coercing it into AppCommand::UserTurn.
    op = AppCommand.review(ReviewTarget.custom("check regressions"))

    plan = exec_run_plan_for_app_command(op)

    assert plan.initial_operation.kind == "review"
    assert plan.initial_operation.review_request is not None
    assert plan.initial_operation.review_request.target == ReviewTarget.custom("check regressions")
    assert plan.prompt_summary == "check regressions"


def test_core_exec_active_thread_runtime_forwards_core_result_to_chatwidget(monkeypatch) -> None:
    # Rust-derived composition test:
    # codex-tui::app observes active-thread server notifications and
    # codex-tui::chatwidget::protocol applies them to turn/streaming state.
    seen = {}

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen["items"] = tuple(item.text for item in plan.initial_operation.items)
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    app_runtime = TuiAppRuntime(
        active_thread_runtime=CoreExecActiveThreadRuntime(
            session_config=object(),
            model_client=object(),
            provider=object(),
            model_info=object(),
            auth=None,
        )
    )

    stream = app_runtime.submit_user_turn("ping")
    kinds = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        kinds.append(event.kind)
        app_runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert seen["items"] == ("ping",)
    assert kinds == ["TurnStarted", "AgentMessageDelta", "TurnCompleted"]
    assert app_runtime.chat_widget.assistant_text() == "pong"
    assert app_runtime.chat_widget.run_state_status_text() == "Ready"


def test_core_exec_active_thread_runtime_consumes_startup_prewarm_once(monkeypatch) -> None:
    # Rust-derived composition test:
    # codex-core/src/session_startup_prewarm.rs schedules a prewarmed
    # ModelClientSession, codex-core/src/tasks/regular.rs consumes it for the
    # first regular turn, and codex-core/src/session/turn.rs uses it instead
    # of creating a new session.
    prewarmed_session = object()
    seen_sessions = []

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_sessions.append(kwargs.get("model_session"))
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
        prewarmed_model_session=prewarmed_session,
    )

    for prompt in ("first", "second"):
        stream = runtime.submit_thread_op(
            "primary",
            AppCommand.user_turn(
                [{"kind": "Text", "text": prompt}],
                cwd=".",
                approval_policy=None,
                active_permission_profile=None,
                model="",
                effort=None,
                summary=None,
                service_tier=None,
                final_output_json_schema=None,
                collaboration_mode=None,
                personality=None,
            ),
        )
        while True:
            event = stream.next_event(timeout=1)
            if event is None or event.kind == "TurnCompleted":
                break

    assert seen_sessions == [prewarmed_session, None]


def test_core_exec_active_thread_runtime_close_releases_prewarm_and_cached_websocket_sessions() -> None:
    # Rust source contract:
    # - codex-tui::app drops the active thread runtime when exiting.
    # - codex-core/src/client.rs websocket sessions are cached for turn reuse,
    #   but app shutdown must close the transport so receiver tasks cannot keep
    #   the process alive after the exit summary.
    calls: list[str] = []

    class Session:
        def __init__(self, name: str) -> None:
            self.name = name

        def close(self) -> None:
            calls.append(f"session:{self.name}")

    class ModelClient:
        def close_cached_websocket_session(self) -> None:
            calls.append("cached")

    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=object(),
        model_info=object(),
        auth=None,
        prewarmed_model_session=Session("prewarm"),
    )

    runtime.close()

    assert calls == ["session:prewarm", "cached"]
    assert runtime._startup_prewarm_session is None
    assert runtime._startup_prewarm_consumed is True


def test_core_exec_active_thread_runtime_schedules_startup_prewarm(monkeypatch) -> None:
    # Rust-derived composition test:
    # startup prewarm runs before the first regular turn and the first turn
    # consumes the warmed session through the canonical session lane.
    prewarmed_session = object()
    seen_sessions = []
    prewarm_calls = []

    class ModelClient:
        def new_session(self):
            return prewarmed_session

    class ProviderInfo:
        def websocket_connect_timeout(self):
            return 1000

    class Provider:
        def info(self):
            return ProviderInfo()

    class ModelInfo:
        slug = "gpt-test"

    async def fake_prewarm(session_config, model_client, provider, model_info, **kwargs):
        prewarm_calls.append((session_config, model_client, provider, model_info, kwargs.get("model_session")))
        await asyncio.sleep(0)
        return kwargs.get("model_session")

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_sessions.append(kwargs.get("model_session"))
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.prewarm_exec_core_websocket_session", fake_prewarm)
    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=Provider(),
        model_info=ModelInfo(),
        auth=None,
        startup_prewarm_enabled=True,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )
    while True:
        event = stream.next_event(timeout=1)
        if event is None or event.kind == "TurnCompleted":
            break

    assert prewarm_calls == [(runtime.session_config, runtime.model_client, runtime.provider, runtime.model_info, prewarmed_session)]
    assert seen_sessions == [prewarmed_session]


def test_core_exec_active_thread_runtime_does_not_wait_full_timeout_for_stale_prewarm(monkeypatch) -> None:
    # Rust source: codex-core/src/session_startup_prewarm.rs.
    # Contract: resolving startup prewarm waits only
    # websocket_connect_timeout - age_at_first_turn. Once the warmup is already
    # older than the timeout, the first regular turn proceeds without paying a
    # second full timeout.
    prewarmed_session = object()
    seen_sessions = []

    class ModelClient:
        def new_session(self):
            return prewarmed_session

    class ProviderInfo:
        def websocket_connect_timeout(self):
            return 10

    class Provider:
        def info(self):
            return ProviderInfo()

    class ModelInfo:
        slug = "gpt-test"

    async def slow_prewarm(session_config, model_client, provider, model_info, **kwargs):
        await asyncio.sleep(0.2)
        return kwargs.get("model_session")

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_sessions.append(kwargs.get("model_session"))
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.prewarm_exec_core_websocket_session", slow_prewarm)
    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=Provider(),
        model_info=ModelInfo(),
        startup_prewarm_enabled=True,
    )
    time.sleep(0.05)

    started = time.monotonic()
    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )
    while True:
        event = stream.next_event(timeout=1)
        if event is None or event.kind == "TurnCompleted":
            break
    elapsed = time.monotonic() - started

    assert elapsed < 0.1
    assert seen_sessions == [None]


def test_core_exec_active_thread_runtime_does_not_force_fallback_after_generic_prewarm_failure(monkeypatch) -> None:
    # Rust modules:
    # - codex-core/src/session_startup_prewarm.rs
    # - codex-core/src/client.rs::ModelClientSession::prewarm_websocket
    # Contract: a generic startup prewarm failure resolves as unavailable and
    # is not itself a sticky fallback decision. Sticky HTTP fallback is owned by
    # the websocket transport fallback policy, such as 426 or retry exhaustion.
    fallback_calls = []
    seen_disabled = []

    class ModelClient:
        disabled = False

        def new_session(self):
            return object()

        def force_http_fallback(self):
            fallback_calls.append(True)
            self.disabled = True
            return True

    class ProviderInfo:
        def websocket_connect_timeout(self):
            return 1000

    class Provider:
        def info(self):
            return ProviderInfo()

    class ModelInfo:
        slug = "gpt-test"

    async def failing_prewarm(*args, **kwargs):
        raise RuntimeError("websocket unavailable")

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_disabled.append(model_client.disabled)
        return UserTurnSamplingResult(
            request_plan=None,
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("pong"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.prewarm_exec_core_websocket_session", failing_prewarm)
    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=ModelClient(),
        provider=Provider(),
        model_info=ModelInfo(),
        startup_prewarm_enabled=True,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )
    while True:
        event = stream.next_event(timeout=1)
        if event is None or event.kind == "TurnCompleted":
            break

    assert fallback_calls == []
    assert seen_disabled == [False]


def test_core_exec_active_thread_runtime_forwards_core_delta_before_result(monkeypatch) -> None:
    # Rust composition contract:
    # codex-tui observes active-thread app-server notifications while the turn
    # is running. The Python TUI adapter must forward core session stream
    # events as they are emitted, not only after the sampling result returns.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="agent_message_content_delta",
                payload=SimpleNamespace(delta="live chunk"),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            session_events=(
                SimpleNamespace(
                    type="agent_message_content_delta",
                    payload=SimpleNamespace(delta="live chunk"),
                ),
            ),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    first = stream.next_event(timeout=1)
    second = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert second is not None and second.kind == "AgentMessageDelta"
    assert second.payload["delta"] == "live chunk"

    remaining = []
    while True:
        event = stream.next_event(timeout=1)
        if event is None:
            break
        remaining.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in remaining] == ["TurnCompleted"]


def test_core_exec_active_thread_runtime_normalizes_transport_delta_into_session_lane(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core/src/session/turn.rs maps ResponseEvent::OutputTextDelta into
    # sess.send_event(EventMsg::AgentMessageContentDelta); codex-tui::app then
    # observes the session/server-notification lane. Python may observe raw
    # websocket frames for latency, but TUI rendering must still enter through
    # the same canonical session event lane.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="transport live")))
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    first = stream.next_event(timeout=1)
    second = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert second is not None and second.kind == "AgentMessageDelta"
    assert second.payload["delta"] == "transport live"

    completed = None
    while completed is None:
        event = stream.next_event(timeout=1)
        assert event is not None
        if event.kind == "TurnCompleted":
            completed = event

    assert completed.payload["turn"]["status"] == "Completed"


def test_core_exec_active_thread_runtime_does_not_attach_raw_stream_observer(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core/src/session/turn.rs is the sole mapper from ResponseEvent into
    # EventMsg, and codex-tui consumes that session/app-server notification
    # lane. The product TUI must not also attach a raw stream observer as a
    # second visible lane.
    seen_kwargs = {}

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        seen_kwargs.update(kwargs)
        kwargs["session_event_observer"](
            SimpleNamespace(
                type="agent_message_content_delta",
                payload=SimpleNamespace(delta="single lane"),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert "stream_event_observer" not in seen_kwargs
    assert [event.payload["delta"] for event in events if event.kind == "AgentMessageDelta"] == ["single lane"]


def test_core_exec_active_thread_runtime_keeps_multiple_transport_delta_chunks(monkeypatch) -> None:
    # Rust composition contract:
    # ResponseEvent::OutputTextDelta is an ordered stream; each chunk from the
    # same canonical stream lane must render. Replay suppression must be
    # source-based, not "first delta wins" for the whole turn.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="hel")))
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="lo")))
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    deltas = [event.payload["delta"] for event in events if event.kind == "AgentMessageDelta"]
    assert deltas == ["hel", "lo"]


def test_core_exec_active_thread_runtime_finishes_on_task_complete_session_event(monkeypatch) -> None:
    # Rust source/test contract:
    # - codex-core::session::turn records completed-response usage and emits
    #   TokenCount before the final EventMsg::TurnComplete.
    # - codex-tui::chatwidget::protocol must see ThreadTokenUsageUpdated before
    #   TurnCompleted restores the ready/input state.
    # - EventMsg::TurnComplete is the terminal turn boundary; the TUI adapter
    #   must not swallow it while waiting for hypothetical later tail events.
    returned = threading.Event()

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="done")))
        observer(
            SimpleNamespace(
                type="token_count",
                payload=SimpleNamespace(
                    info=SimpleNamespace(
                        total_token_usage=SimpleNamespace(
                            total_tokens=8,
                            input_tokens=2,
                            cached_input_tokens=0,
                            output_tokens=6,
                            reasoning_output_tokens=0,
                        ),
                        last_token_usage=SimpleNamespace(
                            total_tokens=8,
                            input_tokens=2,
                            cached_input_tokens=0,
                            output_tokens=6,
                            reasoning_output_tokens=0,
                        ),
                        model_context_window=200000,
                    )
                ),
            )
        )
        observer(SimpleNamespace(type="task_complete", payload=SimpleNamespace()))
        returned.set()
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == [
        "TurnStarted",
        "AgentMessageDelta",
        "ThreadTokenUsageUpdated",
        "TurnCompleted",
    ]
    token_event = next(event for event in events if event.kind == "ThreadTokenUsageUpdated")
    assert token_event.payload["token_usage"]["total"]["total_tokens"] == 8
    assert returned.is_set() is True
    assert stream.next_event(timeout=1) is None


def test_core_exec_active_thread_runtime_maps_token_count_to_chatwidget_usage(monkeypatch) -> None:
    # Rust source/test contract:
    # - codex-core::session::send_token_count_event emits EventMsg::TokenCount.
    # - codex-tui::chatwidget::protocol maps ThreadTokenUsageUpdated into
    #   ChatWidget::set_token_info.
    # - codex-cli::main::format_exit_messages prints non-zero token usage before
    #   the resume hint.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="token_count",
                payload=SimpleNamespace(
                    info=SimpleNamespace(
                        total_token_usage=SimpleNamespace(
                            total_tokens=34,
                            input_tokens=30,
                            cached_input_tokens=10,
                            output_tokens=4,
                            reasoning_output_tokens=2,
                        ),
                        last_token_usage=SimpleNamespace(
                            total_tokens=34,
                            input_tokens=30,
                            cached_input_tokens=10,
                            output_tokens=4,
                            reasoning_output_tokens=2,
                        ),
                        model_context_window=200000,
                    )
                ),
            )
        )
        observer(SimpleNamespace(type="agent_message_content_delta", payload=SimpleNamespace(delta="done")))
        observer(SimpleNamespace(type="task_complete", payload=SimpleNamespace()))
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    active_runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )
    runtime = TuiAppRuntime(active_thread_runtime=active_runtime)

    stream = runtime.submit_user_turn("ping")

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event.kind)
        runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert events == ["TurnStarted", "ThreadTokenUsageUpdated", "AgentMessageDelta", "TurnCompleted"]
    assert runtime.chat_widget.token_info is not None
    assert runtime.chat_widget.token_info.total_token_usage.total_tokens == 34
    assert runtime.chat_widget.token_info.total_token_usage.input_tokens == 30
    assert runtime.chat_widget.token_info.total_token_usage.cached_input_tokens == 10
    assert runtime.chat_widget.token_info.total_token_usage.output_tokens == 4
    assert runtime.chat_widget.token_info.total_token_usage.reasoning_output_tokens == 2
    assert runtime.chat_widget.token_info.model_context_window == 200000


def test_core_exec_active_thread_runtime_uses_one_delta_lane_even_when_replay_differs(monkeypatch) -> None:
    # Rust composition contract:
    # Rust has one visible assistant-delta lane from core session events into
    # codex-tui; it does not fuzzy-match text to remove duplicates. Python's
    # raw websocket observation is normalized into that lane, and a later replay
    # from the result/session side must not become a second visible message even
    # when the text differs by a small amount.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        kwargs["session_event_observer"](
            SimpleNamespace(
                type="agent_message_content_delta",
                payload=SimpleNamespace(delta="hello"),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            session_events=(
                SimpleNamespace(
                    type="agent_message_content_delta",
                    payload=SimpleNamespace(delta="hello!"),
                ),
            ),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    deltas = [event.payload["delta"] for event in events if event.kind == "AgentMessageDelta"]
    assert deltas == ["hello"]


def test_core_exec_active_thread_runtime_surfaces_exec_command_item_before_agent_text(monkeypatch) -> None:
    # Rust composition contract:
    # codex-api/codex-core expose response output items before assistant text,
    # and codex-tui::app forwards command execution lifecycle as
    # ServerNotification::ItemStarted/ItemCompleted. This keeps tool work
    # visible during the no-agent-text phase of a turn.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="response_output_item_done",
                payload=SimpleNamespace(
                    item=ResponseItem.function_call(
                        "exec_command",
                        '{"cmd":"Get-Content README.md","workdir":"C:\\\\repo"}',
                        "call-1",
                        id="item-1",
                    ),
                ),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            tool_response_items=(
                ResponseItem(
                    type="function_call_output",
                    call_id="call-1",
                    output=FunctionCallOutputPayload.text("readme contents", success=True),
                ),
            ),
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "analyze"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == [
        "TurnStarted",
        "ItemStarted",
        "ItemCompleted",
        "AgentMessageDelta",
        "TurnCompleted",
    ]
    started_item = events[1].payload["item"]
    completed_item = events[2].payload["item"]
    assert started_item["kind"] == "CommandExecution"
    assert started_item["command"] == "Get-Content README.md"
    assert started_item["cwd"] == "C:\\repo"
    assert completed_item["status"] == "Completed"
    assert completed_item["aggregated_output"] == "readme contents"
    app_runtime = TuiAppRuntime(active_thread_runtime=runtime)
    app_runtime.handle_notification(events[0])
    app_runtime.handle_notification(events[1])
    app_runtime.handle_notification(events[2])
    assert app_runtime.chat_widget.command_lifecycle.history_cells[0].calls[0].call_id == "call-1"


def test_core_exec_active_thread_runtime_forwards_canonical_item_lifecycle(monkeypatch) -> None:
    # Rust-derived composition test:
    # codex-core::session emits EventMsg::ItemStarted/ItemCompleted carrying a
    # TurnItem, app-server turns that into ServerNotification::ItemStarted and
    # ::ItemCompleted, and codex-tui::chatwidget::protocol consumes the command
    # execution lifecycle without a raw ResponseItem side channel.
    started = TurnItem.command_execution(
        CommandExecutionItem(
            id="call-1",
            command="Get-ChildItem",
            cwd="C:\\repo",
            status="inProgress",
            source="agent",
            command_actions=({"type": "unknown", "cmd": "Get-ChildItem"},),
        )
    )
    completed = TurnItem.command_execution(
        CommandExecutionItem(
            id="call-1",
            command="Get-ChildItem",
            cwd="C:\\repo",
            status="completed",
            source="agent",
            command_actions=({"type": "unknown", "cmd": "Get-ChildItem"},),
            aggregated_output="file.txt",
            exit_code=0,
            duration_ms=12,
        )
    )

    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="item_started",
                payload=SimpleNamespace(thread_id="primary", turn_id="terminal-turn", item=started, started_at_ms=1),
            )
        )
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(
            request_plan=None,
            session_events=(
                SimpleNamespace(
                    type="item_started",
                    payload=SimpleNamespace(thread_id="primary", turn_id="terminal-turn", item=started, started_at_ms=1),
                ),
                SimpleNamespace(
                    type="item_completed",
                    payload=SimpleNamespace(thread_id="primary", turn_id="terminal-turn", item=completed, completed_at_ms=2),
                ),
            ),
            tool_response_items=(
                ResponseItem(
                    type="function_call_output",
                    call_id="call-1",
                    output=FunctionCallOutputPayload.text("fallback duplicate", success=True),
                ),
            ),
            response_items=(ResponseItem.message("assistant", (ContentItem.output_text("done"),)),),
            turn_status="completed",
        )

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    app_runtime = TuiAppRuntime(
        active_thread_runtime=CoreExecActiveThreadRuntime(
            session_config=object(),
            model_client=object(),
            provider=object(),
            model_info=object(),
            auth=None,
        )
    )

    stream = app_runtime.submit_user_turn("analyze")
    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        app_runtime.handle_notification(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events] == [
        "TurnStarted",
        "ItemStarted",
        "ItemCompleted",
        "AgentMessageDelta",
        "TurnCompleted",
    ]
    assert events[1].payload["item"]["kind"] == "CommandExecution"
    assert events[1].payload["item"]["command_actions"] == ({"type": "unknown", "cmd": "Get-ChildItem"},)
    assert events[2].payload["item"]["aggregated_output"] == "file.txt"
    assert app_runtime.chat_widget.command_lifecycle.history_cells[0].calls[0].call_id == "call-1"
    assert app_runtime.chat_widget.command_lifecycle.history_cells[0].calls[0].output.aggregated_output == "file.txt"


def test_session_event_mapper_accepts_dict_item_completed_agent_message() -> None:
    # Rust source: codex-core/src/session/turn.rs::ResponseEvent::OutputItemDone
    # Contract: live stream observers may deliver item_completed as a mapped
    # event object; codex-tui::app must route it to chatwidget ItemCompleted.
    item = TurnItem.agent_message(
        AgentMessageItem("msg-1", (AgentMessageContent.text_content("done-only answer"),))
    )
    notifications = _server_notifications_from_session_event(
        {
            "type": "item_completed",
            "thread_id": "thread-1",
            "turn_id": "turn-1",
            "completed_at_ms": 123,
            "item": item.to_mapping(),
        },
        thread_id="thread-1",
        turn_id="turn-1",
    )

    assert len(notifications) == 1
    assert notifications[0].kind == "ItemCompleted"
    assert notifications[0].payload["item"]["kind"] == "AgentMessage"
    assert notifications[0].payload["item"]["content"][0]["text"] == "done-only answer"


def test_core_exec_active_thread_runtime_forwards_reasoning_delta(monkeypatch) -> None:
    # Rust composition contract:
    # codex-core/src/session/turn.rs maps
    # ResponseEvent::ReasoningSummaryDelta into summary reasoning events, and
    # codex-app-server-protocol::event_mapping turns those into
    # ServerNotification::ReasoningSummaryTextDelta.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        kwargs["session_event_observer"](SimpleNamespace(type="reasoning_summary_delta", payload=SimpleNamespace(delta="**Reading**")))
        await asyncio.sleep(0.05)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    first = stream.next_event(timeout=1)
    second = stream.next_event(timeout=1)
    assert first is not None and first.kind == "TurnStarted"
    assert second is not None and second.kind == "ReasoningSummaryTextDelta"
    assert second.payload["delta"] == "**Reading**"


def test_session_reasoning_content_delta_maps_to_raw_text_delta() -> None:
    # Rust source contract:
    # - codex-core/src/session/turn.rs maps raw
    #   ResponseEvent::ReasoningContentDelta into
    #   EventMsg::ReasoningRawContentDelta.
    # - codex-app-server-protocol/src/protocol/event_mapping.rs maps raw
    #   reasoning content to ServerNotification::ReasoningTextDelta, while
    #   summary text maps to ReasoningSummaryTextDelta.
    summary = _server_notifications_from_session_event(
        SimpleNamespace(type="reasoning_summary_delta", payload=SimpleNamespace(delta="**Reading**")),
        thread_id="thread-1",
        turn_id="turn-1",
    )
    raw = _server_notifications_from_session_event(
        SimpleNamespace(type="reasoning_content_delta", payload=SimpleNamespace(delta="raw detail")),
        thread_id="thread-1",
        turn_id="turn-1",
    )
    legacy_raw = _server_notifications_from_session_event(
        SimpleNamespace(type="reasoning_raw_content_delta", payload=SimpleNamespace(delta="legacy raw detail")),
        thread_id="thread-1",
        turn_id="turn-1",
    )

    assert summary[0].kind == "ReasoningSummaryTextDelta"
    assert raw[0].kind == "ReasoningTextDelta"
    assert legacy_raw[0].kind == "ReasoningTextDelta"


def test_core_exec_active_thread_runtime_forwards_reasoning_section_and_raw_delta(monkeypatch) -> None:
    # Rust composition contract:
    # - codex-core/src/session/turn.rs forwards summary text and raw reasoning
    #   text as distinct reasoning events.
    # - codex-app-server-protocol::event_mapping preserves them as
    #   ReasoningSummaryTextDelta and ReasoningTextDelta respectively.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(SimpleNamespace(type="reasoning_summary_delta", payload=SimpleNamespace(delta="**Inspecting**")))
        observer(SimpleNamespace(type="agent_reasoning_section_break", payload=SimpleNamespace(summary_index=0)))
        observer(SimpleNamespace(type="reasoning_content_delta", payload=SimpleNamespace(delta="raw detail")))
        await asyncio.sleep(0.01)
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    events = []
    while True:
        event = stream.next_event(timeout=1)
        assert event is not None
        events.append(event)
        if event.kind == "TurnCompleted":
            break

    assert [event.kind for event in events[:4]] == [
        "TurnStarted",
        "ReasoningSummaryTextDelta",
        "ReasoningSummaryPartAdded",
        "ReasoningTextDelta",
    ]
    assert events[1].payload["delta"] == "**Inspecting**"
    assert events[3].payload["delta"] == "raw detail"


def test_core_exec_active_thread_runtime_surfaces_stream_error_when_no_agent_text(monkeypatch) -> None:
    # Rust composition contract: core stream/error events are user-visible turn
    # failures when the model never produces assistant text.
    async def fake_core_sampling(session_config, plan, model_client, provider, model_info, **kwargs):
        observer = kwargs["session_event_observer"]
        observer(
            SimpleNamespace(
                type="stream_error",
                payload=SimpleNamespace(
                    message="Reconnecting... 1/5",
                    additional_details="Error while reading the server response",
                ),
            )
        )
        return UserTurnSamplingResult(request_plan=None, response_items=(), turn_status="completed")

    monkeypatch.setattr("pycodex.tui.app.runtime.run_exec_user_turn_core_sampling_websocket_preferred", fake_core_sampling)
    runtime = CoreExecActiveThreadRuntime(
        session_config=object(),
        model_client=object(),
        provider=object(),
        model_info=object(),
        auth=None,
    )

    stream = runtime.submit_thread_op(
        "primary",
        AppCommand.user_turn(
            [{"kind": "Text", "text": "ping"}],
            cwd=".",
            approval_policy=None,
            active_permission_profile=None,
            model="",
            effort=None,
            summary=None,
            service_tier=None,
            final_output_json_schema=None,
            collaboration_mode=None,
            personality=None,
        ),
    )

    assert stream.next_event(timeout=1).kind == "TurnStarted"
    completed = stream.next_event(timeout=1)

    assert completed is not None
    assert completed.kind == "TurnCompleted"
    assert completed.payload["turn"]["status"] == "Failed"
    assert "Error while reading the server response" in completed.payload["turn"]["error"]["message"]
