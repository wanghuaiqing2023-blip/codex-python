"""Telemetry event payload helpers aligned with ``core/tests/suite/otel.rs``."""

from __future__ import annotations

from typing import Any, Mapping


def extract_log_field(line: str, key: str) -> str | None:
    if not isinstance(line, str) or not isinstance(key, str):
        raise TypeError("line and key must be strings")
    quoted_prefix = f'{key}="'
    start = line.find(quoted_prefix)
    if start >= 0:
        value_start = start + len(quoted_prefix)
        end = line.find('"', value_start)
        if end >= 0:
            return line[value_start:end]
    bare_prefix = f"{key}="
    for token in line.split():
        trimmed = token.rstrip(",")
        if trimmed.startswith(bare_prefix):
            return trimmed[len(bare_prefix) :]
    return None


def api_request_event() -> dict[str, Any]:
    return {"event.name": "codex.api_request"}


def conversation_starts_event() -> dict[str, Any]:
    return {"event.name": "codex.conversation_starts"}


def sse_event(event_kind: str, *, error_message: str | None = None, usage: Mapping[str, Any] | None = None) -> dict[str, Any]:
    event: dict[str, Any] = {"event.name": "codex.sse_event", "event.kind": event_kind}
    if error_message is not None:
        event["error.message"] = error_message
    if usage is not None:
        event.update(completed_usage_fields(usage))
    return event


def failed_sse_event_from_payload(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type", "response.failed"))
    response = event.get("response")
    error_message = None
    if isinstance(response, Mapping):
        error = response.get("error")
        if isinstance(error, Mapping):
            raw_message = error.get("message")
            if isinstance(raw_message, str):
                error_message = raw_message
        elif error is not None:
            error_message = "failed to parse ResponseFailed"
    else:
        error_message = "failed to parse ResponseFailed"
    return sse_event(event_type, error_message=error_message)


def completed_usage_fields(usage: Mapping[str, Any]) -> dict[str, Any]:
    input_details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    if not isinstance(input_details, Mapping):
        input_details = {}
    if not isinstance(output_details, Mapping):
        output_details = {}
    return {
        "input_token_count": usage.get("input_tokens"),
        "output_token_count": usage.get("output_tokens"),
        "cached_token_count": input_details.get("cached_tokens"),
        "reasoning_token_count": output_details.get("reasoning_tokens"),
        "tool_token_count": usage.get("total_tokens"),
    }


def response_completed_event(response: Mapping[str, Any]) -> dict[str, Any]:
    usage = response.get("usage")
    if not isinstance(usage, Mapping):
        return sse_event("response.completed", error_message="failed to parse ResponseCompleted")
    return sse_event("response.completed", usage=usage)


def turn_span_token_usage(usage: Mapping[str, Any]) -> dict[str, Any]:
    return completed_usage_fields(usage)


def responses_span_fields(event: Mapping[str, Any]) -> dict[str, Any]:
    event_type = str(event.get("type", ""))
    fields = {"response.kind": event_type}
    item = event.get("item")
    if isinstance(item, Mapping):
        name = item.get("name")
        if isinstance(name, str):
            fields["tool.name"] = name
    return fields


def response_event_span_fields(event: Mapping[str, Any]) -> dict[str, Any]:
    fields = {"event.kind": str(event.get("type", ""))}
    if "response" in event:
        response = event.get("response")
        if isinstance(response, Mapping) and isinstance(response.get("id"), str):
            fields["response.id"] = response["id"]
    return fields


def tool_result_event(
    *,
    call_id: str,
    tool_name: str,
    arguments: Any,
    output: str,
    success: bool,
    mcp_server: str = "",
    mcp_server_origin: str = "",
) -> dict[str, Any]:
    return {
        "event.name": "codex.tool_result",
        "call_id": call_id,
        "tool_name": tool_name,
        "arguments": arguments,
        "output": output,
        "success": success,
        "mcp_server": mcp_server,
        "mcp_server_origin": mcp_server_origin,
    }


def tool_decision_event(*, call_id: str, tool_name: str, decision: str, source: str) -> dict[str, Any]:
    return {
        "event.name": "codex.tool_decision",
        "call_id": call_id,
        "tool_name": tool_name,
        "decision": decision,
        "source": source,
    }


__all__ = [
    "api_request_event",
    "completed_usage_fields",
    "conversation_starts_event",
    "extract_log_field",
    "failed_sse_event_from_payload",
    "response_completed_event",
    "response_event_span_fields",
    "responses_span_fields",
    "sse_event",
    "tool_decision_event",
    "tool_result_event",
    "turn_span_token_usage",
]
