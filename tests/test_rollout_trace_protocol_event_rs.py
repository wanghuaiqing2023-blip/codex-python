from pycodex.rollout_trace import ExecutionStatus, ThreadTraceContext
from test_rollout_trace_thread_rs import metadata, read_json, read_jsonl, single_bundle_dir


def test_protocol_wrapper_records_selected_events_as_raw_payloads(tmp_path):
    # Rust test: thread_tests.rs protocol_wrapper_records_selected_events_as_raw_payloads
    # Contract: record_protocol_event wraps selected EventMsg variants as
    # ProtocolEventObserved breadcrumbs with the original event persisted as a
    # protocol raw payload.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    trace.record_protocol_event({"type": "shutdown_complete"})
    trace.record_protocol_event({"type": "token_count", "tokens": 10})

    bundle = single_bundle_dir(tmp_path)
    events = read_jsonl(bundle / "trace.jsonl")
    observed = [event for event in events if event["payload"]["type"] == "protocol_event_observed"]

    assert len(observed) == 1
    assert observed[0]["payload"]["event_type"] == "shutdown_complete"
    assert read_json(bundle / observed[0]["payload"]["event_payload"]["path"]) == {
        "type": "shutdown_complete"
    }


def test_protocol_wrapper_allowlist_follows_protocol_event_rs(tmp_path):
    # Rust source: protocol_event.rs wrapped_protocol_event_type.
    # Contract: only selected coarse protocol lifecycle/status events are
    # persisted as ProtocolEventObserved breadcrumbs; other protocol traffic is
    # ignored by this wrapper path.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    selected = [
        {"type": "session_configured", "model": "gpt-test"},
        {"type": "turn_started", "turn_id": "turn-1"},
        {"type": "turn_complete", "turn_id": "turn-1"},
        {"type": "turn_aborted", "turn_id": "turn-2", "reason": "interrupted"},
        {"type": "thread_rolled_back", "thread_id": "thread-root"},
        {"type": "error", "message": "boom"},
        {"type": "warning", "message": "careful"},
        {"type": "shutdown_complete"},
    ]
    for event in selected:
        trace.record_protocol_event(event)
    trace.record_protocol_event({"type": "token_count", "tokens": 10})

    bundle = single_bundle_dir(tmp_path)
    observed = [
        event for event in read_jsonl(bundle / "trace.jsonl")
        if event["payload"]["type"] == "protocol_event_observed"
    ]

    assert [event["payload"]["event_type"] for event in observed] == [
        event["type"] for event in selected
    ]
    for raw_event, source_event in zip(observed, selected):
        assert read_json(bundle / raw_event["payload"]["event_payload"]["path"]) == source_event


def test_record_codex_turn_event_maps_lifecycle_status_and_context(tmp_path):
    # Rust source: protocol_event.rs codex_turn_trace_event
    # Contract: TurnStarted/TurnComplete/TurnAborted map to typed Codex turn
    # raw events; aborted events without turn_id use the default turn id.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    trace.record_codex_turn_event("default-turn", {"type": "turn_started", "turn_id": "turn-1"})
    trace.record_codex_turn_event("default-turn", {"type": "turn_complete", "turn_id": "turn-1"})
    trace.record_codex_turn_event("turn-fallback", {"type": "turn_aborted", "reason": "interrupted"})

    events = read_jsonl(single_bundle_dir(tmp_path) / "trace.jsonl")[-3:]
    assert events[0]["codex_turn_id"] == "turn-1"
    assert events[0]["payload"] == {
        "type": "codex_turn_started",
        "codex_turn_id": "turn-1",
        "thread_id": "thread-root",
    }
    assert events[1]["codex_turn_id"] == "turn-1"
    assert events[1]["payload"] == {
        "type": "codex_turn_ended",
        "codex_turn_id": "turn-1",
        "status": "completed",
    }
    assert events[2]["codex_turn_id"] == "turn-fallback"
    assert events[2]["payload"] == {
        "type": "codex_turn_ended",
        "codex_turn_id": "turn-fallback",
        "status": "cancelled",
    }


def test_record_tool_call_event_maps_exec_runtime_and_filters_user_shell(tmp_path):
    # Rust source: protocol_event.rs tool_runtime_trace_event
    # Contract: exec begin/end protocol events from Codex runtime become
    # ToolCallRuntimeStarted/Ended events, while UserShell exec events are
    # ignored.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    trace.record_tool_call_event(
        "turn-1",
        {
            "type": "exec_command_begin",
            "call_id": "tool-1",
            "source": "tool",
            "command": ["cargo", "test"],
            "cwd": "/repo",
        },
    )
    trace.record_tool_call_event(
        "turn-1",
        {
            "type": "exec_command_end",
            "call_id": "tool-1",
            "source": "tool",
            "stdout": "ok\n",
            "stderr": "",
            "exit_code": 0,
            "formatted_output": "ok\n",
            "status": "completed",
        },
    )
    trace.record_tool_call_event(
        "turn-1",
        {
            "type": "exec_command_begin",
            "call_id": "user-shell",
            "source": "user_shell",
            "command": ["bash"],
            "cwd": "/repo",
        },
    )

    bundle = single_bundle_dir(tmp_path)
    events = [
        event
        for event in read_jsonl(bundle / "trace.jsonl")
        if event["payload"]["type"].startswith("tool_call_runtime_")
    ]

    assert [event["payload"]["type"] for event in events] == [
        "tool_call_runtime_started",
        "tool_call_runtime_ended",
    ]
    assert events[0]["thread_id"] == "thread-root"
    assert events[0]["codex_turn_id"] == "turn-1"
    assert events[0]["payload"]["tool_call_id"] == "tool-1"
    assert read_json(bundle / events[0]["payload"]["runtime_payload"]["path"])["command"] == [
        "cargo",
        "test",
    ]
    assert events[1]["payload"]["status"] == ExecutionStatus.COMPLETED.value


def test_record_tool_call_event_maps_patch_mcp_and_collab_status(tmp_path):
    # Rust source: protocol_event.rs tool_runtime_trace_event and
    # TraceExecutionStatus impls. Contract: patch declined maps to cancelled,
    # MCP result errors map to failed, and spawn end without a child thread maps
    # to failed.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    trace.record_tool_call_event(
        "turn-1",
        {"type": "patch_apply_end", "call_id": "patch-1", "status": "declined"},
    )
    trace.record_tool_call_event(
        "turn-1",
        {"type": "mcp_tool_call_end", "call_id": "mcp-1", "ok": False},
    )
    trace.record_tool_call_event(
        "turn-1",
        {"type": "collab_agent_spawn_end", "call_id": "spawn-1", "new_thread_id": None},
    )

    events = [
        event
        for event in read_jsonl(single_bundle_dir(tmp_path) / "trace.jsonl")
        if event["payload"]["type"] == "tool_call_runtime_ended"
    ]

    assert [(event["payload"]["tool_call_id"], event["payload"]["status"]) for event in events] == [
        ("patch-1", "cancelled"),
        ("mcp-1", "failed"),
        ("spawn-1", "failed"),
    ]
