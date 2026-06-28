"""Server-notification builders for staged TUI scenario tests."""

from __future__ import annotations

from typing import Any

from pycodex.tui.chatwidget.protocol import ServerNotification


def turn_started(*, turn_id: str = "turn-1", thread_id: str = "primary") -> ServerNotification:
    return ServerNotification("TurnStarted", {"turn": {"id": turn_id, "thread_id": thread_id}})


def turn_completed(
    *,
    turn_id: str = "turn-1",
    thread_id: str = "primary",
    duration_ms: int | None = 10,
) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {"turn": {"id": turn_id, "thread_id": thread_id, "status": "Completed", "duration_ms": duration_ms}},
    )


def turn_failed(
    message: str,
    *,
    exit_code: int = 1,
    turn_id: str = "turn-1",
    thread_id: str = "primary",
) -> ServerNotification:
    return ServerNotification(
        "TurnCompleted",
        {
            "turn": {
                "id": turn_id,
                "thread_id": thread_id,
                "status": "Failed",
                "error": {"message": message, "codex_error_info": None, "exit_code": exit_code},
            }
        },
    )


def agent_delta(delta: str, *, thread_id: str = "primary", turn_id: str = "turn-1") -> ServerNotification:
    return ServerNotification("AgentMessageDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id})


def thread_token_usage_updated(
    *,
    thread_id: str = "primary",
    total_tokens: int = 0,
    input_tokens: int = 0,
    output_tokens: int = 0,
    model_context_window: int | None = None,
) -> ServerNotification:
    return ServerNotification(
        "ThreadTokenUsageUpdated",
        {
            "thread_id": thread_id,
            "token_usage": {
                "total": {
                    "total_tokens": total_tokens,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
                "last": {
                    "total_tokens": total_tokens,
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                },
                "model_context_window": model_context_window,
            },
        },
    )


def mcp_server_status_updated(
    name: str,
    status: str,
    *,
    error: str | None = None,
    thread_id: str = "primary",
) -> ServerNotification:
    payload: dict[str, object] = {"thread_id": thread_id, "name": name, "status": status}
    if error is not None:
        payload["error"] = error
    return ServerNotification("McpServerStatusUpdated", payload)


def thread_closed(thread_id: str) -> ServerNotification:
    return ServerNotification("ThreadClosed", {"thread_id": thread_id})


def reasoning_summary_delta(delta: str, *, thread_id: str = "primary", turn_id: str = "turn-1") -> ServerNotification:
    return ServerNotification("ReasoningSummaryTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id})


def reasoning_summary_part_added(*, thread_id: str = "primary", turn_id: str = "turn-1") -> ServerNotification:
    return ServerNotification("ReasoningSummaryPartAdded", {"thread_id": thread_id, "turn_id": turn_id})


def reasoning_raw_delta(delta: str, *, thread_id: str = "primary", turn_id: str = "turn-1") -> ServerNotification:
    return ServerNotification("ReasoningTextDelta", {"delta": delta, "thread_id": thread_id, "turn_id": turn_id})


def item_started_command(
    command: str,
    *,
    item_id: str = "cmd-1",
    thread_id: str = "primary",
    turn_id: str = "turn-1",
    command_actions: Any = None,
) -> ServerNotification:
    return ServerNotification(
        "ItemStarted",
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "item": {
                "id": item_id,
                "kind": "CommandExecution",
                "status": "InProgress",
                "command": command,
                "command_actions": [] if command_actions is None else command_actions,
            },
        },
    )


def item_completed_command(
    command: str,
    *,
    item_id: str = "cmd-1",
    thread_id: str = "primary",
    turn_id: str = "turn-1",
    status: str = "Completed",
) -> ServerNotification:
    return ServerNotification(
        "ItemCompleted",
        {
            "thread_id": thread_id,
            "turn_id": turn_id,
            "item": {
                "id": item_id,
                "kind": "CommandExecution",
                "status": status,
                "command": command,
                "command_actions": [],
            },
        },
    )
