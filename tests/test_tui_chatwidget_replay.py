from __future__ import annotations

from types import SimpleNamespace

import pytest

from pycodex.tui.chatwidget.replay import (
    ReplayKind,
    ThreadItemRenderSource,
    Turn,
    TurnStatus,
    handle_thread_item,
    replay_thread_turns,
)


class Widget:
    def __init__(self) -> None:
        self.events: list[tuple] = []
        self.config = SimpleNamespace(show_raw_agent_reasoning=False)
        self.last_non_retry_error = "old"
        self.thread_id = "thread-1"

    def __getattr__(self, name: str):
        def recorder(*args):
            self.events.append((name, *args))

        return recorder


def test_replay_thread_turns_starts_in_progress_and_completes_terminal_turn() -> None:
    widget = Widget()
    turns = [
        Turn(
            id="turn-1",
            status=TurnStatus.IN_PROGRESS,
            items=({"kind": "UserMessage", "content": "hello"},),
        ),
        Turn(id="turn-2", status=TurnStatus.COMPLETED, error=None, duration_ms=42),
    ]

    replay_thread_turns(widget, turns, ReplayKind.INITIAL_HISTORY)

    assert widget.last_non_retry_error is None
    assert widget.events[0] == ("on_task_started",)
    assert widget.events[1] == ("on_committed_user_message", "hello", True)
    completion = widget.events[2]
    assert completion[0] == "handle_turn_completed_notification"
    assert completion[1].thread_id == "thread-1"
    assert completion[1].turn.id == "turn-2"
    assert completion[1].turn.items == ()
    assert completion[2] == ReplayKind.INITIAL_HISTORY


def test_handle_thread_item_replays_reasoning_summary_and_optionally_raw_content() -> None:
    widget = Widget()

    handle_thread_item(
        widget,
        {"kind": "Reasoning", "summary": ["s1"], "content": ["raw"]},
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )

    assert widget.events == [
        ("on_agent_reasoning_delta", "s1"),
        ("on_agent_reasoning_final",),
    ]

    widget = Widget()
    widget.config.show_raw_agent_reasoning = True
    handle_thread_item(
        widget,
        {"kind": "Reasoning", "summary": ["s1"], "content": ["raw"]},
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )

    assert widget.events == [
        ("on_agent_reasoning_delta", "s1"),
        ("on_agent_reasoning_delta", "raw"),
        ("on_agent_reasoning_final",),
    ]


@pytest.mark.parametrize(
    ("item", "expected"),
    [
        ({"kind": "CommandExecution", "status": "InProgress"}, "on_command_execution_started"),
        ({"kind": "CommandExecution", "status": "Completed"}, "on_command_execution_completed"),
        ({"kind": "FileChange", "status": "Completed"}, "on_file_change_completed"),
        ({"kind": "McpToolCall", "status": "InProgress"}, "on_mcp_tool_call_started"),
        ({"kind": "McpToolCall", "status": "Failed"}, "on_mcp_tool_call_completed"),
    ],
)
def test_handle_thread_item_routes_status_sensitive_tool_items(item, expected) -> None:
    widget = Widget()

    handle_thread_item(widget, item, "turn-1", ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY))

    assert widget.events[0][0] == expected


def test_handle_thread_item_skips_in_progress_file_change_and_noop_variants() -> None:
    widget = Widget()

    handle_thread_item(widget, {"kind": "FileChange", "status": "InProgress"}, "turn-1", ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY))
    handle_thread_item(widget, {"kind": "HookPrompt"}, "turn-1", ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY))
    handle_thread_item(widget, {"kind": "DynamicToolCall"}, "turn-1", ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY))

    assert widget.events == []


def test_thread_snapshot_without_turn_id_requests_redraw_after_dispatch() -> None:
    widget = Widget()

    handle_thread_item(widget, {"kind": "ContextCompaction"}, "", ThreadItemRenderSource.replay(ReplayKind.THREAD_SNAPSHOT))

    assert widget.events == [
        ("add_info_message", "Context compacted", None),
        ("request_redraw",),
    ]


def test_unknown_thread_item_variant_is_rejected() -> None:
    widget = Widget()

    with pytest.raises(ValueError):
        handle_thread_item(widget, {"kind": "FutureItem"}, "turn-1", ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY))
