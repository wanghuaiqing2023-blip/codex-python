from pycodex import rollout_trace as rt
from pycodex.rollout_trace import (
    ExecutionStatus,
    RawPayloadKind,
    RawToolCallRequester,
    RawTraceEventContext,
    RawTraceEventPayload,
    TerminalObservationSource,
    TerminalOperationKind,
    TerminalRequest,
    TerminalResult,
    ThreadTraceContext,
    replay_bundle,
)
from test_rollout_trace_conversation_rs import message
from test_rollout_trace_thread_rs import metadata, single_bundle_dir


def _generic_summary(label: str) -> dict:
    return {
        "type": "generic",
        "label": label,
        "input_preview": None,
        "output_preview": None,
    }


def test_exec_tool_reduces_to_terminal_operation_and_session(tmp_path):
    # Rust test: reducer/tool/terminal_tests.rs
    # exec_tool_reduces_to_terminal_operation_and_session
    # Contract: protocol runtime begin/end payloads create a terminal
    # operation/session while preserving canonical tool invocation/result
    # payload ids and model-visible observation links.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    first = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    first.record_started({"input": [message("user", "run tests")]})
    first.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "function_call",
                "name": "exec_command",
                "arguments": '{"cmd":"cargo test"}',
                "call_id": "call-1",
            }
        ],
    )
    invocation_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "exec_command",
            "tool_namespace": None,
            "payload": {"type": "function", "arguments": '{"cmd":"cargo test"}'},
        },
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-1",
            model_visible_call_id="call-1",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind="exec_command",
            summary=_generic_summary("exec_command"),
            invocation_payload=invocation_payload,
        ),
    )
    runtime_start_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "tool-1",
            "turn_id": "turn-1",
            "command": ["cargo", "test"],
            "cwd": "/repo",
        },
    )
    runtime_start = trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallRuntimeStarted",
            tool_call_id="tool-1",
            runtime_payload=runtime_start_payload,
        ),
    )
    runtime_end_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "call_id": "tool-1",
            "process_id": "pty-1",
            "turn_id": "turn-1",
            "command": ["cargo", "test"],
            "cwd": "/repo",
            "stdout": "ok\n",
            "stderr": "",
            "exit_code": 0,
            "formatted_output": "ok\n",
            "status": "completed",
        },
    )
    runtime_end = trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallRuntimeEnded",
            tool_call_id="tool-1",
            status=ExecutionStatus.COMPLETED,
            runtime_payload=runtime_end_payload,
        ),
    )
    result_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {
            "type": "direct_response",
            "response_item": {
                "type": "function_call_output",
                "call_id": "call-1",
                "output": "ok\n",
            },
        },
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="tool-1",
            status=ExecutionStatus.COMPLETED,
            result_payload=result_payload,
        ),
    )
    trace.record_codex_turn_started("turn-2")
    second = trace.inference_trace_context("turn-2", "gpt-test", "test-provider").start_attempt()
    second.record_started(
        {
            "previous_response_id": "resp-1",
            "input": [
                {
                    "type": "function_call_output",
                    "call_id": "call-1",
                    "output": "ok\n",
                }
            ],
        }
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    operation = rollout.terminal_operations["terminal_operation:1"]
    output_item_id = rollout.inference_calls[second.inference_call_id].request_item_ids[-1]

    assert rollout.tool_calls["tool-1"].terminal_operation_id == "terminal_operation:1"
    assert rt._jsonable(rollout.tool_calls["tool-1"].summary) == {
        "type": "terminal",
        "operation_id": "terminal_operation:1",
    }
    assert rollout.tool_calls["tool-1"].raw_invocation_payload_id == invocation_payload.raw_payload_id
    assert rollout.tool_calls["tool-1"].raw_result_payload_id == result_payload.raw_payload_id
    assert rollout.tool_calls["tool-1"].raw_runtime_payload_ids == [
        runtime_start_payload.raw_payload_id,
        runtime_end_payload.raw_payload_id,
    ]
    assert operation.terminal_id == "pty-1"
    assert operation.kind == TerminalOperationKind.EXEC_COMMAND
    assert operation.execution.started_seq == runtime_start.seq
    assert operation.execution.ended_seq == runtime_end.seq
    assert operation.request == TerminalRequest.ExecCommand(
        command=["cargo", "test"],
        display_command="cargo test",
        cwd="/repo",
    )
    assert operation.result == TerminalResult(0, "ok\n", "", "ok\n")
    assert operation.model_observations[0].call_item_ids == rollout.inference_calls[first.inference_call_id].response_item_ids
    assert operation.model_observations[0].output_item_ids == [output_item_id]
    assert operation.model_observations[0].source == TerminalObservationSource.DIRECT_TOOL_CALL
    assert rollout.terminal_sessions["pty-1"].operation_ids == ["terminal_operation:1"]


def test_write_stdin_operation_reuses_existing_terminal_session(tmp_path):
    # Rust test: reducer/tool/terminal_tests.rs
    # write_stdin_operation_reuses_existing_terminal_session
    # Contract: runtime write_stdin begin joins the existing terminal session
    # and appends the new operation id instead of creating a second session.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    startup_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {"process_id": "pty-1", "command": ["bash"], "cwd": "/repo"},
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-start",
            model_visible_call_id=None,
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind="exec_command",
            summary=_generic_summary("exec_command"),
            invocation_payload=None,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallRuntimeStarted",
            tool_call_id="tool-start",
            runtime_payload=startup_payload,
        ),
    )
    stdin_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RUNTIME_EVENT,
        {
            "process_id": "pty-1",
            "command": ["bash"],
            "cwd": "/repo",
            "interaction_input": "echo hi\n",
        },
    )
    stdin_start = trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-stdin",
            model_visible_call_id=None,
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind="write_stdin",
            summary=_generic_summary("write_stdin"),
            invocation_payload=None,
        ),
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallRuntimeStarted",
            tool_call_id="tool-stdin",
            runtime_payload=stdin_payload,
        ),
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    operation = rollout.terminal_operations["terminal_operation:2"]

    assert rollout.terminal_sessions["pty-1"].operation_ids == [
        "terminal_operation:1",
        "terminal_operation:2",
    ]
    assert operation.terminal_id == "pty-1"
    assert operation.kind == TerminalOperationKind.WRITE_STDIN
    assert operation.execution.started_seq == stdin_start.seq + 1
    assert operation.request == TerminalRequest.WriteStdin(stdin="echo hi\n")
    assert operation.result is None


