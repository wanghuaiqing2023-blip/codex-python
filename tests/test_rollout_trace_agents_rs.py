from __future__ import annotations

import json
from pathlib import Path

from pycodex.rollout_trace import (
    ExecutionStatus,
    RawPayloadKind,
    RawToolCallRequester,
    RawTraceEventContext,
    RawTraceEventPayload,
    RolloutStatus,
    TraceAnchor,
    TraceWriter,
    replay_bundle,
)


ROOT_THREAD = "019d0000-0000-7000-8000-000000000001"
CHILD_THREAD = "019d0000-0000-7000-8000-000000000002"


def test_child_thread_metadata_creates_spawn_origin_without_delivery_edge(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: child_thread_metadata_creates_spawn_origin_without_delivery_edge
    # Contract: child thread metadata records spawned origin but does not
    # materialize a delivery interaction edge before a recipient-side message
    # or runtime fallback exists.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", CHILD_THREAD)
    metadata = writer.write_json_payload(
        RawPayloadKind.SESSION_METADATA,
        {
            "nickname": "James",
            "agent_role": "explorer",
            "task_name": "repo_file_counter",
            "model": "gpt-test",
            "session_source": {
                "subagent": {
                    "thread_spawn": {
                        "parent_thread_id": ROOT_THREAD,
                        "agent_path": "/root/repo_file_counter",
                        "agent_nickname": "James",
                        "agent_role": "explorer",
                    }
                }
            },
        },
    )
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id=CHILD_THREAD,
            agent_path="/root/repo_file_counter",
            metadata_payload=metadata,
        )
    )

    replayed = replay_bundle(tmp_path)
    thread = replayed.threads[CHILD_THREAD]

    assert thread.nickname == "James"
    assert thread.default_model == "gpt-test"
    assert thread.origin.type == "spawned"
    assert thread.origin.parent_thread_id == ROOT_THREAD
    assert thread.origin.spawn_edge_id == f"edge:spawn:{ROOT_THREAD}:{CHILD_THREAD}"
    assert thread.origin.task_name == "repo_file_counter"
    assert thread.origin.agent_role == "explorer"
    assert f"edge:spawn:{ROOT_THREAD}:{CHILD_THREAD}" not in replayed.interaction_edges


def test_spawn_runtime_payload_falls_back_to_child_thread_without_delivery_item(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: spawn_runtime_payload_falls_back_to_child_thread_without_delivery_item
    # Contract: a spawn edge with no recipient-side delivered task item falls
    # back to the existing child thread while preserving raw tool evidence.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", ROOT_THREAD)
    _append_started_root_agent(writer)
    invocation, begin, end, result = _append_spawn_agent_tool_lifecycle(writer)
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id=CHILD_THREAD,
            agent_path="/root/repo_file_counter",
            metadata_payload=None,
        )
    )

    replayed = replay_bundle(tmp_path)
    edge_id = f"edge:spawn:{ROOT_THREAD}:{CHILD_THREAD}"
    edge = replayed.interaction_edges[edge_id]

    assert edge.kind == "spawn_agent"
    assert edge.source == TraceAnchor.ToolCall("call-spawn")
    assert edge.target == TraceAnchor.Thread(CHILD_THREAD)
    assert edge.carried_item_ids == []
    assert edge.carried_raw_payload_ids == [
        invocation.raw_payload_id,
        begin.raw_payload_id,
        end.raw_payload_id,
        result.raw_payload_id,
    ]


