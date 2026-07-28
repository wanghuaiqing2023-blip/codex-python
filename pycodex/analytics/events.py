"""Rust-aligned ``codex-analytics::events`` owner."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from . import _enum_value
from .facts import *
from .facts import _SnakeEnum

DEFAULT_ORIGINATOR = "codex_cli_rs"

def plugin_state_event_type(state: PluginState | str) -> str:
    state_value = _enum_value(state)
    return {
        PluginState.INSTALLED.value: "codex_plugin_installed",
        PluginState.UNINSTALLED.value: "codex_plugin_uninstalled",
        PluginState.ENABLED.value: "codex_plugin_enabled",
        PluginState.DISABLED.value: "codex_plugin_disabled",
    }[state_value]

def codex_app_metadata(
    tracking: TrackEventsContext,
    app: AppInvocation,
    *,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    return {
        "connector_id": app.connector_id,
        "thread_id": tracking.thread_id,
        "turn_id": tracking.turn_id,
        "app_name": app.app_name,
        "product_client_id": product_client_id,
        "invoke_type": _enum_value(app.invocation_type),
        "model_slug": tracking.model_slug,
    }

def codex_plugin_metadata(
    plugin: PluginTelemetryMetadata,
    *,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    summary = plugin.capability_summary
    return {
        "plugin_id": plugin.remote_plugin_id or plugin.plugin_id.as_key(),
        "plugin_name": plugin.plugin_id.plugin_name,
        "marketplace_name": plugin.plugin_id.marketplace_name,
        "has_skills": None if summary is None else summary.has_skills,
        "mcp_server_count": None if summary is None else len(summary.mcp_server_names),
        "connector_ids": None if summary is None else list(summary.app_connector_ids),
        "product_client_id": product_client_id,
    }

def codex_plugin_used_metadata(
    tracking: TrackEventsContext,
    plugin: PluginTelemetryMetadata,
    *,
    product_client_id: str = DEFAULT_ORIGINATOR,
) -> dict[str, Any]:
    return {
        **codex_plugin_metadata(plugin, product_client_id=product_client_id),
        "thread_id": tracking.thread_id,
        "turn_id": tracking.turn_id,
        "model_slug": tracking.model_slug,
    }

def codex_hook_run_metadata(tracking: TrackEventsContext, hook: HookRunFact) -> dict[str, Any]:
    return {
        "thread_id": tracking.thread_id,
        "turn_id": tracking.turn_id,
        "model_slug": tracking.model_slug,
        "hook_name": analytics_hook_event_name(hook.event_name),
        "hook_source": analytics_hook_source(hook.hook_source),
        "status": analytics_hook_status(hook.status),
    }

def analytics_hook_event_name(event_name: HookEventName | str) -> str:
    return event_name.value if isinstance(event_name, HookEventName) else str(event_name)

def analytics_hook_source(source: HookSource | str) -> str:
    return _enum_value(source)

def analytics_hook_status(status: HookRunStatus | str) -> str:
    return _enum_value(status)

class AppServerRpcTransport(_SnakeEnum):
    STDIO = "stdio"
    WEBSOCKET = "websocket"
    IN_PROCESS = "in_process"

class GuardianReviewDecision(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"

class GuardianReviewTerminalStatus(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"
    FAILED_CLOSED = "failed_closed"

class GuardianReviewFailureReason(_SnakeEnum):
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    PROMPT_BUILD_ERROR = "prompt_build_error"
    SESSION_ERROR = "session_error"
    PARSE_ERROR = "parse_error"

class GuardianReviewSessionKind(_SnakeEnum):
    TRUNK_NEW = "trunk_new"
    TRUNK_REUSED = "trunk_reused"
    EPHEMERAL_FORKED = "ephemeral_forked"

class GuardianApprovalRequestSource(_SnakeEnum):
    MAIN_TURN = "main_turn"
    DELEGATED_SUBAGENT = "delegated_subagent"

class ReviewStatus(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    TIMED_OUT = "timed_out"

class ReviewResolution(_SnakeEnum):
    NONE = "none"
    SESSION_APPROVAL = "session_approval"
    EXEC_POLICY_AMENDMENT = "exec_policy_amendment"
    NETWORK_POLICY_AMENDMENT = "network_policy_amendment"

class FinalApprovalOutcome(_SnakeEnum):
    UNKNOWN = "unknown"
    NOT_NEEDED = "not_needed"
    CONFIG_ALLOWED = "config_allowed"
    POLICY_FORBIDDEN = "policy_forbidden"
    GUARDIAN_APPROVED = "guardian_approved"
    GUARDIAN_DENIED = "guardian_denied"
    GUARDIAN_ABORTED = "guardian_aborted"
    USER_APPROVED = "user_approved"
    USER_APPROVED_FOR_SESSION = "user_approved_for_session"
    USER_DENIED = "user_denied"
    USER_ABORTED = "user_aborted"

class ToolItemTerminalStatus(_SnakeEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    REJECTED = "rejected"
    INTERRUPTED = "interrupted"

class ToolItemFailureKind(_SnakeEnum):
    TOOL_ERROR = "tool_error"
    APPROVAL_DENIED = "approval_denied"
    APPROVAL_ABORTED = "approval_aborted"
    SANDBOX_DENIED = "sandbox_denied"
    POLICY_FORBIDDEN = "policy_forbidden"

class WebSearchActionKind(_SnakeEnum):
    SEARCH = "search"
    OPEN_PAGE = "open_page"
    FIND_IN_PAGE = "find_in_page"
    OTHER = "other"

class ReviewSubjectKind(_SnakeEnum):
    COMMAND_EXECUTION = "command_execution"
    FILE_CHANGE = "file_change"
    MCP_TOOL_CALL = "mcp_tool_call"
    PERMISSIONS = "permissions"
    NETWORK_ACCESS = "network_access"

class Reviewer(_SnakeEnum):
    GUARDIAN = "guardian"
    USER = "user"

class ReviewTrigger(_SnakeEnum):
    INITIAL = "initial"
    SANDBOX_DENIAL = "sandbox_denial"
    NETWORK_POLICY_DENIAL = "network_policy_denial"
    EXECVE_INTERCEPT = "execve_intercept"

@dataclass
class CodexToolItemEventBase:
    thread_id: str
    turn_id: str
    item_id: str
    app_server_client: dict[str, Any]
    runtime: dict[str, Any]
    thread_source: Any | None
    subagent_source: str | None
    parent_thread_id: str | None
    tool_name: str
    started_at_ms: int
    completed_at_ms: int
    duration_ms: int | None
    execution_duration_ms: int | None
    review_count: int
    guardian_review_count: int
    user_review_count: int
    final_approval_outcome: FinalApprovalOutcome | str
    terminal_status: ToolItemTerminalStatus | str
    failure_kind: ToolItemFailureKind | str | None
    requested_additional_permissions: bool
    requested_network_access: bool

@dataclass
class GuardianReviewTrackContext:
    fields: dict[str, Any]

@dataclass
class GuardianReviewEventParams:
    thread_id: str
    turn_id: str
    review_id: str
    target_item_id: str | None
    approval_request_source: GuardianApprovalRequestSource | str
    reviewed_action: dict[str, Any]
    reviewed_action_truncated: bool
    decision: GuardianReviewDecision | str
    terminal_status: GuardianReviewTerminalStatus | str
    failure_reason: GuardianReviewFailureReason | str | None
    risk_level: Any | None
    user_authorization: Any | None
    outcome: Any | None
    guardian_thread_id: str | None
    guardian_session_kind: GuardianReviewSessionKind | str | None
    guardian_model: str | None
    guardian_reasoning_effort: str | None
    had_prior_review_context: bool | None
    review_timeout_ms: int
    tool_call_count: int | None
    time_to_first_token_ms: int | None
    completion_latency_ms: int | None
    started_at: int
    completed_at: int | None
    input_tokens: int | None
    cached_input_tokens: int | None
    output_tokens: int | None
    reasoning_output_tokens: int | None
    total_tokens: int | None

class GuardianReviewAnalyticsResult(_SnakeEnum):
    APPROVED = "approved"
    DENIED = "denied"
    ABORTED = "aborted"
    FAILED = "failed"

def subagent_source_name(subagent_source: Any) -> str:
    value = _enum_value(subagent_source)
    if isinstance(value, dict):
        kind = value.get("kind") or value.get("type")
        if kind == "ThreadSpawn":
            return "thread_spawn"
        if kind == "MemoryConsolidation":
            return "memory_consolidation"
        if kind == "Review":
            return "review"
        if kind == "Compact":
            return "compact"
        if kind == "Other":
            other = value.get("value") or value.get("name")
            return str(other) if other is not None else "other"
    text = str(value)
    mapping = {
        "Review": "review",
        "review": "review",
        "Compact": "compact",
        "compact": "compact",
        "ThreadSpawn": "thread_spawn",
        "thread_spawn": "thread_spawn",
        "MemoryConsolidation": "memory_consolidation",
        "memory_consolidation": "memory_consolidation",
    }
    if text.startswith("Other:"):
        return text.split(":", 1)[1]
    return mapping.get(text, text)

def subagent_parent_thread_id(subagent_source: Any) -> str | None:
    value = _enum_value(subagent_source)
    if isinstance(value, dict) and (value.get("kind") or value.get("type")) == "ThreadSpawn":
        parent = value.get("parent_thread_id")
        return None if parent is None else str(parent)
    return None

def codex_compaction_event_params(
    input: CodexCompactionEvent,
    *,
    session_id: str,
    app_server_client: dict[str, Any],
    runtime: dict[str, Any],
    thread_source: Any | None,
    subagent_source: str | None,
    parent_thread_id: str | None,
) -> dict[str, Any]:
    return {
        "thread_id": input.thread_id,
        "session_id": session_id,
        "turn_id": input.turn_id,
        "app_server_client": dict(app_server_client),
        "runtime": dict(runtime),
        "thread_source": _enum_value(thread_source),
        "subagent_source": subagent_source,
        "parent_thread_id": parent_thread_id,
        "trigger": _enum_value(input.trigger),
        "reason": _enum_value(input.reason),
        "implementation": _enum_value(input.implementation),
        "phase": _enum_value(input.phase),
        "strategy": _enum_value(input.strategy),
        "status": _enum_value(input.status),
        "error": input.error,
        "active_context_tokens_before": input.active_context_tokens_before,
        "active_context_tokens_after": input.active_context_tokens_after,
        "started_at": input.started_at,
        "completed_at": input.completed_at,
        "duration_ms": input.duration_ms,
    }

GuardianReviewedAction = dict[str, Any]


__all__ = [name for name in globals() if not name.startswith("_")]
