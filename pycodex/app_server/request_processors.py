"""Parent request-processor module projection for ``codex-app-server``.

Rust ``src/request_processors.rs`` owns the request-processor namespace:
child module declarations, crate-local processor re-exports, helper re-exports,
and the small rollout-history bridge used to build API ``Turn`` values.
Concrete request handlers live in the child modules and are intentionally out
of scope for this parent-module port.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from pycodex.app_server_protocol import ThreadHistoryBuilder, Turn
from pycodex.rollout import EventPersistenceMode, is_persisted_rollout_item

JsonValue = Any


REQUEST_PROCESSOR_CHILD_MODULES: tuple[str, ...] = (
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

REQUEST_PROCESSOR_REEXPORTS: tuple[str, ...] = (
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

REQUEST_PROCESSOR_HELPER_REEXPORTS: tuple[str, ...] = (
    "populate_thread_turns_from_history",
    "thread_from_stored_thread",
    "thread_settings_from_config_snapshot",
    "thread_settings_from_core_snapshot",
)

REQUEST_PROCESSOR_TEST_HELPER_REEXPORTS: tuple[str, ...] = (
    "read_summary_from_rollout",
    "summary_to_thread",
)


def persisted_limited_rollout_items(items: Iterable[JsonValue]) -> list[JsonValue]:
    """Return the items Rust would pass to ``ThreadHistoryBuilder``.

    Mirrors ``build_api_turns_from_rollout_items`` in
    ``codex-app-server/src/request_processors.rs`` where only rollout entries
    persisted under ``EventPersistenceMode::Limited`` are replayed into the
    app-server thread-history builder.
    """

    return [
        item
        for item in items
        if is_persisted_rollout_item(item, EventPersistenceMode.LIMITED)
    ]


def build_api_turns_from_rollout_items(items: Iterable[JsonValue]) -> list[Turn]:
    """Build app-server API turns from limited-persisted rollout items."""

    builder = ThreadHistoryBuilder()
    for item in persisted_limited_rollout_items(items):
        builder.handle_rollout_item(item)
    return builder.finish()


__all__ = [
    "REQUEST_PROCESSOR_CHILD_MODULES",
    "REQUEST_PROCESSOR_HELPER_REEXPORTS",
    "REQUEST_PROCESSOR_REEXPORTS",
    "REQUEST_PROCESSOR_TEST_HELPER_REEXPORTS",
    "build_api_turns_from_rollout_items",
    "persisted_limited_rollout_items",
]