def test_dispatch_write_stdin_payload_reduces_to_terminal_operation(tmp_path):
    # Rust test: reducer/tool/terminal_tests.rs
    # dispatch_write_stdin_payload_reduces_to_terminal_operation
    # Contract: direct write_stdin without protocol runtime events creates a
    # terminal operation from dispatch invocation/result payloads.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    request_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "write_stdin",
            "tool_namespace": None,
            "payload": {
                "type": "function",
                "arguments": '{"session_id":123,"chars":"echo hi\\n","yield_time_ms":250,"max_output_tokens":2000}',
            },
        },
    )
    tool_start = trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-stdin",
            model_visible_call_id="call-stdin",
            code_mode_runtime_tool_id=None,
            requester=RawToolCallRequester.Model(),
            kind="write_stdin",
            summary=_generic_summary("write_stdin"),
            invocation_payload=request_payload,
        ),
    )
    response_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {
            "type": "direct_response",
            "response_item": {
                "type": "function_call_output",
                "call_id": "call-stdin",
                "output": "hi\n",
            },
        },
    )
    tool_end = trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="tool-stdin",
            status=ExecutionStatus.COMPLETED,
            result_payload=response_payload,
        ),
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))
    operation = rollout.terminal_operations["terminal_operation:1"]

    assert rollout.tool_calls["tool-stdin"].terminal_operation_id == "terminal_operation:1"
    assert operation.terminal_id == "123"
    assert operation.execution.started_seq == tool_start.seq
    assert operation.execution.ended_seq == tool_end.seq
    assert operation.request == TerminalRequest.WriteStdin(
        stdin="echo hi\n",
        yield_time_ms=250,
        max_output_tokens=2000,
    )
    assert operation.result == TerminalResult(None, "hi\n", "", "hi\n")
    assert operation.raw_payload_ids == [
        request_payload.raw_payload_id,
        response_payload.raw_payload_id,
    ]
    assert rollout.terminal_sessions["123"].operation_ids == ["terminal_operation:1"]


def test_code_mode_write_stdin_result_projects_structured_exec_fields(tmp_path):
    # Rust test: reducer/tool/terminal_tests.rs
    # code_mode_write_stdin_result_projects_structured_exec_fields
    # Contract: code-mode write_stdin result payload keeps structured unified
    # exec fields in the terminal result projection.
    trace = ThreadTraceContext.start_root_in_root_for_test(tmp_path, metadata("thread-root"))
    trace.record_codex_turn_started("turn-1")
    attempt = trace.inference_trace_context("turn-1", "gpt-test", "test-provider").start_attempt()
    attempt.record_started({"input": [message("user", "run code")]})
    attempt.record_completed(
        "resp-1",
        "req-1",
        None,
        [
            {
                "type": "custom_tool_call",
                "name": "exec",
                "call_id": "call-code",
                "input": "await tools.write_stdin({ chars: '' })",
            }
        ],
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "CodeCellStarted",
            runtime_cell_id="cell-1",
            model_visible_call_id="call-code",
            source_js="await tools.write_stdin({ chars: '' })",
        ),
    )
    request_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_INVOCATION,
        {
            "tool_name": "write_stdin",
            "tool_namespace": None,
            "payload": {
                "type": "function",
                "arguments": '{"session_id":456,"chars":"","yield_time_ms":1000,"max_output_tokens":4000}',
            },
        },
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallStarted",
            tool_call_id="tool-stdin",
            model_visible_call_id=None,
            code_mode_runtime_tool_id="runtime-tool-1",
            requester=RawToolCallRequester.CodeCell("cell-1"),
            kind="write_stdin",
            summary=_generic_summary("write_stdin"),
            invocation_payload=request_payload,
        ),
    )
    response_payload = trace.writer.write_json_payload(
        RawPayloadKind.TOOL_RESULT,
        {
            "type": "code_mode_response",
            "value": {
                "chunk_id": "abc123",
                "wall_time_seconds": 1.25,
                "exit_code": 0,
                "original_token_count": 3,
                "output": "done\n",
            },
        },
    )
    trace.writer.append_with_context(
        RawTraceEventContext("thread-root", "turn-1"),
        RawTraceEventPayload.variant(
            "ToolCallEnded",
            tool_call_id="tool-stdin",
            status=ExecutionStatus.COMPLETED,
            result_payload=response_payload,
        ),
    )

    rollout = replay_bundle(single_bundle_dir(tmp_path))

    assert rollout.terminal_operations["terminal_operation:1"].result == TerminalResult(
        0,
        "done\n",
        "",
        "done\n",
        original_token_count=3,
        chunk_id="abc123",
    )
