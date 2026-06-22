from pycodex.rollout_trace import (
    CodeCellRuntimeStatus,
    ConversationItemKind,
    ExecutionStatus,
    ProducerRef,
    RawPayloadKind,
    RawTraceEventContext,
    RawTraceEventPayload,
    RawToolCallRequester,
    ThreadTraceContext,
    replay_bundle,
)
from pycodex.code_mode import FunctionCallOutputContentItem, RuntimeResponse
import pytest
from test_rollout_trace_conversation_rs import message
from test_rollout_trace_thread_rs import metadata, read_json, read_jsonl, single_bundle_dir


def reduced_code_cell_id(model_visible_call_id: str) -> str:
    return f"code_cell:{model_visible_call_id}"


def test_code_cell_writer_records_runtime_response_payloads(tmp_path):
    # Rust source: code_cell.rs CodeCellTraceContext::record_initial_response,
    # record_ended, code_cell_status_for_runtime_response, and
    # CodeCellResponseTracePayload. Contract: writer-side code-cell lifecycle
    # events carry the thread/turn context, map RuntimeResponse variants to
    # CodeCellRuntimeStatus, and write ToolResult raw payloads shaped as
    # {"response": <RuntimeResponse>}.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    code_cell = trace.start_code_cell_trace(
        "turn-1",
        "runtime-cell-1",
        "call-code",
        "text('hi')",
    )
    code_cell.record_initial_response(
        RuntimeResponse.yielded(
            cell_id="runtime-cell-1",
            content_items=(FunctionCallOutputContentItem.input_text("running"),),
        )
    )
    code_cell.record_ended(
        RuntimeResponse.result(
            cell_id="runtime-cell-1",
            content_items=(FunctionCallOutputContentItem.input_text("boom"),),
            error_text="boom",
        )
    )

    bundle = single_bundle_dir(tmp_path)
    events = read_jsonl(bundle / "trace.jsonl")[-3:]

    assert [event["thread_id"] for event in events] == ["thread-root"] * 3
    assert [event["codex_turn_id"] for event in events] == ["turn-1"] * 3
    assert events[0]["payload"] == {
        "type": "code_cell_started",
        "runtime_cell_id": "runtime-cell-1",
        "model_visible_call_id": "call-code",
        "source_js": "text('hi')",
    }

    initial_payload = events[1]["payload"]
    assert initial_payload["type"] == "code_cell_initial_response"
    assert initial_payload["runtime_cell_id"] == "runtime-cell-1"
    assert initial_payload["status"] == "yielded"
    assert initial_payload["response_payload"]["kind"] == {"type": "tool_result"}
    assert read_json(bundle / initial_payload["response_payload"]["path"]) == {
        "response": {
            "type": "yielded",
            "cell_id": "runtime-cell-1",
            "content_items": [{"type": "input_text", "text": "running"}],
        }
    }

    ended_payload = events[2]["payload"]
    assert ended_payload["type"] == "code_cell_ended"
    assert ended_payload["runtime_cell_id"] == "runtime-cell-1"
    assert ended_payload["status"] == "failed"
    assert ended_payload["response_payload"]["kind"] == {"type": "tool_result"}
    assert read_json(bundle / ended_payload["response_payload"]["path"]) == {
        "response": {
            "type": "result",
            "cell_id": "runtime-cell-1",
            "content_items": [{"type": "input_text", "text": "boom"}],
            "error_text": "boom",
        }
    }


