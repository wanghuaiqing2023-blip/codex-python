"""Responses SSE event helpers for the Rust ``codex-api`` port.

Rust source:
- ``codex/codex-rs/codex-api/src/sse/responses.rs``
"""

from __future__ import annotations

import re
import json
from dataclasses import dataclass
from collections.abc import Iterable
from collections.abc import Iterator
from typing import Any

from ..common import ResponseEvent
from ..common import ResponseStream
from ..error import ApiError
from ..rate_limits import parse_all_rate_limits
from pycodex.codex_client import IdleTimeout
from pycodex.codex_client import StreamResponse
from pycodex.codex_client import TransportError


TRUSTED_ACCESS_FOR_CYBER_VERIFICATION = "trusted_access_for_cyber"
CYBER_POLICY_FALLBACK_MESSAGE = (
    "This request has been flagged for possible cybersecurity risk."
)
X_REASONING_INCLUDED_HEADER = "x-reasoning-included"
OPENAI_MODEL_HEADER = "openai-model"
REQUEST_ID_HEADER = "x-request-id"


@dataclass(frozen=True)
class ResponsesStreamEvent:
    kind: str
    headers: Any = None
    metadata: Any = None
    response: Any = None
    item: Any = None
    item_id: str | None = None
    call_id: str | None = None
    delta: str | None = None
    summary_index: int | None = None
    content_index: int | None = None

    @classmethod
    def from_json_dict(cls, value: dict[str, Any]) -> "ResponsesStreamEvent":
        return cls(
            kind=str(value.get("type", "")),
            headers=value.get("headers"),
            metadata=value.get("metadata"),
            response=value.get("response"),
            item=value.get("item"),
            item_id=value.get("item_id"),
            call_id=value.get("call_id"),
            delta=value.get("delta"),
            summary_index=value.get("summary_index"),
            content_index=value.get("content_index"),
        )

    def response_model(self) -> str | None:
        response_headers = (
            self.response.get("headers")
            if isinstance(self.response, dict)
            else None
        )
        model = _header_openai_model_value_from_json(response_headers)
        if model is not None:
            return model
        return _header_openai_model_value_from_json(self.headers)

    def model_verifications(self) -> list[str] | None:
        if self.kind != "response.metadata":
            return None
        if not isinstance(self.metadata, dict):
            return None
        return _model_verifications_from_json_value(
            self.metadata.get("openai_verification_recommendation")
        )


@dataclass(frozen=True)
class ResponsesEventError(Exception):
    error: ApiError

    @classmethod
    def api(cls, error: ApiError) -> "ResponsesEventError":
        return cls(error)

    def into_api_error(self) -> ApiError:
        return self.error

    def __str__(self) -> str:
        return str(self.error)


def process_responses_event(event: ResponsesStreamEvent) -> ResponseEvent | None:
    kind = event.kind
    if kind == "response.output_item.done":
        if event.item is not None:
            return ResponseEvent("output_item_done", event.item)
    if kind == "response.output_text.delta":
        if event.delta is not None:
            return ResponseEvent("output_text_delta", event.delta)
    if kind == "response.custom_tool_call_input.delta":
        item_id = event.item_id or event.call_id
        if event.delta is not None and item_id is not None:
            return ResponseEvent(
                "tool_call_input_delta",
                {"item_id": item_id, "call_id": event.call_id, "delta": event.delta},
            )
    if kind == "response.reasoning_summary_text.delta":
        if event.delta is not None and event.summary_index is not None:
            return ResponseEvent(
                "reasoning_summary_delta",
                {"delta": event.delta, "summary_index": event.summary_index},
            )
    if kind == "response.reasoning_text.delta":
        if event.delta is not None and event.content_index is not None:
            return ResponseEvent(
                "reasoning_content_delta",
                {"delta": event.delta, "content_index": event.content_index},
            )
    if kind == "response.created":
        if event.response is not None:
            return ResponseEvent("created")
    if kind == "response.failed":
        raise ResponsesEventError.api(_api_error_from_failed_response(event.response))
    if kind == "response.incomplete":
        reason = "unknown"
        if isinstance(event.response, dict):
            details = event.response.get("incomplete_details")
            if isinstance(details, dict) and isinstance(details.get("reason"), str):
                reason = details["reason"]
        raise ResponsesEventError.api(
            ApiError.stream(f"Incomplete response returned, reason: {reason}")
        )
    if kind == "response.completed":
        if isinstance(event.response, dict):
            try:
                return _completed_event_from_response(event.response)
            except (KeyError, TypeError, ValueError) as exc:
                raise ResponsesEventError.api(
                    ApiError.stream(f"failed to parse ResponseCompleted: {exc}")
                ) from exc
    if kind == "response.output_item.added":
        if event.item is not None:
            return ResponseEvent("output_item_added", event.item)
    if kind == "response.reasoning_summary_part.added":
        if event.summary_index is not None:
            return ResponseEvent(
                "reasoning_summary_part_added",
                {"summary_index": event.summary_index},
            )
    return None


