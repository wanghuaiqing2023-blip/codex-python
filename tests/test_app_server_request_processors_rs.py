"""Rust parity tests for ``codex-app-server/src/request_processors.rs``.

The Rust parent module declares child request-processor modules, re-exports
their processor types, re-exports a handful of thread helpers, and filters
rollout entries with ``EventPersistenceMode::Limited`` before replaying them
through ``ThreadHistoryBuilder``.
"""

from pycodex.app_server.request_processors import (
    REQUEST_PROCESSOR_CHILD_MODULES,
    REQUEST_PROCESSOR_HELPER_REEXPORTS,
    REQUEST_PROCESSOR_REEXPORTS,
    REQUEST_PROCESSOR_TEST_HELPER_REEXPORTS,
    build_api_turns_from_rollout_items,
    persisted_limited_rollout_items,
)
from pycodex.app_server_protocol import ThreadHistoryBuilder


def test_request_processors_parent_module_declares_rust_child_modules() -> None:
    # Rust source: codex-app-server/src/request_processors.rs module declarations.
    assert REQUEST_PROCESSOR_CHILD_MODULES == (
        "account_processor",
        "apps_processor",
        "catalog_processor",
        "command_exec_processor",
        "config_processor",
        "environment_processor",
        "external_agent_config_processor",
        "feedback_doctor_report",
        "feedback_processor",
        "fs_processor",
        "git_processor",
        "initialize_processor",
        "marketplace_processor",
        "mcp_processor",
        "plugins",
        "process_exec_processor",
        "remote_control_processor",
        "search",
        "thread_processor",
        "token_usage_replay",
        "turn_processor",
        "windows_sandbox_processor",
        "config_errors",
        "request_errors",
        "thread_goal_processor",
        "thread_lifecycle",
        "thread_resume_redaction",
        "thread_summary",
    )


def test_request_processors_parent_module_reexports_rust_processors() -> None:
    # Rust source: codex-app-server/src/request_processors.rs pub(crate) uses.
    assert REQUEST_PROCESSOR_REEXPORTS == (
        "AccountRequestProcessor",
        "AppsRequestProcessor",
        "CatalogRequestProcessor",
        "CommandExecRequestProcessor",
        "ConfigRequestProcessor",
        "EnvironmentRequestProcessor",
        "ExternalAgentConfigRequestProcessor",
        "FeedbackRequestProcessor",
        "FsRequestProcessor",
        "GitRequestProcessor",
        "InitializeRequestProcessor",
        "MarketplaceRequestProcessor",
        "McpRequestProcessor",
        "PluginRequestProcessor",
        "ProcessExecRequestProcessor",
        "RemoteControlRequestProcessor",
        "SearchRequestProcessor",
        "ThreadGoalRequestProcessor",
        "ThreadRequestProcessor",
        "TurnRequestProcessor",
        "WindowsSandboxRequestProcessor",
    )


def test_request_processors_parent_module_reexports_thread_helpers() -> None:
    # Rust source: codex-app-server/src/request_processors.rs helper pub(crate) uses.
    assert REQUEST_PROCESSOR_HELPER_REEXPORTS == (
        "populate_thread_turns_from_history",
        "thread_from_stored_thread",
        "thread_settings_from_config_snapshot",
        "thread_settings_from_core_snapshot",
    )
    assert REQUEST_PROCESSOR_TEST_HELPER_REEXPORTS == (
        "read_summary_from_rollout",
        "summary_to_thread",
    )


def test_build_api_turns_filters_to_limited_persisted_rollout_items() -> None:
    # Rust source: build_api_turns_from_rollout_items filters through
    # codex_rollout::is_persisted_rollout_item(..., EventPersistenceMode::Limited).
    items = [
        {"type": "event_msg", "payload": {"type": "turn_started", "turn_id": "turn-1", "model_context_window": None}},
        {"type": "event_msg", "payload": {"type": "warning", "message": "not persisted"}},
        {"type": "event_msg", "payload": {"type": "exec_command_end", "call_id": "call-1", "exit_code": 0}},
        {"type": "event_msg", "payload": {"type": "user_message", "message": "hello"}},
        {"type": "event_msg", "payload": {"type": "agent_message", "message": "world"}},
        {"type": "event_msg", "payload": {"type": "turn_complete", "turn_id": "turn-1", "last_agent_message": "world"}},
    ]

    filtered = persisted_limited_rollout_items(items)

    assert [item["payload"]["type"] for item in filtered] == [
        "turn_started",
        "user_message",
        "agent_message",
        "turn_complete",
    ]

    expected_builder = ThreadHistoryBuilder()
    for item in filtered:
        expected_builder.handle_rollout_item(item)

    turns = build_api_turns_from_rollout_items(items)

    assert turns == expected_builder.finish()
    assert len(turns) == 1
    assert [item.type for item in turns[0].items] == ["userMessage", "agentMessage"]