def test_code_cell_lifecycle_links_nested_tools_waits_and_outputs(tmp_path):
    # Rust test: reducer/code_cell_tests.rs
    # code_cell_lifecycle_links_nested_tools_waits_and_outputs
    # Contract: code-cell lifecycle reduction links the model-visible exec
    # source item, nested code-cell tool calls, later custom-tool output items,
    # wait calls addressed by runtime cell_id, and final cell status.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [message("user", "count files")]})
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellStarted",
            runtime_cell_id="1",
            model_visible_call_id="call-code",
            source_js="text('hi')",
        ),
    )
    first.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-code",
                "input": "text('hi')",
            }
        ],
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellInitialResponse",
            runtime_cell_id="1",
            status=CodeCellRuntimeStatus.YIELDED,
            response_payload=None,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="nested-tool-1",
            model_visible_call_id=None,
            code_mode_runtime_tool_id="tool-1",
            requester=RawToolCallRequester.CodeCell("1"),
            kind="exec_command",
            summary={
                "type": "generic",
                "label": "exec_command",
                "input_preview": "pwd",
                "output_preview": None,
            },
            invocation_payload=None,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="nested-tool-1",
            status=ExecutionStatus.COMPLETED,
            result_payload=None,
        ),
    )

    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "previous_response_id": "resp-1",
            "input": [
                {
                    "type": "custom_tool_call_output",
                    "call_id": "call-code",
                    "output": "Script running with cell ID 1",
                }
            ],
        }
    )
    wait_request = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "wait",
            "tool_namespace": None,
            "payload": {
                "type": "function",
                "arguments": '{"cell_id":"1"}',
            },
        },
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-2"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="wait-tool-1",
            model_visible_call_id="wait-call",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind={"type": "other", "name": "wait"},
            summary={
                "type": "generic",
                "label": "wait",
                "input_preview": '{"cell_id":"1"}',
                "output_preview": None,
            },
            invocation_payload=wait_request,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-2"),
        RawTraceEventPayload.variant(
            "CodeCellEnded",
            runtime_cell_id="1",
            status=CodeCellRuntimeStatus.COMPLETED,
            response_payload=None,
        ),
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    code_cell_id = reduced_code_cell_id("call-code")
    cell = rollout.code_cells[code_cell_id]
    output_item_id = rollout.inference_calls[second.inference_call_id].request_item_ids[-1]

    assert cell.thread_id == "thread-root"
    assert cell.runtime_status == CodeCellRuntimeStatus.COMPLETED
    assert cell.execution.status == ExecutionStatus.COMPLETED
    assert cell.runtime_cell_id == "1"
    assert cell.nested_tool_call_ids == ["nested-tool-1"]
    assert cell.wait_tool_call_ids == ["wait-tool-1"]
    assert cell.output_item_ids == [output_item_id]
    assert rollout.conversation_items[output_item_id].produced_by == [
        ProducerRef.CodeCell(code_cell_id)
    ]
    assert rollout.conversation_items[cell.source_item_id].kind == ConversationItemKind.CUSTOM_TOOL_CALL


def test_fast_code_cell_lifecycle_waits_for_source_item(tmp_path):
    # Rust test: reducer/code_cell_tests.rs
    # fast_code_cell_lifecycle_waits_for_source_item
    # Contract: CodeCellStarted/InitialResponse/Ended may arrive before the
    # custom_tool_call source item; reducer queues lifecycle events and replays
    # them after inference completion materializes the source conversation item.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "count files")]})
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellStarted",
            runtime_cell_id="1",
            model_visible_call_id="call-code",
            source_js="not valid js",
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellInitialResponse",
            runtime_cell_id="1",
            status=CodeCellRuntimeStatus.FAILED,
            response_payload=None,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellEnded",
            runtime_cell_id="1",
            status=CodeCellRuntimeStatus.FAILED,
            response_payload=None,
        ),
    )
    attempt.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-code",
                "input": "not valid js",
            }
        ],
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    cell = rollout.code_cells[reduced_code_cell_id("call-code")]

    assert cell.thread_id == "thread-root"
    assert cell.runtime_status == CodeCellRuntimeStatus.FAILED
    assert cell.execution.status == ExecutionStatus.FAILED
    assert cell.runtime_cell_id == "1"
    assert rollout.conversation_items[cell.source_item_id].kind == ConversationItemKind.CUSTOM_TOOL_CALL