def spawn_response_stream(
    stream_response: StreamResponse,
    idle_timeout: float | None,
    telemetry: Any | None = None,
    turn_state: Any | None = None,
) -> ResponseStream:
    """Project Rust ``spawn_response_stream`` into a synchronous stream facade."""

    headers = _casefold_headers(stream_response.headers)
    turn_state_header = headers.get("x-codex-turn-state")
    if turn_state is not None and turn_state_header is not None:
        _set_turn_state(turn_state, turn_state_header)

    events = _spawn_response_events(
        stream_response.bytes,
        headers,
        idle_timeout,
        telemetry,
    )
    return ResponseStream.from_iterable(
        events,
        upstream_request_id=headers.get(REQUEST_ID_HEADER),
    )


def process_sse(
    stream: Iterable[bytes | str | TransportError | BaseException | IdleTimeout],
    idle_timeout: float | None = None,
    telemetry: Any | None = None,
) -> Iterator[ResponseEvent | ApiError]:
    """Parse Responses SSE chunks using Rust ``process_sse`` terminal semantics."""

    del idle_timeout
    parser = _SseDataParser()
    response_error: ApiError | None = None
    last_server_model: str | None = None
    completed = False

    for item in stream:
        if isinstance(item, IdleTimeout):
            yield ApiError.stream("idle timeout waiting for SSE")
            return
        if isinstance(item, TransportError):
            yield ApiError.stream(str(item))
            return
        if isinstance(item, BaseException):
            yield ApiError.stream(str(item))
            return

        chunk = item.encode() if isinstance(item, str) else bytes(item)
        try:
            payloads = list(parser.feed(chunk))
        except UnicodeDecodeError as exc:
            yield ApiError.stream(str(exc))
            return

        for data in payloads:
            event = _event_from_sse_data(data)
            if event is None:
                continue
            model = event.response_model()
            if model is not None and model != last_server_model:
                yield ResponseEvent("server_model", model)
                last_server_model = model

            verifications = event.model_verifications()
            if verifications is not None:
                yield ResponseEvent("model_verifications", verifications)

            try:
                mapped = process_responses_event(event)
            except ResponsesEventError as exc:
                response_error = exc.into_api_error()
                continue
            if mapped is None:
                continue
            yield mapped
            if mapped.kind == "completed":
                completed = True
                return

    try:
        payloads = list(parser.finish())
    except UnicodeDecodeError as exc:
        yield ApiError.stream(str(exc))
        return
    for data in payloads:
        event = _event_from_sse_data(data)
        if event is None:
            continue
        try:
            mapped = process_responses_event(event)
        except ResponsesEventError as exc:
            response_error = exc.into_api_error()
            continue
        if mapped is not None:
            yield mapped
            if mapped.kind == "completed":
                completed = True
                return

    if not completed:
        yield response_error or ApiError.stream("stream closed before response.completed")


def try_parse_retry_after(error: dict[str, Any]) -> float | None:
    if error.get("code") != "rate_limit_exceeded":
        return None
    message = error.get("message")
    if not isinstance(message, str):
        return None
    match = re.search(
        r"(?i)try again in\s*(\d+(?:\.\d+)?)\s*(s|ms|seconds?)",
        message,
    )
    if not match:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "ms":
        return value / 1000
    return value


def _api_error_from_failed_response(response: Any) -> ApiError:
    if not isinstance(response, dict):
        return ApiError.stream("response.failed event received")
    error = response.get("error")
    if not isinstance(error, dict):
        return ApiError.stream("response.failed event received")

    code = error.get("code")
    message = error.get("message")
    if code == "context_length_exceeded":
        return ApiError.context_window_exceeded()
    if code == "insufficient_quota":
        return ApiError.quota_exceeded()
    if code == "usage_not_included":
        return ApiError.usage_not_included()
    if code == "cyber_policy":
        return ApiError.cyber_policy(_cyber_policy_message(message))
    if code == "invalid_prompt":
        return ApiError.invalid_request(
            message if isinstance(message, str) else "Invalid request."
        )
    if code in {"server_is_overloaded", "slow_down"}:
        return ApiError.server_overloaded()
    return ApiError.retryable(
        message if isinstance(message, str) else "",
        delay=try_parse_retry_after(error),
    )


def _completed_event_from_response(response: dict[str, Any]) -> ResponseEvent:
    response_id = response.get("id")
    if not isinstance(response_id, str):
        raise KeyError("id")
    usage = response.get("usage")
    return ResponseEvent(
        "completed",
        {
            "response_id": response_id,
            "token_usage": _token_usage_from_response_usage(usage),
            "end_turn": response.get("end_turn"),
        },
    )