def test_spawn_runtime_payload_targets_delivered_child_message(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: spawn_runtime_payload_targets_delivered_child_message
    # Contract: spawn edges prefer the child-side delivered task message over
    # the child-thread fallback when the inter-agent mailbox item appears.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", ROOT_THREAD)
    _append_started_root_agent(writer)
    invocation, begin, end, result = _append_spawn_agent_tool_lifecycle(writer)
    _append_started_child_thread(writer, "/root/repo_file_counter")
    _append_inference_request(
        writer,
        thread_id=CHILD_THREAD,
        turn_id="turn-child-1",
        inference_id="inference-child-1",
        items=[
            _message_item(
                "assistant",
                _inter_agent_message("/root", "/root/repo_file_counter", "count", True),
            )
        ],
    )

    replayed = replay_bundle(tmp_path)
    edge = replayed.interaction_edges[f"edge:spawn:{ROOT_THREAD}:{CHILD_THREAD}"]

    assert edge.kind == "spawn_agent"
    assert edge.source == TraceAnchor.ToolCall("call-spawn")
    assert edge.target.type == "conversation_item"
    target_item_id = edge.target.item_id
    assert target_item_id is not None
    assert edge.carried_item_ids == [target_item_id]
    assert replayed.conversation_items[target_item_id].thread_id == CHILD_THREAD
    assert edge.carried_raw_payload_ids == [
        invocation.raw_payload_id,
        begin.raw_payload_id,
        end.raw_payload_id,
        result.raw_payload_id,
    ]


def test_send_message_runtime_payload_targets_delivered_child_message(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: send_message_runtime_payload_targets_delivered_child_message
    # Contract: send_message runtime begin/end payloads resolve to the precise
    # recipient-side inter-agent mailbox conversation item and record end time.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", ROOT_THREAD)
    _append_started_root_agent(writer)
    _append_send_message_tool_lifecycle(writer)
    _append_started_child_thread(writer, "/root/child")
    _append_inference_request(
        writer,
        thread_id=CHILD_THREAD,
        turn_id="turn-child-1",
        inference_id="inference-child-1",
        items=[
            _message_item(
                "assistant",
                _inter_agent_message("/root", "/root/child", "hello", False),
            )
        ],
    )

    replayed = replay_bundle(tmp_path)
    edge = replayed.interaction_edges["edge:tool:call-send"]

    assert edge.kind == "send_message"
    assert edge.source == TraceAnchor.ToolCall("call-send")
    assert edge.target.type == "conversation_item"
    target_item_id = edge.target.item_id
    assert target_item_id is not None
    assert edge.carried_item_ids == [target_item_id]
    assert replayed.conversation_items[target_item_id].thread_id == CHILD_THREAD
    assert edge.ended_at_unix_ms is not None


def test_close_agent_runtime_payload_targets_thread(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: close_agent_runtime_payload_targets_thread
    # Contract: close_agent runtime payloads create a thread-targeted edge,
    # carry all tool evidence, and child thread completion does not end rollout.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", ROOT_THREAD)
    _append_started_root_agent(writer)
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id=CHILD_THREAD,
            agent_path="/root/child",
            metadata_payload=None,
        )
    )
    invocation, begin, end, result = _append_close_agent_tool_lifecycle(writer)
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadEnded",
            thread_id=CHILD_THREAD,
            status=RolloutStatus.COMPLETED,
        )
    )

    replayed = replay_bundle(tmp_path)
    edge = replayed.interaction_edges["edge:tool:call-close"]

    assert edge.kind == "close_agent"
    assert edge.source == TraceAnchor.ToolCall("call-close")
    assert edge.target == TraceAnchor.Thread(CHILD_THREAD)
    assert edge.carried_item_ids == []
    assert edge.carried_raw_payload_ids == [
        invocation.raw_payload_id,
        begin.raw_payload_id,
        end.raw_payload_id,
        result.raw_payload_id,
    ]
    assert replayed.threads[CHILD_THREAD].execution.status == ExecutionStatus.COMPLETED
    assert replayed.status == RolloutStatus.RUNNING


