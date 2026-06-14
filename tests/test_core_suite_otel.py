"""Suite parity tests for ``codex-rs/core/tests/suite/otel.rs``."""

from __future__ import annotations

from pycodex.core.otel_events import (
    api_request_event,
    conversation_starts_event,
    extract_log_field,
    failed_sse_event_from_payload,
    response_completed_event,
    response_event_span_fields,
    responses_span_fields,
    sse_event,
    tool_decision_event,
    tool_result_event,
    turn_span_token_usage,
)


def _usage() -> dict[str, object]:
    return {
        "input_tokens": 3,
        "input_tokens_details": {"cached_tokens": 1},
        "output_tokens": 5,
        "output_tokens_details": {"reasoning_tokens": 2},
        "total_tokens": 9,
    }


def test_extract_log_field_handles_empty_bare_values() -> None:
    line = 'event.name="codex.tool_result" mcp_server= mcp_server_origin='
    assert extract_log_field(line, "mcp_server") == ""
    assert extract_log_field(line, "mcp_server_origin") == ""


def test_extract_log_field_does_not_confuse_similar_keys() -> None:
    line = 'event.name="codex.tool_result" mcp_server_origin=stdio'
    assert extract_log_field(line, "mcp_server") is None
    assert extract_log_field(line, "mcp_server_origin") == "stdio"


def test_responses_api_emits_api_request_event() -> None:
    assert api_request_event()["event.name"] == "codex.api_request"
    assert conversation_starts_event()["event.name"] == "codex.conversation_starts"


def test_process_sse_emits_tracing_for_output_item() -> None:
    event = sse_event("response.output_item.done")
    assert event == {"event.name": "codex.sse_event", "event.kind": "response.output_item.done"}


def test_process_sse_emits_failed_event_on_parse_error() -> None:
    event = sse_event("response.parse_error", error_message="expected ident at line 1 column 2")
    assert event["error.message"] == "expected ident at line 1 column 2"


def test_process_sse_records_failed_event_when_stream_closes_without_completed() -> None:
    event = sse_event("response.stream_closed", error_message="stream closed before response.completed")
    assert event["error.message"] == "stream closed before response.completed"


def test_process_sse_failed_event_records_response_error_message() -> None:
    event = failed_sse_event_from_payload({"type": "response.failed", "response": {"error": {"message": "boom"}}})
    assert event["event.kind"] == "response.failed"
    assert event["error.message"] == "boom"


def test_process_sse_failed_event_logs_parse_error() -> None:
    event = failed_sse_event_from_payload({"type": "response.failed", "response": {"error": "not-an-object"}})
    assert event["event.kind"] == "response.failed"
    assert event["error.message"] == "failed to parse ResponseFailed"


def test_process_sse_failed_event_logs_missing_error() -> None:
    event = failed_sse_event_from_payload({"type": "response.failed", "response": {}})
    assert event["event.kind"] == "response.failed"
    assert "error.message" not in event


def test_process_sse_failed_event_logs_response_completed_parse_error() -> None:
    event = response_completed_event({})
    assert event["event.kind"] == "response.completed"
    assert event["error.message"] == "failed to parse ResponseCompleted"


def test_process_sse_emits_completed_telemetry() -> None:
    event = response_completed_event({"id": "resp1", "usage": _usage()})
    assert event["input_token_count"] == 3
    assert event["output_token_count"] == 5
    assert event["cached_token_count"] == 1
    assert event["reasoning_token_count"] == 2
    assert event["tool_token_count"] == 9


def test_turn_and_completed_response_spans_record_token_usage() -> None:
    assert turn_span_token_usage(_usage()) == {
        "input_token_count": 3,
        "output_token_count": 5,
        "cached_token_count": 1,
        "reasoning_token_count": 2,
        "tool_token_count": 9,
    }


def test_handle_responses_span_records_response_kind_and_tool_name() -> None:
    fields = responses_span_fields({"type": "response.output_item.done", "item": {"name": "shell_command"}})
    assert fields == {"response.kind": "response.output_item.done", "tool.name": "shell_command"}


def test_record_responses_sets_span_fields_for_response_events() -> None:
    fields = response_event_span_fields({"type": "response.completed", "response": {"id": "resp1"}})
    assert fields == {"event.kind": "response.completed", "response.id": "resp1"}


def test_handle_response_item_records_tool_result_for_custom_tool_call() -> None:
    event = tool_result_event(call_id="custom-call", tool_name="custom", arguments="input", output="unsupported call: custom", success=False)
    assert event["event.name"] == "codex.tool_result"
    assert event["tool_name"] == "custom"
    assert event["success"] is False
    assert event["mcp_server"] == ""
    assert event["mcp_server_origin"] == ""


def test_handle_response_item_records_tool_result_for_function_call() -> None:
    event = tool_result_event(call_id="function-call", tool_name="nonexistent", arguments='{"value":1}', output="unsupported call: nonexistent", success=False)
    assert event["call_id"] == "function-call"
    assert event["arguments"] == '{"value":1}'
    assert event["output"] == "unsupported call: nonexistent"


def test_handle_response_item_records_tool_result_for_shell_command_call() -> None:
    event = tool_result_event(call_id="shell-call", tool_name="shell_command", arguments='{"command":"echo shell"}', output="sandbox denied", success=False)
    assert event["tool_name"] == "shell_command"
    assert event["output"]
    assert event["success"] is False


def test_handle_shell_command_autoapprove_from_config_records_tool_decision() -> None:
    assert tool_decision_event(call_id="auto_config_call", tool_name="shell_command", decision="approved", source="config")["source"] == "config"


def test_handle_shell_command_user_approved_records_tool_decision() -> None:
    event = tool_decision_event(call_id="user_approved_call", tool_name="shell_command", decision="approved", source="user")
    assert event["decision"] == "approved"
    assert event["source"] == "user"


def test_handle_shell_command_user_approved_for_session_records_tool_decision() -> None:
    event = tool_decision_event(call_id="user_approved_session_call", tool_name="shell_command", decision="approvedforsession", source="user")
    assert event["decision"] == "approvedforsession"


def test_handle_sandbox_error_user_approves_retry_records_tool_decision() -> None:
    event = tool_decision_event(call_id="sandbox_retry_call", tool_name="shell_command", decision="approved", source="user")
    assert event["call_id"] == "sandbox_retry_call"
    assert event["decision"] == "approved"


def test_handle_shell_command_user_denies_records_tool_decision() -> None:
    event = tool_decision_event(call_id="user_denied_call", tool_name="shell_command", decision="denied", source="user")
    assert event["decision"] == "denied"


def test_handle_sandbox_error_user_approves_for_session_records_tool_decision() -> None:
    event = tool_decision_event(call_id="sandbox_session_call", tool_name="shell_command", decision="approvedforsession", source="user")
    assert event["call_id"] == "sandbox_session_call"
    assert event["decision"] == "approvedforsession"


def test_handle_sandbox_error_user_denies_records_tool_decision() -> None:
    event = tool_decision_event(call_id="sandbox_deny_call", tool_name="shell_command", decision="denied", source="user")
    assert event["call_id"] == "sandbox_deny_call"
    assert event["decision"] == "denied"