def test_cancelled_turn_terminates_unfinished_code_cell(tmp_path):
    # Rust test: reducer/code_cell_tests.rs
    # cancelled_turn_terminates_unfinished_code_cell
    # Contract: cancelled/failed/aborted owning turns close still-running code
    # cells; normal completed turns do not imply code-cell completion.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "count files")]})
    attempt.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-code",
                "input": "await tools.exec_command({cmd: 'slow'});",
            }
        ],
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellStarted",
            runtime_cell_id="1",
            model_visible_call_id="call-code",
            source_js="await tools.exec_command({cmd: 'slow'});",
        ),
    )
    turn_end = trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodexTurnEnded",
            codex_turn_id="turn-1",
            status=ExecutionStatus.CANCELLED,
        ),
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    cell = rollout.code_cells[reduced_code_cell_id("call-code")]

    assert cell.runtime_status == CodeCellRuntimeStatus.TERMINATED
    assert cell.execution.status == ExecutionStatus.CANCELLED
    assert cell.execution.ended_seq == turn_end.seq


def test_runtime_code_cell_ids_can_repeat_across_threads(tmp_path):
    # Rust test: reducer/code_cell_tests.rs
    # runtime_code_cell_ids_can_repeat_across_threads
    # Contract: runtime cell ids are thread-local handles; the reduced
    # code_cell id is based on model-visible call id, so the same runtime id
    # can appear independently in different threads.
    root = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    child = root.start_child_thread_trace_or_disabled(metadata("thread-child"))

    cases = [
        (root, "thread-root", "turn-root", "call-root"),
        (child, "thread-child", "turn-child", "call-child"),
    ]
    for trace, thread_id, turn_id, call_id in cases:
        trace.record_codex_turn_started(turn_id)
        attempt = trace.inference_trace_context(turn_id, "gpt-test", "test-provider").start_attempt()
        attempt.record_started({"input": [message("user", "run code")]})
        trace.writer.append_with_context(
            RawTraceEventContext(thread_id, turn_id),
            RawTraceEventPayload.variant(
                "CodeCellStarted",
                runtime_cell_id="1",
                model_visible_call_id=call_id,
                source_js="text('hi')",
            ),
        )
        attempt.record_completed(
            f"resp-{thread_id}",
            "req-1",
            None,
            [
                {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": call_id,
                    "input": "text('hi')",
                }
            ],
        )
        trace.writer.append_with_context(
            RawTraceEventContext(thread_id, turn_id),
            RawTraceEventPayload.variant(
                "CodeCellEnded",
                runtime_cell_id="1",
                status=CodeCellRuntimeStatus.COMPLETED,
                response_payload=None,
            ),
        )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    root_cell = rollout.code_cells[reduced_code_cell_id("call-root")]
    child_cell = rollout.code_cells[reduced_code_cell_id("call-child")]

    assert root_cell.thread_id == "thread-root"
    assert child_cell.thread_id == "thread-child"
    assert root_cell.runtime_cell_id == "1"
    assert child_cell.runtime_cell_id == "1"


def test_runtime_code_cell_id_conflict_is_reducer_error_within_thread(tmp_path):
    # Rust source: reducer/code_cell.rs record_runtime_code_cell_id and
    # runtime_code_cell_key. Contract: runtime cell ids are thread-local
    # handles; the same runtime id may repeat across threads, but within one
    # thread it cannot map to two durable model-visible code-cell ids.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))

    for turn_id, call_id in (("turn-1", "call-one"), ("turn-2", "call-two")):
        trace.record_codex_turn_started(turn_id)
        attempt = trace.inference_trace_context(turn_id, "gpt-test", "test-provider").start_attempt()
        attempt.record_started({"input": [message("user", "run code")]})
        attempt.record_completed(
            f"resp-{turn_id}",
            "req-1",
            None,
            [
                {
                    "type": "custom_tool_call",
                    "name": "exec",
                    "call_id": call_id,
                    "input": "text('hi')",
                }
            ],
        )
        trace.writer.append_with_context(
            RawTraceEventContext("thread-root", turn_id),
            RawTraceEventPayload.variant(
                "CodeCellStarted",
                runtime_cell_id="1",
                model_visible_call_id=call_id,
                source_js="text('hi')",
            ),
        )

    with pytest.raises(
        ValueError,
        match=(
            "runtime code cell 1 in thread thread-root mapped to both "
            "code_cell:call-one and code_cell:call-two"
        ),
    ):
        replay_bundle(single_bundle_dir(tmp_path))