def test_agent_result_edge_links_child_result_to_parent_notification(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: agent_result_edge_links_child_result_to_parent_notification
    # Contract: child completion notifications link the latest child assistant
    # message to the parent-side delivered notification item.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", ROOT_THREAD)
    _append_started_root_agent(writer)
    _append_started_child_thread(writer, "/root/child")
    _append_inference_request(
        writer,
        thread_id=CHILD_THREAD,
        turn_id="turn-child-1",
        inference_id="inference-child-1",
        items=[_message_item("assistant", "task")],
    )
    _append_inference_completed(
        writer,
        thread_id=CHILD_THREAD,
        turn_id="turn-child-1",
        inference_id="inference-child-1",
        items=[_message_item("assistant", "done")],
    )
    notification = '<subagent_notification>{"agent_path":"/root/child","status":{"completed":"done"}}</subagent_notification>'
    carried_payload = _append_agent_result_observed(writer, notification)
    _append_turn_started(writer, ROOT_THREAD, "turn-root-1")
    _append_inference_request(
        writer,
        thread_id=ROOT_THREAD,
        turn_id="turn-root-1",
        inference_id="inference-root-1",
        items=[
            _message_item(
                "assistant",
                _inter_agent_message("/root/child", "/root", notification, False),
            )
        ],
    )

    replayed = replay_bundle(tmp_path)
    edge = replayed.interaction_edges["edge:agent_result:thread-child:turn-child-1:thread-root"]

    assert edge.kind == "agent_result"
    assert edge.source.type == "conversation_item"
    source_item_id = edge.source.item_id
    assert source_item_id is not None
    assert _single_text(replayed.conversation_items[source_item_id]) == "done"
    assert edge.target.type == "conversation_item"
    target_item_id = edge.target.item_id
    assert target_item_id is not None
    assert replayed.conversation_items[target_item_id].thread_id == ROOT_THREAD
    assert edge.carried_item_ids == [target_item_id]
    assert edge.carried_raw_payload_ids == [carried_payload.raw_payload_id]


def test_agent_result_edge_falls_back_to_child_thread_without_result_message(tmp_path: Path) -> None:
    # Source: rust_test_migrated
    # Rust crate: codex-rollout-trace
    # Rust module: src/reducer/tool/agents.rs
    # Rust test: agent_result_edge_falls_back_to_child_thread_without_result_message
    # Contract: failed/cancelled child notifications can target the parent
    # notification item while using the child thread as source fallback.
    writer = TraceWriter.create(tmp_path, "trace-1", "rollout-1", ROOT_THREAD)
    _append_started_root_agent(writer)
    _append_started_child_thread(writer, "/root/child")
    notification = '<subagent_notification>{"agent_path":"/root/child","status":{"failed":"boom"}}</subagent_notification>'
    carried_payload = _append_agent_result_observed(writer, notification)
    _append_turn_started(writer, ROOT_THREAD, "turn-root-1")
    _append_inference_request(
        writer,
        thread_id=ROOT_THREAD,
        turn_id="turn-root-1",
        inference_id="inference-root-1",
        items=[
            _message_item(
                "assistant",
                _inter_agent_message("/root/child", "/root", notification, False),
            )
        ],
    )

    replayed = replay_bundle(tmp_path)
    edge = replayed.interaction_edges["edge:agent_result:thread-child:turn-child-1:thread-root"]

    assert edge.kind == "agent_result"
    assert edge.source == TraceAnchor.Thread(CHILD_THREAD)
    assert edge.target.type == "conversation_item"
    target_item_id = edge.target.item_id
    assert target_item_id is not None
    assert replayed.conversation_items[target_item_id].thread_id == ROOT_THREAD
    assert edge.carried_item_ids == [target_item_id]
    assert edge.carried_raw_payload_ids == [carried_payload.raw_payload_id]


def _append_started_root_agent(writer: TraceWriter) -> None:
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id=ROOT_THREAD,
            agent_path="/root",
            metadata_payload=None,
        )
    )
    writer.append_with_context(
        RawTraceEventContext(ROOT_THREAD, "turn-1"),
        RawTraceEventPayload.variant(
            "CodexTurnStarted",
            codex_turn_id="turn-1",
            thread_id=ROOT_THREAD,
        ),
    )


