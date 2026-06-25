from __future__ import annotations

from types import SimpleNamespace

import pytest

from pycodex.tui.chatwidget.replay import (
    AgentMessageItem,
    ReplayKind,
    ThreadItemRenderSource,
    Turn,
    TurnStatus,
    handle_thread_item,
    replay_thread_turns,
)


class Widget:
    def __init__(self) -> None:
        self.events = []  # type: list[tuple]
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


def test_agent_message_is_rehydrated_as_text_item_with_memory_citation() -> None:
    widget = Widget()
    citation = {
        "entries": [{"path": "src/lib.rs", "line_start": 1, "line_end": 2, "note": "note"}],
        "thread_ids": ["rollout-1"],
    }

    handle_thread_item(
        widget,
        {
            "kind": "AgentMessage",
            "id": "msg-1",
            "text": "answer",
            "phase": "final",
            "memory_citation": citation,
        },
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )

    event = widget.events[0]
    assert event[0] == "on_agent_message_item_completed"
    assert isinstance(event[1], AgentMessageItem)
    assert event[1].id == "msg-1"
    assert event[1].content == ({"type": "Text", "text": "answer"},)
    assert event[1].phase == "final"
    assert event[1].memory_citation == {
        "entries": ({"path": "src/lib.rs", "line_start": 1, "line_end": 2, "note": "note"},),
        "rollout_ids": ["rollout-1"],
    }
    assert event[2] is True


def test_plan_web_search_and_image_items_route_to_rust_callbacks() -> None:
    widget = Widget()

    handle_thread_item(
        widget,
        {"kind": "Plan", "text": "1. inspect"},
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )
    handle_thread_item(
        widget,
        {"kind": "WebSearch", "id": "search-1", "query": "codex", "action": None},
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )
    handle_thread_item(
        widget,
        {"kind": "ImageView", "path": "diagram.png"},
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )
    handle_thread_item(
        widget,
        {
            "kind": "ImageGeneration",
            "id": "img-1",
            "revised_prompt": "a cat",
            "saved_path": "cat.png",
        },
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )

    assert widget.events == [
        ("on_plan_item_completed", "1. inspect"),
        ("on_web_search_begin", "search-1"),
        ("on_web_search_end", "search-1", "codex", "Other"),
        ("on_view_image_tool_call", "diagram.png"),
        ("on_image_generation_end", "img-1", "a cat", "cat.png"),
    ]


def test_review_mode_enters_only_from_replay_but_exit_always_routes() -> None:
    widget = Widget()

    handle_thread_item(
        widget,
        {"kind": "EnteredReviewMode", "review": {"preset": "review"}},
        "turn-1",
        ThreadItemRenderSource.live(),
    )
    handle_thread_item(
        widget,
        {"kind": "EnteredReviewMode", "review": {"preset": "review"}},
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )
    handle_thread_item(
        widget,
        {"kind": "ExitedReviewMode"},
        "turn-1",
        ThreadItemRenderSource.live(),
    )

    assert widget.events == [
        ("enter_review_mode_with_hint", {"preset": "review"}, True),
        ("exit_review_mode_after_item",),
    ]


def test_collab_agent_item_is_forwarded_unchanged() -> None:
    widget = Widget()
    item = {
        "kind": "CollabAgentToolCall",
        "id": "agent-1",
        "tool": "delegate",
        "status": "Completed",
    }

    handle_thread_item(
        widget,
        item,
        "turn-1",
        ThreadItemRenderSource.replay(ReplayKind.INITIAL_HISTORY),
    )

    assert widget.events == [("on_collab_agent_tool_call", item)]


def test_replay_thread_turns_handles_failed_and_interrupted_terminal_turns() -> None:
    widget = Widget()
    turns = [
        {
            "id": "turn-failed",
            "items": (),
            "status": "Failed",
            "error": "boom",
            "started_at": "start",
            "completed_at": "end",
            "duration_ms": 7,
        },
        {
            "id": "turn-interrupted",
            "items": (),
            "status": "Interrupted",
            "error": None,
            "started_at": None,
            "completed_at": None,
            "duration_ms": None,
        },
    ]

    replay_thread_turns(widget, turns, ReplayKind.THREAD_SNAPSHOT)

    assert widget.events[0][0] == "handle_turn_completed_notification"
    assert widget.events[0][1].turn.id == "turn-failed"
    assert widget.events[0][1].turn.error == "boom"
    assert widget.events[0][1].turn.started_at == "start"
    assert widget.events[0][1].turn.completed_at == "end"
    assert widget.events[0][1].turn.duration_ms == 7
    assert widget.events[0][2] == ReplayKind.THREAD_SNAPSHOT
    assert widget.events[1][0] == "handle_turn_completed_notification"
    assert widget.events[1][1].turn.id == "turn-interrupted"


def test_live_reasoning_only_finalizes_without_replaying_deltas() -> None:
    widget = Widget()

    handle_thread_item(
        widget,
        {"kind": "Reasoning", "summary": ["s1"], "content": ["raw"]},
        "turn-1",
        ThreadItemRenderSource.live(),
    )

    assert widget.events == [("on_agent_reasoning_final",)]
