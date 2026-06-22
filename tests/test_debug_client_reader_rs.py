"""Prepared parity tests for Rust ``codex-debug-client/src/reader.rs``.

Pytest is deferred until the full ``codex-debug-client`` crate is functionally
complete, per the crate-level porting workflow.
"""

from __future__ import annotations

import io
import json

from pycodex.debug_client.output import Output
from pycodex.debug_client.reader import (
    COMMAND_APPROVAL_METHOD,
    FILE_CHANGE_APPROVAL_METHOD,
    ITEM_COMPLETED_METHOD,
    emit_filtered_item,
    handle_filtered_notification,
    handle_response,
    handle_server_request,
    process_server_line,
    send_response,
    write_multiline,
)
from pycodex.debug_client.state import PendingRequest, ReaderEvent, State


def make_output() -> tuple[Output, io.StringIO, io.StringIO]:
    stdout = io.StringIO()
    stderr = io.StringIO()
    return Output.new(None, stdout=stdout, stderr=stderr, color=False), stdout, stderr


def test_send_response_writes_jsonrpc_response_line() -> None:
    # Rust source: send_response serializes JSONRPCResponse { id, result } plus newline.
    stdin = io.StringIO()

    send_response(stdin, "req-1", {"decision": "accept"})

    assert stdin.getvalue() == '{"id":"req-1","result":{"decision":"accept"}}\n'


def test_handle_server_request_auto_responds_to_command_approval() -> None:
    # Rust source: CommandExecutionRequestApproval sends decision wrapper and logs client line.
    output, _stdout, stderr = make_output()
    stdin = io.StringIO()

    handle_server_request(
        {"method": COMMAND_APPROVAL_METHOD, "id": "req-1", "params": {"command": "echo hi"}},
        "accept",
        "decline",
        stdin,
        output,
    )

    assert json.loads(stdin.getvalue()) == {
        "id": "req-1",
        "result": {"decision": {"type": "accept"}},
    }
    assert "auto-response for command approval 'req-1': Accept" in stderr.getvalue()


def test_handle_server_request_auto_responds_to_file_change_approval() -> None:
    # Rust source: FileChangeRequestApproval sends plain file decision and logs client line.
    output, _stdout, stderr = make_output()
    stdin = io.StringIO()

    handle_server_request(
        {"method": FILE_CHANGE_APPROVAL_METHOD, "id": "req-2", "params": {"path": "a.txt"}},
        "decline",
        "accept",
        stdin,
        output,
    )

    assert json.loads(stdin.getvalue()) == {"id": "req-2", "result": {"decision": "accept"}}
    assert "auto-response for file change approval 'req-2': Accept" in stderr.getvalue()


def test_handle_response_start_resume_and_list_update_state_and_events() -> None:
    # Rust source: handle_response removes pending ids and emits ReaderEvent variants.
    state = State(
        pending={
            "1": PendingRequest.START,
            "2": PendingRequest.RESUME,
            "3": PendingRequest.LIST,
        }
    )
    events: list[ReaderEvent] = []

    handle_response({"id": "1", "result": {"thread": {"id": "thr-1"}}}, state, events)
    handle_response({"id": "2", "result": {"thread": {"id": "thr-2"}}}, state, events)
    handle_response(
        {
            "id": "3",
            "result": {
                "data": [{"id": "thr-1"}, {"id": "thr-3"}],
                "nextCursor": "cursor",
            },
        },
        state,
        events,
    )

    assert state.pending == {}
    assert state.thread_id == "thr-2"
    assert state.known_threads == ["thr-1", "thr-2", "thr-3"]
    assert events == [
        ReaderEvent.thread_ready("thr-1"),
        ReaderEvent.thread_ready("thr-2"),
        ReaderEvent.thread_list(["thr-1", "thr-3"], "cursor"),
    ]


def test_handle_response_unknown_pending_id_is_ignored() -> None:
    # Rust source: responses without matching pending requests are no-ops.
    state = State()
    events: list[ReaderEvent] = []

    handle_response({"id": "missing", "result": {"thread": {"id": "thr"}}}, state, events)

    assert state == State()
    assert events == []


def test_handle_filtered_notification_emits_item_completed_agent_message() -> None:
    # Rust source: filtered ItemCompleted notifications render selected ThreadItem variants.
    output, stdout, _stderr = make_output()

    handle_filtered_notification(
        {
            "method": ITEM_COMPLETED_METHOD,
            "params": {
                "threadId": "thr-1",
                "item": {"type": "AgentMessage", "text": "hello"},
            },
        },
        output,
    )

    assert stdout.getvalue() == "thr-1 assistant: hello\n"


def test_emit_filtered_item_renders_plan_and_multiline_text() -> None:
    # Rust source: Plan emits a summary line and write_multiline details.
    output, stdout, _stderr = make_output()

    emit_filtered_item({"type": "Plan", "text": "one\ntwo"}, "thr-1", output)

    assert stdout.getvalue() == (
        "thr-1 assistant: plan\n"
        "thr-1 assistant:\n"
        "thr-1   one\n"
        "thr-1   two\n"
    )


def test_emit_filtered_item_renders_tool_item_variants() -> None:
    # Rust source: CommandExecution, FileChange, and McpToolCall have compact filtered lines.
    output, stdout, _stderr = make_output()

    emit_filtered_item(
        {
            "type": "CommandExecution",
            "command": "pwd",
            "status": "completed",
            "exitCode": 0,
            "aggregatedOutput": "out",
        },
        "thr-1",
        output,
    )
    emit_filtered_item({"type": "FileChange", "status": "completed", "changes": {"a.txt": {}}}, "thr-1", output)
    emit_filtered_item(
        {
            "type": "McpToolCall",
            "server": "srv",
            "tool": "lookup",
            "status": "failed",
            "arguments": {"q": "x"},
            "result": {"ok": True},
            "error": "bad",
        },
        "thr-1",
        output,
    )

    assert stdout.getvalue() == (
        "thr-1 tool: command pwd (completed)\n"
        "thr-1 tool exit: 0\n"
        "thr-1 tool output:\n"
        "thr-1   out\n"
        "thr-1 tool: file change (completed, 1 files)\n"
        "thr-1 tool: srv.lookup (failed)\n"
        'thr-1 tool args: {"q":"x"}\n'
        "thr-1 tool result: {'ok': True}\n"
        "thr-1 tool error: 'bad'\n"
    )


def test_write_multiline_matches_reader_helper_format() -> None:
    # Rust source: write_multiline emits header then indented text lines.
    output, stdout, _stderr = make_output()

    write_multiline(output, "thr-1", "tool output:", "a\nb")

    assert stdout.getvalue() == "thr-1 tool output:\nthr-1   a\nthr-1   b\n"


def test_process_server_line_logs_raw_line_and_dispatches_response() -> None:
    # Rust source: start_reader logs non-empty raw server JSON before dispatching.
    output, stdout, _stderr = make_output()
    state = State(pending={"1": PendingRequest.START})
    events: list[ReaderEvent] = []

    process_server_line(
        '{"id":"1","result":{"thread":{"id":"thr-1"}}}',
        io.StringIO(),
        state,
        events,
        output,
        filtered_output=False,
    )
    process_server_line("not json", io.StringIO(), state, events, output)

    assert stdout.getvalue().splitlines() == [
        '{"id":"1","result":{"thread":{"id":"thr-1"}}}',
        "not json",
    ]
    assert state.thread_id == "thr-1"
    assert events == [ReaderEvent.thread_ready("thr-1")]