def _append_started_child_thread(writer: TraceWriter, agent_path: str) -> None:
    writer.append(
        RawTraceEventPayload.variant(
            "ThreadStarted",
            thread_id=CHILD_THREAD,
            agent_path=agent_path,
            metadata_payload=None,
        )
    )
    writer.append_with_context(
        RawTraceEventContext(CHILD_THREAD, "turn-child-1"),
        RawTraceEventPayload.variant(
            "CodexTurnStarted",
            codex_turn_id="turn-child-1",
            thread_id=CHILD_THREAD,
        ),
    )


def _append_turn_started(writer: TraceWriter, thread_id: str, turn_id: str) -> None:
    writer.append_with_context(
        RawTraceEventContext(thread_id, turn_id),
        RawTraceEventPayload.variant(
            "CodexTurnStarted",
            codex_turn_id=turn_id,
            thread_id=thread_id,
        ),
    )


def _append_inference_request(
    writer: TraceWriter,
    *,
    thread_id: str,
    turn_id: str,
    inference_id: str,
    items: list[dict],
) -> None:
    request = writer.write_json_payload(
        RawPayloadKind.INFERENCE_REQUEST,
        {
            "model": "gpt-test",
            "provider_name": "test-provider",
            "input": items,
        },
    )
    writer.append_with_context(
        RawTraceEventContext(thread_id, turn_id),
        RawTraceEventPayload.variant(
            "InferenceStarted",
            inference_call_id=inference_id,
            thread_id=thread_id,
            codex_turn_id=turn_id,
            model="gpt-test",
            provider_name="test-provider",
            request_payload=request,
        ),
    )


def _append_inference_completed(
    writer: TraceWriter,
    *,
    thread_id: str,
    turn_id: str,
    inference_id: str,
    items: list[dict],
) -> None:
    response = writer.write_json_payload(
        RawPayloadKind.INFERENCE_RESPONSE,
        {
            "output_items": items,
            "token_usage": {
                "input_tokens": 1,
                "cached_input_tokens": 0,
                "output_tokens": 1,
                "reasoning_output_tokens": 0,
            },
        },
    )
    writer.append_with_context(
        RawTraceEventContext(thread_id, turn_id),
        RawTraceEventPayload.variant(
            "InferenceCompleted",
            inference_call_id=inference_id,
            response_id=f"response-{inference_id}",
            upstream_request_id=None,
            response_payload=response,
        ),
    )


def _append_spawn_agent_tool_lifecycle(writer: TraceWriter):
    invocation = writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "spawn_agent",
            "payload": {
                "type": "function",
                "arguments": '{"task_name":"repo_file_counter","message":"count"}',
            },
        },
    )
    context = RawTraceEventContext(ROOT_THREAD, "turn-1")
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="call-spawn",
            model_visible_call_id="call-spawn",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "spawn_agent"},
            summary={
                "type": "generic",
                "label": "spawn_agent",
                "input_preview": None,
                "output_preview": None,
            },
            invocation_payload=invocation,
        ),
    )
    begin = writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "call-spawn",
            "sender_thread_id": ROOT_THREAD,
            "prompt": "count",
        },
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallRuntimeStarted",
            tool_call_id="call-spawn",
            runtime_payload=begin,
        ),
    )
    end = writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "call-spawn",
            "sender_thread_id": ROOT_THREAD,
            "new_thread_id": CHILD_THREAD,
            "prompt": "count",
            "model": "gpt-test",
            "reasoning_effort": "medium",
            "status": "running",
        },
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallRuntimeEnded",
            tool_call_id="call-spawn",
            status=ExecutionStatus.COMPLETED,
            runtime_payload=end,
        ),
    )
    result = writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {"task_name": "/root/repo_file_counter"},
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="call-spawn",
            status=ExecutionStatus.COMPLETED,
            result_payload=result,
        ),
    )
    return invocation, begin, end, result