def _token_usage_from_response_usage(usage: Any) -> dict[str, int] | None:
    if not isinstance(usage, dict):
        return None
    input_details = usage.get("input_tokens_details")
    output_details = usage.get("output_tokens_details")
    return {
        "input_tokens": int(usage.get("input_tokens", 0)),
        "cached_input_tokens": int(
            input_details.get("cached_tokens", 0)
            if isinstance(input_details, dict)
            else 0
        ),
        "output_tokens": int(usage.get("output_tokens", 0)),
        "reasoning_output_tokens": int(
            output_details.get("reasoning_tokens", 0)
            if isinstance(output_details, dict)
            else 0
        ),
        "total_tokens": int(usage.get("total_tokens", 0)),
    }


def _header_openai_model_value_from_json(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for name, item in value.items():
        if str(name).lower() in {"openai-model", "x-openai-model"}:
            return _json_value_as_string(item)
    return None


def _model_verifications_from_json_value(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    output: list[str] = []
    for item in value:
        if item == TRUSTED_ACCESS_FOR_CYBER_VERIFICATION and item not in output:
            output.append(item)
    return output or None


def _json_value_as_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _json_value_as_string(value[0])
    return None


def _cyber_policy_message(message: Any) -> str:
    if isinstance(message, str) and message.strip():
        return message
    return CYBER_POLICY_FALLBACK_MESSAGE


def _spawn_response_events(
    stream: Iterable[bytes | str | TransportError | BaseException | IdleTimeout],
    headers: dict[str, str],
    idle_timeout: float | None,
    telemetry: Any | None,
) -> Iterator[ResponseEvent | ApiError]:
    server_model = headers.get(OPENAI_MODEL_HEADER)
    if server_model is not None:
        yield ResponseEvent("server_model", server_model)
    for snapshot in parse_all_rate_limits(headers):
        yield ResponseEvent("rate_limits", snapshot)
    models_etag = headers.get("x-models-etag")
    if models_etag is not None:
        yield ResponseEvent("models_etag", models_etag)
    if X_REASONING_INCLUDED_HEADER in headers:
        yield ResponseEvent("server_reasoning_included", True)
    yield from process_sse(stream, idle_timeout, telemetry)


def _event_from_sse_data(data: str) -> ResponsesStreamEvent | None:
    try:
        value = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(value, dict):
        return None
    return ResponsesStreamEvent.from_json_dict(value)


class _SseDataParser:
    def __init__(self) -> None:
        self._buffer = b""
        self._data_lines: list[str] = []

    def feed(self, chunk: bytes) -> Iterator[str]:
        self._buffer += chunk
        while True:
            line, sep, rest = self._next_line(self._buffer)
            if sep is None:
                return
            self._buffer = rest
            yielded = self._handle_line(line.decode("utf-8"))
            if yielded is not None:
                yield yielded

    def finish(self) -> Iterator[str]:
        if self._buffer:
            yielded = self._handle_line(self._buffer.decode("utf-8"))
            self._buffer = b""
            if yielded is not None:
                yield yielded
        if self._data_lines:
            data = "\n".join(self._data_lines)
            self._data_lines = []
            yield data

    @staticmethod
    def _next_line(buffer: bytes) -> tuple[bytes, bytes | None, bytes]:
        positions = [
            pos for pos in (buffer.find(b"\n"), buffer.find(b"\r")) if pos != -1
        ]
        if not positions:
            return buffer, None, b""
        pos = min(positions)
        if buffer[pos : pos + 2] == b"\r\n":
            return buffer[:pos], b"\r\n", buffer[pos + 2 :]
        return buffer[:pos], buffer[pos : pos + 1], buffer[pos + 1 :]

    def _handle_line(self, line: str) -> str | None:
        if line == "":
            if not self._data_lines:
                return None
            data = "\n".join(self._data_lines)
            self._data_lines = []
            return data
        if line.startswith(":"):
            return None
        field, value = _split_sse_field(line)
        if field == "data":
            self._data_lines.append(value)
        return None


def _split_sse_field(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line, ""
    field, value = line.split(":", 1)
    if value.startswith(" "):
        value = value[1:]
    return field, value


def _casefold_headers(headers: dict[str, Any]) -> dict[str, str]:
    return {str(key).lower(): str(value) for key, value in headers.items()}


def _set_turn_state(turn_state: Any, value: str) -> None:
    setter = getattr(turn_state, "set", None)
    if callable(setter):
        setter(value)
    elif isinstance(turn_state, dict):
        turn_state["value"] = value


__all__ = [
    "CYBER_POLICY_FALLBACK_MESSAGE",
    "TRUSTED_ACCESS_FOR_CYBER_VERIFICATION",
    "ResponsesEventError",
    "ResponsesStreamEvent",
    "process_responses_event",
    "process_sse",
    "spawn_response_stream",
    "try_parse_retry_after",
]
