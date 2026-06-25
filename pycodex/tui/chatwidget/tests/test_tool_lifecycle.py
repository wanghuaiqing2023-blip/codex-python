from pathlib import Path

from pycodex.tui.chatwidget.tool_lifecycle import (
    CollabAgentTool,
    CollabAgentToolCallStatus,
    HistoryCell,
    McpError,
    McpResult,
    PatchApplyStatus,
    ThreadItem,
    ThreadItemKind,
    ToolLifecycleModel,
    mcp_completion_result,
)


def test_patch_and_image_events_append_history_and_redraw_like_rust():
    model = ToolLifecycleModel(cwd=Path("/repo"))

    model.on_patch_apply_begin({Path("a.py"): "change"})
    model.on_view_image_tool_call(Path("/repo/image.png"))
    model.on_image_generation_begin()
    model.on_image_generation_end("call", "prompt", Path("/repo/out.png"))

    assert model.history[0].kind == "patch_event"
    assert model.history[1].kind == "view_image_tool_call"
    assert model.history[2].kind == "image_generation_call"
    assert model.answer_stream_flushes == 3
    assert model.redraw_requests == 2


def test_file_change_completed_marks_work_and_only_failed_patch_adds_failure_cell():
    model = ToolLifecycleModel()

    model.handle_file_change_completed_now(ThreadItem.file_change(PatchApplyStatus.SUCCESS))
    assert model.had_work_activity is True
    assert model.history == []

    model.handle_file_change_completed_now(ThreadItem.file_change(PatchApplyStatus.FAILED))
    assert model.history[-1].kind == "patch_apply_failure"


def test_mcp_started_creates_active_cell_and_completed_flushes_matching_cell():
    model = ToolLifecycleModel()
    started = ThreadItem.mcp_tool_call(id="mcp-1", server="srv", tool="tool", arguments={"x": 1})
    completed = ThreadItem.mcp_tool_call(
        id="mcp-1",
        server="srv",
        tool="tool",
        arguments={"x": 1},
        result=McpResult(content=["ok"], structured_content={"ok": True}),
        duration_ms=42,
    )

    model.handle_mcp_tool_call_started_now(started)
    assert model.active_cell.call_id == "mcp-1"
    assert model.active_cell_revision == 1
    assert model.redraw_requests == 1

    model.handle_mcp_tool_call_completed_now(completed)
    assert model.active_cell is None
    assert model.had_work_activity is True
    assert model.boxed_history == []
    assert model.history[-1].kind == "active_cell"
    assert model.history[-1].data["cell"].completed is True


def test_mcp_completed_without_matching_active_cell_creates_and_flushes_cell_with_error_extra():
    model = ToolLifecycleModel()
    completed = ThreadItem.mcp_tool_call(
        id="mcp-2",
        server="srv",
        tool="tool",
        error=McpError("boom"),
        duration_ms=-10,
    )

    model.handle_mcp_tool_call_completed_now(completed)

    assert model.history[-1].kind == "active_cell"
    assert model.history[-1].data["cell"].duration_ms == 0
    assert model.boxed_history[-1].kind == "mcp_tool_call_error"
    assert model.boxed_history[-1].data["message"] == "boom"


def test_web_search_begin_and_end_update_active_cell_or_fallback_history():
    model = ToolLifecycleModel()

    model.on_web_search_begin("search-1")
    model.on_web_search_end("search-1", "query", "action")

    assert model.history[-1].kind == "active_cell"
    assert model.history[-1].data["cell"].completed is True
    assert model.had_work_activity is True

    model.on_web_search_end("missing", "q2", "action2")
    assert model.history[-1].kind == "web_search_call"
    assert model.history[-1].data["query"] == "q2"


def test_defer_paths_queue_started_and_completed_items():
    model = ToolLifecycleModel(defer_items=True)
    started = ThreadItem.mcp_tool_call(id="mcp", server="srv", tool="tool")
    completed = ThreadItem.file_change(PatchApplyStatus.SUCCESS)

    model.on_mcp_tool_call_started(started)
    model.on_file_change_completed(completed)

    assert model.deferred_queue.started == [started]
    assert model.deferred_queue.completed == [completed]
    assert model.history == []


def test_collab_spawn_request_is_cached_until_terminal_status_and_emits_event():
    model = ToolLifecycleModel()
    start = ThreadItem.collab_agent_tool_call(
        id="spawn",
        tool=CollabAgentTool.SPAWN_AGENT,
        status=CollabAgentToolCallStatus.IN_PROGRESS,
        payload={"spawn_request": {"task": "build"}},
    )
    done = ThreadItem.collab_agent_tool_call(
        id="spawn",
        tool=CollabAgentTool.SPAWN_AGENT,
        status=CollabAgentToolCallStatus.COMPLETED,
    )

    model.on_collab_agent_tool_call(start)
    assert model.pending_collab_spawn_requests["spawn"] == {"task": "build"}
    assert model.history[-1].kind == "collab_agent_tool_call"

    model.on_collab_agent_tool_call(done)
    assert "spawn" not in model.pending_collab_spawn_requests
    assert model.history[-1].data["spawn_request"] == {"task": "build"}


def test_queued_item_dispatches_only_command_mcp_and_file_change_variants():
    model = ToolLifecycleModel()
    command = ThreadItem(ThreadItemKind.COMMAND_EXECUTION)
    mcp = ThreadItem.mcp_tool_call(id="mcp", server="srv", tool="tool")
    file_change = ThreadItem.file_change(PatchApplyStatus.SUCCESS)

    model.handle_queued_item_started_now(command)
    model.handle_queued_item_started_now(mcp)
    model.handle_queued_item_completed_now(command)
    model.handle_queued_item_completed_now(file_change)

    assert model.command_started == [command]
    assert model.command_completed == [command]
    assert model.had_work_activity is True


def test_mcp_completion_result_shapes_match_rust_error_precedence():
    assert mcp_completion_result(ThreadItem.mcp_tool_call(id="a", server="s", tool="t", error=McpError("e"))) == (
        "error",
        "e",
    )
    assert mcp_completion_result(ThreadItem.mcp_tool_call(id="a", server="s", tool="t")) == (
        "error",
        "MCP tool call completed without a result",
    )