def _append_send_message_tool_lifecycle(writer: TraceWriter) -> None:
    invocation = writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "send_message",
            "payload": {
                "type": "function",
                "arguments": '{"target":"/root/child","message":"hello"}',
            },
        },
    )
    context = RawTraceEventContext(ROOT_THREAD, "turn-1")
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="call-send",
            model_visible_call_id="call-send",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "send_message"},
            summary={
                "type": "generic",
                "label": "send_message",
                "input_preview": None,
                "output_preview": None,
            },
            invocation_payload=invocation,
        ),
    )
    begin = writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "call-send",
            "sender_thread_id": ROOT_THREAD,
            "receiver_thread_id": CHILD_THREAD,
            "prompt": "hello",
            "status": "running",
        },
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallRuntimeStarted",
            tool_call_id="call-send",
            runtime_payload=begin,
        ),
    )
    end = writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "call-send",
            "sender_thread_id": ROOT_THREAD,
            "receiver_thread_id": CHILD_THREAD,
            "prompt": "hello",
            "status": "running",
        },
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallRuntimeEnded",
            tool_call_id="call-send",
            status=ExecutionStatus.COMPLETED,
            runtime_payload=end,
        ),
    )


def _append_close_agent_tool_lifecycle(writer: TraceWriter):
    invocation = writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "close_agent",
            "payload": {
                "type": "function",
                "arguments": '{"target":"/root/child"}',
            },
        },
    )
    context = RawTraceEventContext(ROOT_THREAD, "turn-1")
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="call-close",
            model_visible_call_id="call-close",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "close_agent"},
            summary={
                "type": "generic",
                "label": "close_agent",
                "input_preview": None,
                "output_preview": None,
            },
            invocation_payload=invocation,
        ),
    )
    begin = writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "call-close",
            "sender_thread_id": ROOT_THREAD,
            "receiver_thread_id": CHILD_THREAD,
        },
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallRuntimeStarted",
            tool_call_id="call-close",
            runtime_payload=begin,
        ),
    )
    end = writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "call-close",
            "sender_thread_id": ROOT_THREAD,
            "receiver_thread_id": CHILD_THREAD,
            "receiver_agent_nickname": "Scout",
            "receiver_agent_role": "explorer",
            "status": "running",
        },
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallRuntimeEnded",
            tool_call_id="call-close",
            status=ExecutionStatus.COMPLETED,
            runtime_payload=end,
        ),
    )
    result = writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {"previous_status": "running"},
    )
    writer.append_with_context(
        context,
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="call-close",
            status=ExecutionStatus.COMPLETED,
            result_payload=result,
        ),
    )
    return invocation, begin, end, result


def _message_item(role: str, text: str) -> dict:
    return {"type": "message", "role": role, "content": [{"type": "text", "text": text}]}


def _append_agent_result_observed(writer: TraceWriter, notification: str):
    carried_payload = writer.write_json_payload(
        RawPayloadKind.AGENT_RESULT,
        {
            "child_agent_path": "/root/child",
            "message": notification,
            "status": {"completed": "done"},
        },
    )
    writer.append_with_context(
        RawTraceEventContext(CHILD_THREAD, "turn-child-1"),
        RawTraceEventPayload.variant(
            "AgentResultObserved",
            edge_id="edge:agent_result:thread-child:turn-child-1:thread-root",
            child_thread_id=CHILD_THREAD,
            child_codex_turn_id="turn-child-1",
            parent_thread_id=ROOT_THREAD,
            message=notification,
            carried_payload=carried_payload,
        ),
    )
    return carried_payload


def _single_text(item) -> str:
    assert len(item.body.parts) == 1
    part = item.body.parts[0]
    assert part.type == "text"
    assert part.text is not None
    return part.text


def _inter_agent_message(author: str, recipient: str, content: str, trigger_turn: bool) -> str:
    return json.dumps(
        {
            "author": author,
            "recipient": recipient,
            "other_recipients": [],
            "content": content,
            "trigger_turn": trigger_turn,
        },
        separators=(",", ":"),
    )
