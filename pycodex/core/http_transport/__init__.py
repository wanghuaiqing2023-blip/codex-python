"""Stdlib HTTP transport helpers for prepared sampling requests."""

from __future__ import annotations

import json
import math
import os
import re
import inspect
import importlib
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from types import SimpleNamespace
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin

from pycodex.core.client import (
    LastResponse,
    ModelClient,
    ModelClientSession,
    RESPONSES_ENDPOINT,
    X_CODEX_TURN_STATE_HEADER,
    build_responses_headers,
    build_session_headers,
    insert_header_if_valid,
    stamp_ws_stream_request_start_ms,
)
from pycodex.codex_api import map_api_error
from pycodex.codex_api.common import ResponseEvent
from pycodex.codex_api.endpoint.responses_websocket import ResponsesWebsocketClient
from pycodex.codex_api.error import ApiError
from pycodex.codex_api.provider import Provider as CodexApiProvider
from pycodex.codex_api.provider import RetryConfig
from pycodex.codex_client import TransportError
from pycodex.core.session.turn.sampler import PreparedSamplingRequest, PreparedSamplingResult
from pycodex.core.session.turn.sampler import sample_with_model_client_session
from pycodex.core.session.turn.sampler import sample_with_model_client_session_retries
from pycodex.core.session.turn.runtime import BuiltToolsFn, SamplerFn, UserTurnSamplingResult
from pycodex.core.session.turn.runtime import run_user_turn_sampling_from_session
from pycodex.protocol import AccountPlanType, AuthPlanType, CodexErr, CodexErrorInfo, ConnectionFailedError, ContentItem, CreditsSnapshot
from pycodex.protocol import EventMsg, StreamErrorEvent, WarningEvent
from pycodex.protocol import ModelVerification
from pycodex.protocol import RateLimitReachedType, RateLimitSnapshot, RateLimitWindow
from pycodex.protocol import ResponseStreamFailed, RetryLimitReachedError
from pycodex.protocol import UnexpectedResponseError, UsageLimitReachedError, UserInput
from pycodex.protocol import ResponseItem

CODEX_EXEC_ORIGINATOR = "codex_exec"
CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"
OPENAI_MODEL_HEADER = "openai-model"
X_REASONING_INCLUDED_HEADER = "x-reasoning-included"
X_MODELS_ETAG_HEADER = "x-models-etag"
DEFAULT_STREAM_MAX_RETRIES = 5
MAX_STREAM_MAX_RETRIES = 100


def _timing_trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        return


@dataclass(frozen=True)
class HttpTransportConfig:
    """Configuration for a prepared Responses API HTTP request."""

    endpoint: str
    headers: Mapping[str, str] | None = None
    timeout: float | None = None
    turn_state: Any = None
    enable_request_compression: bool = False
    use_codex_backend_auth: bool = False


def http_transport_config_from_provider(
    model_client: ModelClient,
    provider: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    turn_metadata_header: str | None = None,
) -> HttpTransportConfig:
    """Build HTTP transport config from provider/auth/model-client state."""

    resolved_endpoint = endpoint or _provider_responses_endpoint(provider)
    resolved_auth = auth if auth is not None else getattr(provider, "auth", None)
    headers = model_client.build_compact_request_headers(
        turn_metadata_header=turn_metadata_header,
        auth=resolved_auth,
    )
    headers.update(
        {
            key: value
            for key, value in build_responses_headers(
                model_client.state.beta_features_header,
                None,
                turn_metadata_header,
            ).items()
            if key not in headers
        }
    )
    if model_client.state.include_timing_metrics:
        insert_header_if_valid(headers, "x-responsesapi-include-timing-metrics", "true")
    insert_header_if_valid(headers, "Originator", exec_originator_header_value())
    return HttpTransportConfig(
        resolved_endpoint,
        headers=headers,
        timeout=timeout,
        enable_request_compression=model_client.state.enable_request_compression,
        use_codex_backend_auth=_auth_uses_codex_backend(resolved_auth),
    )


def send_prepared_http_sampling_request(
    prepared: PreparedSamplingRequest,
    config: HttpTransportConfig,
    *,
    opener: Any = None,
) -> PreparedSamplingResult:
    """Send a prepared sampling request with the Python standard library."""

    json_request = _to_json_compatible(prepared.prepared_request)
    headers = _request_headers_for_config(config)
    body = json.dumps(json_request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    body, headers = prepare_request_body_for_transport(body, headers, config)
    request = Request(config.endpoint, data=body, headers=headers, method="POST")
    open_fn = urlopen if opener is None else opener
    try:
        response = open_fn(request, timeout=config.timeout) if config.timeout is not None else open_fn(request)
    except HTTPError as exc:
        raise _codex_err_from_http_error(exc) from exc
    except TimeoutError as exc:
        raise CodexErr.simple("request_timeout") from exc
    except URLError as exc:
        raise _codex_err_from_url_error(exc) from exc
    headers = _response_headers(response)
    _record_turn_state_from_headers(config.turn_state, headers)
    with response:
        try:
            payload = response.read()
        except OSError as exc:
            raise CodexErr.response_stream_failed(ResponseStreamFailed(str(exc))) from exc
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CodexErr.response_stream_failed(ResponseStreamFailed(str(exc))) from exc
    except json.JSONDecodeError:
        return _prepared_sampling_result_from_sse(prepared, payload, headers=headers)
    payload_error = _codex_err_from_responses_payload(decoded)
    if payload_error is not None:
        raise payload_error
    response_items = response_items_from_responses_payload(decoded)
    return PreparedSamplingResult(
        prepared_request=prepared.prepared_request,
        response_items=response_items,
        raw_result=decoded,
        mode=prepared.mode,
        rate_limits=_parse_all_rate_limits(headers),
        server_model=_non_empty_header(headers, OPENAI_MODEL_HEADER),
        server_models=tuple(_single_optional(_non_empty_header(headers, OPENAI_MODEL_HEADER))),
        server_reasoning_included=_server_reasoning_included(headers),
        models_etag=_non_empty_header(headers, X_MODELS_ETAG_HEADER),
        end_turn=decoded.get("end_turn") if isinstance(decoded.get("end_turn"), bool) else None,
        stream_events=(),
    )


async def send_prepared_http_sampling_request_live(
    prepared: PreparedSamplingRequest,
    config: HttpTransportConfig,
    *,
    opener: Any = None,
) -> PreparedSamplingResult:
    """Send a prepared HTTP request and forward SSE events as they arrive.

    Rust source: ``codex-core/src/client.rs::stream_responses_api`` maps the
    response stream into Codex events before the full response completes.  This
    async wrapper keeps stdlib HTTP but preserves that live-event contract for
    callers that provide ``sampling_request.stream_event_observer``.
    """

    json_request = _to_json_compatible(prepared.prepared_request)
    body = json.dumps(json_request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = _request_headers_for_config(config)
    body, headers = prepare_request_body_for_transport(body, headers, config)
    request = Request(config.endpoint, data=body, headers=headers, method="POST")
    open_fn = opener if opener is not None else urlopen
    try:
        response = open_fn(request, timeout=config.timeout) if config.timeout is not None else open_fn(request)
    except HTTPError as exc:
        raise _codex_err_from_http_error(exc) from exc
    except TimeoutError as exc:
        raise CodexErr.simple("request_timeout") from exc
    except URLError as exc:
        raise _codex_err_from_url_error(exc) from exc
    response_headers = _response_headers(response)
    _record_turn_state_from_headers(config.turn_state, response_headers)
    live_stream_events_emitted = False
    with response:
        try:
            readline = getattr(response, "readline", None)
            if callable(readline):
                payload, live_stream_events_emitted = await _read_http_response_payload_live(
                    prepared,
                    response,
                    readline,
                )
            else:
                payload = response.read()
        except OSError as exc:
            raise CodexErr.response_stream_failed(ResponseStreamFailed(str(exc))) from exc
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise CodexErr.response_stream_failed(ResponseStreamFailed(str(exc))) from exc
    except json.JSONDecodeError:
        return _prepared_sampling_result_from_sse(
            prepared,
            payload,
            headers=response_headers,
            live_stream_events_emitted=live_stream_events_emitted,
        )
    payload_error = _codex_err_from_responses_payload(decoded)
    if payload_error is not None:
        raise payload_error
    response_items = response_items_from_responses_payload(decoded)
    return PreparedSamplingResult(
        prepared_request=prepared.prepared_request,
        response_items=response_items,
        raw_result=decoded,
        mode=prepared.mode,
        rate_limits=_parse_all_rate_limits(response_headers),
        server_model=_non_empty_header(response_headers, OPENAI_MODEL_HEADER),
        server_models=tuple(_single_optional(_non_empty_header(response_headers, OPENAI_MODEL_HEADER))),
        server_reasoning_included=_server_reasoning_included(response_headers),
        models_etag=_non_empty_header(response_headers, X_MODELS_ETAG_HEADER),
        end_turn=decoded.get("end_turn") if isinstance(decoded.get("end_turn"), bool) else None,
        stream_events=(),
        live_stream_events_emitted=live_stream_events_emitted,
    )


async def _read_http_response_payload_live(
    prepared: PreparedSamplingRequest,
    response: Any,
    readline: Any,
) -> tuple[bytes, bool]:
    chunks: list[bytes] = []
    data_lines: list[str] = []
    event_name: str | None = None
    live_stream_events_emitted = False
    while True:
        line_bytes = readline()
        if not line_bytes:
            break
        if isinstance(line_bytes, str):
            raw_line = line_bytes
            chunks.append(line_bytes.encode("utf-8"))
        else:
            chunks.append(bytes(line_bytes))
            raw_line = bytes(line_bytes).decode("utf-8", errors="replace")
        line = raw_line.rstrip("\r\n")
        if not line:
            event = _sse_json_event_from_lines(data_lines, event_name)
            data_lines = []
            event_name = None
            if event is not None:
                live_stream_events_emitted = (
                    await _notify_live_sse_event(prepared, event) or live_stream_events_emitted
                )
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip() or None
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
    event = _sse_json_event_from_lines(data_lines, event_name)
    if event is not None:
        live_stream_events_emitted = await _notify_live_sse_event(prepared, event) or live_stream_events_emitted
    return b"".join(chunks), live_stream_events_emitted


async def _notify_live_sse_event(prepared: PreparedSamplingRequest, event: Mapping[str, Any]) -> bool:
    if event.get("type") == "response.completed":
        return False
    response_event = _response_event_from_sse_event(event)
    if response_event is None:
        return False
    item = response_event.get("item")
    _timing_trace(
        "http_sse_live_event",
        type=response_event.get("type"),
        item_type=getattr(item, "type", None),
        item_name=getattr(item, "name", None),
        call_id=getattr(item, "call_id", None),
    )
    return await _notify_stream_event_observer(
        getattr(prepared.sampling_request, "stream_event_observer", None),
        response_event,
    )


def _request_headers_for_config(config: HttpTransportConfig) -> dict[str, str]:
    headers = {"Content-Type": "application/json", **dict(config.headers or {})}
    turn_state = getattr(config, "turn_state", None)
    getter = getattr(turn_state, "get", None)
    if callable(getter):
        state = getter()
        if isinstance(state, str):
            insert_header_if_valid(headers, X_CODEX_TURN_STATE_HEADER, state)
    return headers


def prepare_request_body_for_transport(
    body: bytes,
    headers: Mapping[str, str] | None,
    config: HttpTransportConfig,
    *,
    zstd_compress: Any = None,
) -> tuple[bytes, dict[str, str]]:
    if not isinstance(body, bytes):
        raise TypeError("body must be bytes")
    prepared_headers = dict(headers or {})
    if not config.enable_request_compression or not config.use_codex_backend_auth:
        return body, prepared_headers
    compressor = zstd_compress if zstd_compress is not None else _zstd_compressor()
    if compressor is None:
        return body, prepared_headers
    compressed = compressor(body)
    if not isinstance(compressed, bytes):
        raise TypeError("zstd compressor must return bytes")
    prepared_headers["Content-Encoding"] = "zstd"
    return compressed, prepared_headers


def _zstd_compressor() -> Any | None:
    try:
        module = importlib.import_module("zstandard")
    except ImportError:
        return None
    compressor_cls = getattr(module, "ZstdCompressor", None)
    if compressor_cls is None:
        return None
    compressor = compressor_cls()
    compress = getattr(compressor, "compress", None)
    return compress if callable(compress) else None


def _auth_uses_codex_backend(auth: Any) -> bool:
    if auth is None or isinstance(auth, str):
        return False
    if isinstance(auth, Mapping):
        value = auth.get("auth_mode") or auth.get("mode")
    else:
        value = getattr(auth, "auth_mode", None)
        if callable(value):
            value = value()
    if value is None:
        return False
    normalized = str(value).lower()
    return normalized in {"chatgpt", "chatgpt_auth", "chatgptauth", "codex_backend", "codex-backend"}


def _record_turn_state_from_headers(turn_state: Any, headers: Any) -> None:
    if turn_state is None:
        return
    value = _header_value_allow_empty(headers, X_CODEX_TURN_STATE_HEADER)
    if value is None:
        return
    setter = getattr(turn_state, "set", None)
    if callable(setter):
        setter(value)


def _prepared_sampling_result_from_sse(
    prepared: PreparedSamplingRequest,
    payload: bytes,
    *,
    headers: Any = None,
    live_stream_events_emitted: bool = False,
) -> PreparedSamplingResult:
    try:
        text = payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CodexErr.response_stream_failed(ResponseStreamFailed(str(exc))) from exc
    parsed = _parse_responses_sse_stream(text)
    header_rate_limits = _parse_all_rate_limits(headers)
    header_server_model = _non_empty_header(headers, OPENAI_MODEL_HEADER)
    header_events = _response_header_stream_events(
        header_server_model=header_server_model,
        rate_limits=header_rate_limits,
        models_etag=_non_empty_header(headers, X_MODELS_ETAG_HEADER),
        server_reasoning_included=_server_reasoning_included(headers),
    )
    parsed_stream_events = tuple(parsed.get("stream_events") or ())
    parsed_server_models = tuple(parsed.get("server_models") or ())
    return PreparedSamplingResult(
        prepared_request=prepared.prepared_request,
        response_items=parsed["response_items"],
        raw_result=parsed["raw_result"],
        mode=prepared.mode,
        rate_limits=header_rate_limits,
        server_model=parsed.get("server_model") or header_server_model,
        server_models=tuple(_single_optional(header_server_model)) + parsed_server_models,
        server_reasoning_included=_server_reasoning_included(headers),
        models_etag=_non_empty_header(headers, X_MODELS_ETAG_HEADER),
        model_verifications=tuple(parsed.get("model_verifications") or ()),
        end_turn=parsed.get("end_turn") if isinstance(parsed.get("end_turn"), bool) else None,
        stream_events=header_events + parsed_stream_events,
        live_stream_events_emitted=live_stream_events_emitted,
    )


def _response_header_stream_events(
    *,
    header_server_model: str | None,
    rate_limits: tuple[RateLimitSnapshot, ...],
    models_etag: str | None,
    server_reasoning_included: bool | None,
) -> tuple[dict[str, Any], ...]:
    events: list[dict[str, Any]] = []
    if header_server_model is not None:
        events.append({"type": "server_model", "server_model": header_server_model})
    for snapshot in rate_limits:
        events.append({"type": "rate_limits", "rate_limits": snapshot})
    if models_etag is not None:
        events.append({"type": "models_etag", "models_etag": models_etag})
    if server_reasoning_included is not None:
        events.append({"type": "server_reasoning_included", "server_reasoning_included": server_reasoning_included})
    return tuple(events)


def _parse_responses_sse_stream(text: str) -> dict[str, Any]:
    events = tuple(_iter_sse_json_events(text))
    if not events:
        raise CodexErr.response_stream_failed(ResponseStreamFailed("stream closed before response.completed"))

    response_items: list[ResponseItem] = []
    completed_response: Mapping[str, Any] | None = None
    completed_event: Mapping[str, Any] | None = None
    server_models: list[str] = []
    model_verifications: list[ModelVerification] = []
    stream_events: list[dict[str, Any]] = []
    active_delta_message: dict[str, Any] | None = None
    active_delta_index: int | None = None
    active_delta_tool_call: dict[str, Any] | None = None
    active_delta_tool_call_index: int | None = None
    pending_stream_error: CodexErr | None = None
    for event in events:
        server_model = _sse_response_model(event)
        if server_model is not None and (not server_models or server_models[-1] != server_model):
            server_models.append(server_model)
            stream_events.append({"type": "server_model", "server_model": server_model})
        new_model_verifications: list[ModelVerification] = []
        for verification in _sse_model_verifications(event):
            if verification not in model_verifications:
                model_verifications.append(verification)
                new_model_verifications.append(verification)
        if new_model_verifications:
            stream_events.append(
                {
                    "type": "model_verifications",
                    "model_verifications": tuple(new_model_verifications),
                }
            )
        response_event = _response_event_from_sse_event(event)
        if response_event is not None:
            stream_events.append(response_event)
        event_type = event.get("type")
        if event_type == "response.output_item.done":
            item = event.get("item") or event.get("output_item")
            if isinstance(item, Mapping):
                done_item = _sse_response_item_or_none(item)
                if done_item is None:
                    continue
                if (
                    active_delta_message is not None
                    and active_delta_index is not None
                    and _sse_done_replaces_active_delta(done_item, active_delta_message)
                ):
                    response_items[active_delta_index] = done_item
                elif (
                    active_delta_tool_call is not None
                    and active_delta_tool_call_index is not None
                    and _sse_done_replaces_active_tool_call(done_item, active_delta_tool_call)
                ):
                    response_items[active_delta_tool_call_index] = done_item
                else:
                    response_items.append(done_item)
                active_delta_message = None
                active_delta_index = None
                active_delta_tool_call = None
                active_delta_tool_call_index = None
        elif event_type == "response.output_item.added":
            item = event.get("item") or event.get("output_item")
            active_delta_index = None
            active_delta_tool_call_index = None
            added_item = _sse_response_item_or_none(item)
            active_delta_message = _sse_delta_message_seed(item) if added_item is not None else None
            active_delta_tool_call = _sse_delta_tool_call_seed(item) if added_item is not None else None
            if added_item is not None and active_delta_message is not None:
                response_items.append(
                    ResponseItem.message(
                        str(active_delta_message.get("role") or "assistant"),
                        (ContentItem.output_text(str(active_delta_message.get("text") or "")),),
                        id=active_delta_message.get("id") if isinstance(active_delta_message.get("id"), str) else None,
                    )
                )
                active_delta_index = len(response_items) - 1
            elif added_item is not None and active_delta_tool_call is not None:
                response_items.append(_sse_tool_call_item_from_delta(active_delta_tool_call))
                active_delta_tool_call_index = len(response_items) - 1
        elif event_type == "response.output_text.delta":
            delta = event.get("delta")
            if isinstance(delta, str) and active_delta_message is not None and active_delta_index is not None:
                active_delta_message["text"] = str(active_delta_message.get("text") or "") + delta
                response_items[active_delta_index] = ResponseItem.message(
                    str(active_delta_message.get("role") or "assistant"),
                    (ContentItem.output_text(str(active_delta_message.get("text") or "")),),
                    id=active_delta_message.get("id") if isinstance(active_delta_message.get("id"), str) else None,
                )
        elif event_type in {"response.function_call_arguments.delta", "response.custom_tool_call_input.delta"}:
            delta = event.get("delta")
            if (
                isinstance(delta, str)
                and active_delta_tool_call is not None
                and active_delta_tool_call_index is not None
                and _sse_tool_delta_applies(event, active_delta_tool_call, event_type)
            ):
                active_delta_tool_call["text"] = str(active_delta_tool_call.get("text") or "") + delta
                response_items[active_delta_tool_call_index] = _sse_tool_call_item_from_delta(active_delta_tool_call)
        elif event_type == "response.completed":
            response = event.get("response")
            if isinstance(response, Mapping):
                _validate_sse_completed_response(response)
                completed_event = event
                completed_response = response
                break
        elif event_type == "response.incomplete":
            pending_stream_error = CodexErr.stream(_sse_incomplete_message(event))
        elif event_type == "response.failed":
            mapped = _codex_err_from_responses_payload(event)
            if mapped is None:
                response = event.get("response")
                mapped = _codex_err_from_responses_payload(response) if isinstance(response, Mapping) else None
            if mapped is not None:
                pending_stream_error = mapped
            else:
                pending_stream_error = CodexErr.stream(_sse_failed_message(event))
        elif event_type in {"error", "response.error"}:
            mapped = _codex_err_from_responses_payload(event)
            if mapped is not None:
                raise mapped
            raise CodexErr.response_stream_failed(ResponseStreamFailed(_sse_error_message(event)))

    if completed_response is None:
        if pending_stream_error is not None:
            raise pending_stream_error
        raise CodexErr.response_stream_failed(ResponseStreamFailed("stream closed before response.completed"))

    if not response_items:
        try:
            response_items = list(response_items_from_responses_payload(completed_response))
        except (KeyError, TypeError, ValueError):
            response_items = []

    raw_result = dict(completed_response)
    if _responses_output_is_empty(raw_result.get("output")):
        raw_result["output"] = [item.to_mapping() for item in response_items]
    if completed_event is not None and "type" not in raw_result:
        raw_result["type"] = completed_event.get("type")
    return {
        "response_items": tuple(response_items),
        "raw_result": raw_result,
        "server_model": server_models[-1] if server_models else None,
        "server_models": tuple(server_models),
        "model_verifications": tuple(model_verifications),
        "end_turn": completed_response.get("end_turn") if isinstance(completed_response.get("end_turn"), bool) else None,
        "stream_events": tuple(stream_events),
    }


def _response_event_from_sse_event(event: Mapping[str, Any]) -> dict[str, Any] | None:
    event_type = event.get("type")
    if event_type == "response.output_item.done":
        item = event.get("item") or event.get("output_item")
        done_item = _sse_response_item_or_none(item)
        if done_item is not None:
            return {"type": "output_item_done", "item": done_item}
    if event_type == "response.output_item.added":
        item = event.get("item") or event.get("output_item")
        added_item = _sse_response_item_or_none(item)
        if added_item is not None:
            return {"type": "output_item_added", "item": added_item}
    if event_type == "response.output_text.delta":
        delta = event.get("delta")
        if isinstance(delta, str):
            return {"type": "output_text_delta", "delta": delta}
    if event_type == "response.custom_tool_call_input.delta":
        delta = event.get("delta")
        item_id = event.get("item_id") or event.get("call_id")
        if isinstance(delta, str) and isinstance(item_id, str):
            result: dict[str, Any] = {"type": "tool_call_input_delta", "item_id": item_id, "delta": delta}
            if isinstance(event.get("call_id"), str):
                result["call_id"] = event["call_id"]
            return result
    if event_type == "response.function_call_arguments.delta":
        delta = event.get("delta")
        item_id = event.get("item_id") or event.get("call_id")
        if isinstance(delta, str) and isinstance(item_id, str):
            result = {"type": "tool_call_input_delta", "item_id": item_id, "delta": delta}
            if isinstance(event.get("call_id"), str):
                result["call_id"] = event["call_id"]
            return result
    if event_type == "response.reasoning_summary_text.delta":
        delta = event.get("delta")
        summary_index = event.get("summary_index")
        if isinstance(delta, str) and isinstance(summary_index, int) and not isinstance(summary_index, bool):
            return {"type": "reasoning_summary_delta", "delta": delta, "summary_index": summary_index}
    if event_type == "response.reasoning_text.delta":
        delta = event.get("delta")
        content_index = event.get("content_index")
        if isinstance(delta, str) and isinstance(content_index, int) and not isinstance(content_index, bool):
            return {"type": "reasoning_content_delta", "delta": delta, "content_index": content_index}
    if event_type == "response.reasoning_summary_part.added":
        summary_index = event.get("summary_index")
        if isinstance(summary_index, int) and not isinstance(summary_index, bool):
            return {"type": "reasoning_summary_part_added", "summary_index": summary_index}
    if event_type == "response.created" and isinstance(event.get("response"), Mapping):
        return {"type": "created"}
    if event_type == "response.completed":
        response = event.get("response")
        if isinstance(response, Mapping):
            _validate_sse_completed_response(response)
            return {
                "type": "completed",
                "response_id": response["id"],
                "token_usage": response.get("usage"),
                "end_turn": response.get("end_turn") if isinstance(response.get("end_turn"), bool) else None,
            }
    return None


def _iter_sse_json_events(text: str) -> tuple[Mapping[str, Any], ...]:
    events: list[Mapping[str, Any]] = []
    data_lines: list[str] = []
    event_name: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")
        if not line:
            _append_sse_event(events, data_lines, event_name)
            data_lines = []
            event_name = None
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip() or None
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip(" "))
    _append_sse_event(events, data_lines, event_name)
    return tuple(events)


def _append_sse_event(events: list[Mapping[str, Any]], data_lines: list[str], event_name: str | None = None) -> None:
    parsed = _sse_json_event_from_lines(data_lines, event_name)
    if parsed is not None:
        events.append(parsed)


def _sse_json_event_from_lines(data_lines: list[str], event_name: str | None = None) -> Mapping[str, Any] | None:
    if not data_lines:
        return None
    data = "\n".join(data_lines).strip()
    if not data or data == "[DONE]":
        return None
    try:
        parsed = json.loads(data)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, Mapping):
        return None
    if event_name and "type" not in parsed:
        parsed = {"type": event_name, **dict(parsed)}
    return parsed


def _sse_response_model(event: Mapping[str, Any]) -> str | None:
    response = event.get("response")
    if isinstance(response, Mapping):
        model = _openai_model_from_json_headers(response.get("headers"))
        if model is not None:
            return model
    return _openai_model_from_json_headers(event.get("headers"))


def _sse_delta_message_seed(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    if item.get("type") != "message":
        return None
    role = item.get("role")
    if role is not None and role != "assistant":
        return None
    text_parts: list[str] = []
    content = item.get("content")
    if isinstance(content, list):
        for part in content:
            if isinstance(part, Mapping) and part.get("type") == "output_text" and isinstance(part.get("text"), str):
                text_parts.append(str(part.get("text")))
    return {
        "id": item.get("id"),
        "role": role or "assistant",
        "text": "".join(text_parts),
    }


def _sse_delta_tool_call_seed(item: Any) -> dict[str, Any] | None:
    if not isinstance(item, Mapping):
        return None
    item_type = item.get("type")
    if item_type == "function_call":
        name = item.get("name")
        call_id = item.get("call_id")
        if not isinstance(name, str) or not isinstance(call_id, str):
            return None
        arguments = item.get("arguments")
        return {
            "id": item.get("id"),
            "type": "function_call",
            "call_id": call_id,
            "name": name,
            "namespace": item.get("namespace"),
            "text": arguments if isinstance(arguments, str) else "",
        }
    if item_type == "custom_tool_call":
        name = item.get("name")
        call_id = item.get("call_id")
        if not isinstance(name, str) or not isinstance(call_id, str):
            return None
        input_text = item.get("input")
        return {
            "id": item.get("id"),
            "type": "custom_tool_call",
            "call_id": call_id,
            "name": name,
            "status": item.get("status"),
            "text": input_text if isinstance(input_text, str) else "",
        }
    return None


def _sse_tool_call_item_from_delta(state: Mapping[str, Any]) -> ResponseItem:
    item_type = state.get("type")
    item_id = state.get("id") if isinstance(state.get("id"), str) else None
    call_id = str(state.get("call_id"))
    name = str(state.get("name"))
    text = str(state.get("text") or "")
    if item_type == "function_call":
        namespace = state.get("namespace") if isinstance(state.get("namespace"), str) else None
        return ResponseItem.function_call(name, text, call_id, namespace=namespace, id=item_id)
    status = state.get("status") if isinstance(state.get("status"), str) else None
    return ResponseItem.custom_tool_call(name, text, call_id, status=status, id=item_id)


def _sse_response_item_or_none(item: Any) -> ResponseItem | None:
    if not isinstance(item, Mapping):
        return None
    try:
        return ResponseItem.from_mapping(item)
    except (KeyError, TypeError, ValueError):
        return None


def _sse_done_replaces_active_delta(done_item: ResponseItem, active_delta_message: Mapping[str, Any]) -> bool:
    active_id = active_delta_message.get("id")
    if isinstance(active_id, str):
        return done_item.id == active_id
    return done_item.id is None and done_item.type == "message" and done_item.role == active_delta_message.get("role")


def _sse_done_replaces_active_tool_call(done_item: ResponseItem, active_delta_tool_call: Mapping[str, Any]) -> bool:
    active_id = active_delta_tool_call.get("id")
    if isinstance(active_id, str):
        return done_item.id == active_id
    return (
        done_item.id is None
        and done_item.type == active_delta_tool_call.get("type")
        and done_item.call_id == active_delta_tool_call.get("call_id")
    )


def _sse_tool_delta_applies(
    event: Mapping[str, Any],
    active_delta_tool_call: Mapping[str, Any],
    event_type: str,
) -> bool:
    expected_type = (
        "function_call"
        if event_type == "response.function_call_arguments.delta"
        else "custom_tool_call"
    )
    if active_delta_tool_call.get("type") != expected_type:
        return False
    item_id = event.get("item_id")
    if isinstance(item_id, str) and isinstance(active_delta_tool_call.get("id"), str):
        return item_id == active_delta_tool_call.get("id")
    call_id = event.get("call_id")
    if isinstance(call_id, str):
        return call_id == active_delta_tool_call.get("call_id")
    return True


def _responses_output_is_empty(output: Any) -> bool:
    if output is None:
        return True
    if isinstance(output, (list, tuple)):
        return not any(isinstance(item, Mapping) for item in output)
    return False


def _openai_model_from_json_headers(value: Any) -> str | None:
    if not isinstance(value, Mapping):
        return None
    for name, item in value.items():
        if not isinstance(name, str):
            continue
        if name.lower() not in {"openai-model", "x-openai-model"}:
            continue
        model = _json_value_as_string(item)
        if model:
            return model
    return None


def _json_value_as_string(value: Any) -> str | None:
    if isinstance(value, str):
        return value
    if isinstance(value, list) and value:
        return _json_value_as_string(value[0])
    return None


def _sse_model_verifications(event: Mapping[str, Any]) -> tuple[ModelVerification, ...]:
    if event.get("type") != "response.metadata":
        return ()
    metadata = event.get("metadata")
    if not isinstance(metadata, Mapping):
        return ()
    raw = metadata.get("openai_verification_recommendation")
    if not isinstance(raw, list):
        return ()
    verifications: list[ModelVerification] = []
    for item in raw:
        if item == "trusted_access_for_cyber" and ModelVerification.TRUSTED_ACCESS_FOR_CYBER not in verifications:
            verifications.append(ModelVerification.TRUSTED_ACCESS_FOR_CYBER)
    return tuple(verifications)


def _single_optional(value: Any) -> tuple[Any, ...]:
    return () if value is None else (value,)


def _sse_error_message(event: Mapping[str, Any]) -> str:
    error = _error_mapping(event)
    message = _error_message(error)
    if message:
        return message
    response = event.get("response")
    if isinstance(response, Mapping):
        message = _error_message(_error_mapping(response))
        if message:
            return message
    message_value = event.get("message")
    if isinstance(message_value, str) and message_value.strip():
        return message_value.strip()
    event_type = event.get("type")
    return event_type if isinstance(event_type, str) and event_type else "response stream failed"


def _sse_incomplete_message(event: Mapping[str, Any]) -> str:
    reason = None
    response = event.get("response")
    if isinstance(response, Mapping):
        details = response.get("incomplete_details")
        if isinstance(details, Mapping):
            value = details.get("reason")
            if isinstance(value, str) and value:
                reason = value
    return f"Incomplete response returned, reason: {reason or 'unknown'}"


def _sse_failed_message(event: Mapping[str, Any]) -> str:
    response = event.get("response")
    if isinstance(response, Mapping):
        message = _error_message(_error_mapping(response))
        if message:
            return message
    message = _error_message(_error_mapping(event))
    if message:
        return message
    return "response.failed event received"


def _validate_sse_completed_response(response: Mapping[str, Any]) -> None:
    if not isinstance(response.get("id"), str):
        raise CodexErr.stream("failed to parse ResponseCompleted: missing response id")
    usage = response.get("usage")
    if usage is not None and not isinstance(usage, Mapping):
        raise CodexErr.stream("failed to parse ResponseCompleted: invalid usage")
    if isinstance(usage, Mapping):
        for key in ("input_tokens", "output_tokens", "total_tokens"):
            value = usage.get(key)
            if isinstance(value, bool) or not isinstance(value, int):
                raise CodexErr.stream(f"failed to parse ResponseCompleted: missing or invalid usage.{key}")


def _to_json_compatible(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "to_mapping"):
        return _to_json_compatible(value.to_mapping())
    if isinstance(value, Mapping):
        return {str(key): _to_json_compatible(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_compatible(item) for item in value]
    return value


def _http_error_message(exc: HTTPError) -> str:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        body = ""
    parsed = _error_message_from_payload(body)
    if parsed:
        return f"Responses API request failed with HTTP {exc.code}: {parsed}"
    reason = getattr(exc, "reason", None)
    if reason:
        return f"Responses API request failed with HTTP {exc.code}: {reason}"
    return f"Responses API request failed with HTTP {exc.code}"


def _codex_err_from_http_error(exc: HTTPError) -> CodexErr:
    body = ""
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except OSError:
        body = ""
    mapped = _codex_err_from_http_status_body(
        exc.code,
        body,
        headers=exc.headers,
    )
    if mapped is not None:
        return mapped
    return CodexErr.unexpected_status(
        UnexpectedResponseError(
            status=exc.code,
            body=body,
            url=getattr(exc, "url", None),
            cf_ray=_header_value(exc.headers, "cf-ray"),
            request_id=_request_id(exc.headers),
            identity_authorization_error=_header_value(exc.headers, "x-openai-authorization-error"),
            identity_error_code=_x_error_json_code(exc.headers),
        )
    )


def _codex_err_from_url_error(exc: URLError) -> CodexErr:
    reason = getattr(exc, "reason", exc)
    if isinstance(reason, TimeoutError):
        return CodexErr.simple("request_timeout")
    return CodexErr.connection_failed(ConnectionFailedError(str(reason)))


def _response_headers(response: Any) -> Any:
    headers = getattr(response, "headers", None)
    if headers is not None:
        return headers
    info = getattr(response, "info", None)
    if callable(info):
        return info()
    return None


def _header_value(headers: Any, name: str) -> str | None:
    value = _header_value_allow_empty(headers, name)
    if isinstance(value, str) and value:
        return value
    return None


def _header_value_allow_empty(headers: Any, name: str) -> str | None:
    if headers is None:
        return None
    getter = getattr(headers, "get", None)
    if callable(getter):
        value = getter(name)
        if value is None:
            value = getter(name.lower())
        if value is None:
            value = getter(name.upper())
        if isinstance(value, str):
            return value
    items = getattr(headers, "items", None)
    if callable(items):
        name_lower = name.lower()
        for key, value in items():
            if isinstance(key, str) and key.lower() == name_lower and isinstance(value, str):
                return value
    return None


def _header_names(headers: Any) -> tuple[str, ...]:
    if headers is None:
        return ()
    keys = getattr(headers, "keys", None)
    if callable(keys):
        return tuple(key for key in keys() if isinstance(key, str))
    items = getattr(headers, "items", None)
    if callable(items):
        return tuple(key for key, _value in items() if isinstance(key, str))
    return ()


def _header_present(headers: Any, name: str) -> bool:
    name_lower = name.lower()
    return any(header.lower() == name_lower for header in _header_names(headers))


def _codex_err_from_http_status_body(
    status: int,
    body: str,
    *,
    headers: Any = None,
) -> CodexErr | None:
    parsed = _json_mapping(body)
    error = _error_mapping(parsed)
    if status == 503 and _error_code(error) in {"server_is_overloaded", "slow_down"}:
        return CodexErr.simple("server_overloaded")
    if status == 400:
        if _error_code(error) == "cyber_policy":
            return CodexErr.cyber_policy(
                _error_message(error) or "This request has been flagged for possible cybersecurity risk."
            )
        if "The image data you provided does not represent a valid image" in body:
            return CodexErr.simple("invalid_image_request")
        return CodexErr.invalid_request(body)
    if status == 500:
        return CodexErr.simple("internal_server_error")
    if status == 429:
        if _error_type(error) == "usage_limit_reached":
            return CodexErr.usage_limit_reached(
                UsageLimitReachedError(
                    plan_type=_auth_plan_type(error.get("plan_type") if error is not None else None),
                    resets_at=_utc_timestamp(error.get("resets_at") if error is not None else None),
                    rate_limits=_parse_rate_limit_for_limit(headers, _header_value(headers, "x-codex-active-limit")),
                    promo_message=_non_empty_header(headers, "x-codex-promo-message"),
                    rate_limit_reached_type=_rate_limit_reached_type(headers),
                )
            )
        if _error_type(error) == "usage_not_included":
            return CodexErr.simple("usage_not_included")
        return CodexErr.retry_limit(RetryLimitReachedError(status, _request_tracking_id(headers)))
    return None


def _codex_err_from_responses_payload(payload: Any) -> CodexErr | None:
    if not isinstance(payload, Mapping):
        return None
    error = _error_mapping(payload)
    if error is None:
        response = payload.get("response")
        error = _error_mapping(response) if isinstance(response, Mapping) else None
    if error is None:
        return None
    code = _error_code(error)
    if code == "context_length_exceeded":
        return CodexErr.simple("context_window_exceeded")
    if code == "insufficient_quota":
        return CodexErr.simple("quota_exceeded")
    if code == "usage_not_included":
        return CodexErr.simple("usage_not_included")
    if code == "cyber_policy":
        return CodexErr.cyber_policy(
            _error_message(error) or "This request has been flagged for possible cybersecurity risk."
        )
    if code == "invalid_prompt":
        return CodexErr.invalid_request(_error_message(error) or "Invalid request.")
    if code in {"server_is_overloaded", "slow_down"}:
        return CodexErr.simple("server_overloaded")
    if code == "rate_limit_exceeded":
        message = _error_message(error) or ""
        return CodexErr.stream(message, retry_after=_retry_after_seconds_from_error(error))
    return None


def _json_mapping(body: str) -> Mapping[str, Any] | None:
    if not body:
        return None
    try:
        parsed = json.loads(body)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, Mapping) else None


def _error_mapping(payload: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    if payload is None:
        return None
    error = payload.get("error")
    return error if isinstance(error, Mapping) else None


def _error_code(error: Mapping[str, Any] | None) -> str | None:
    value = error.get("code") if error is not None else None
    return value if isinstance(value, str) else None


def _error_type(error: Mapping[str, Any] | None) -> str | None:
    value = error.get("type") if error is not None else None
    return value if isinstance(value, str) else None


def _error_message(error: Mapping[str, Any] | None) -> str | None:
    value = error.get("message") if error is not None else None
    if not isinstance(value, str):
        return None
    value = value.strip()
    return value or None


def _retry_after_seconds_from_error(error: Mapping[str, Any] | None) -> float | None:
    message = _error_message(error)
    if message is None:
        return None
    match = re.search(r"try again in\s*(\d+(?:\.\d+)?)\s*(s|ms|seconds?)", message, flags=re.IGNORECASE)
    if match is None:
        return None
    value = float(match.group(1))
    unit = match.group(2).lower()
    if unit == "ms":
        return int(value) / 1000.0
    return value


def _request_id(headers: Any) -> str | None:
    return _header_value(headers, "x-request-id") or _header_value(headers, "x-oai-request-id")


def _request_tracking_id(headers: Any) -> str | None:
    return _request_id(headers) or _header_value(headers, "cf-ray")


def _non_empty_header(headers: Any, name: str) -> str | None:
    value = _header_value(headers, name)
    if value is None:
        return None
    value = value.strip()
    return value or None


def _x_error_json_code(headers: Any) -> str | None:
    encoded = _header_value(headers, "x-error-json")
    if not encoded:
        return None
    try:
        import base64

        decoded = base64.b64decode(encoded)
        parsed = json.loads(decoded.decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(parsed, Mapping):
        return None
    error = _error_mapping(parsed)
    return _error_code(error)


def _auth_plan_type(value: Any) -> AuthPlanType | None:
    if isinstance(value, str):
        return AuthPlanType.from_raw_value(value)
    return None


def _utc_timestamp(value: Any) -> datetime | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return None


def _rate_limit_reached_type(headers: Any) -> RateLimitReachedType | None:
    value = _non_empty_header(headers, "x-codex-rate-limit-reached-type")
    if value is None:
        return None
    try:
        return RateLimitReachedType.parse(value)
    except ValueError:
        return None


def _parse_rate_limit_for_limit(headers: Any, limit_id: str | None) -> RateLimitSnapshot | None:
    normalized = (limit_id or "codex").strip().lower().replace("_", "-")
    if not normalized:
        normalized = "codex"
    prefix = f"x-{normalized}"
    snapshot = RateLimitSnapshot(
        limit_id=normalized.replace("-", "_"),
        limit_name=_non_empty_header(headers, f"{prefix}-limit-name"),
        primary=_parse_rate_limit_window(
            headers,
            f"{prefix}-primary-used-percent",
            f"{prefix}-primary-window-minutes",
            f"{prefix}-primary-reset-at",
        ),
        secondary=_parse_rate_limit_window(
            headers,
            f"{prefix}-secondary-used-percent",
            f"{prefix}-secondary-window-minutes",
            f"{prefix}-secondary-reset-at",
        ),
        credits=_parse_credits_snapshot(headers),
    )
    return snapshot


def _parse_all_rate_limits(headers: Any) -> tuple[RateLimitSnapshot, ...]:
    if headers is None:
        return ()
    snapshots: list[RateLimitSnapshot] = []
    default_snapshot = _parse_rate_limit_for_limit(headers, None)
    if default_snapshot is not None:
        snapshots.append(default_snapshot)
    limit_ids = sorted(
        {
            limit_id
            for name in _header_names(headers)
            for limit_id in (_rate_limit_header_name_to_limit_id(name),)
            if limit_id is not None and limit_id != "codex"
        }
    )
    for limit_id in limit_ids:
        snapshot = _parse_rate_limit_for_limit(headers, limit_id)
        if snapshot is not None and _rate_limit_snapshot_has_data(snapshot):
            snapshots.append(snapshot)
    return tuple(snapshots)


def _rate_limit_header_name_to_limit_id(name: str) -> str | None:
    normalized = name.strip().lower()
    suffix = "-primary-used-percent"
    if not normalized.endswith(suffix):
        return None
    prefix = normalized[: -len(suffix)]
    if not prefix.startswith("x-"):
        return None
    limit = prefix[2:].strip()
    return limit.replace("-", "_") if limit else None


def _rate_limit_snapshot_has_data(snapshot: RateLimitSnapshot) -> bool:
    return snapshot.primary is not None or snapshot.secondary is not None or snapshot.credits is not None


def _parse_rate_limit_window(
    headers: Any,
    used_percent_header: str,
    window_minutes_header: str,
    resets_at_header: str,
) -> RateLimitWindow | None:
    used_percent = _header_float(headers, used_percent_header)
    if used_percent is None:
        return None
    window_minutes = _header_int(headers, window_minutes_header)
    resets_at = _header_int(headers, resets_at_header)
    if used_percent == 0.0 and (window_minutes is None or window_minutes == 0) and resets_at is None:
        return None
    return RateLimitWindow(used_percent=used_percent, window_minutes=window_minutes, resets_at=resets_at)


def _parse_credits_snapshot(headers: Any) -> CreditsSnapshot | None:
    has_credits = _header_bool(headers, "x-codex-credits-has-credits")
    unlimited = _header_bool(headers, "x-codex-credits-unlimited")
    if has_credits is None or unlimited is None:
        return None
    return CreditsSnapshot(
        has_credits=has_credits,
        unlimited=unlimited,
        balance=_non_empty_header(headers, "x-codex-credits-balance"),
    )


def _server_reasoning_included(headers: Any) -> bool | None:
    return True if _header_present(headers, X_REASONING_INCLUDED_HEADER) else None


def _header_float(headers: Any, name: str) -> float | None:
    value = _non_empty_header(headers, name)
    if value is None:
        return None
    try:
        parsed = float(value)
    except ValueError:
        return None
    return parsed if math.isfinite(parsed) else None


def _header_int(headers: Any, name: str) -> int | None:
    value = _non_empty_header(headers, name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _header_bool(headers: Any, name: str) -> bool | None:
    value = _non_empty_header(headers, name)
    if value is None:
        return None
    if value.lower() == "true" or value == "1":
        return True
    if value.lower() == "false" or value == "0":
        return False
    return None


def _error_message_from_payload(body: str) -> str:
    if not body:
        return ""
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return body.strip()
    if isinstance(payload, Mapping):
        error = payload.get("error")
        if isinstance(error, Mapping):
            message = error.get("message")
            if isinstance(message, str) and message:
                return message
        message = payload.get("message")
        if isinstance(message, str) and message:
            return message
    return body.strip()


def _provider_responses_endpoint(provider: Any) -> str:
    for name in ("responses_endpoint", "responses_url", "endpoint"):
        value = getattr(provider, name, None)
        if isinstance(value, str) and value:
            return value
    if isinstance(provider, Mapping):
        for name in ("responses_endpoint", "responses_url", "endpoint"):
            value = provider.get(name)
            if isinstance(value, str) and value:
                return value
    base_url = getattr(provider, "base_url", None)
    if base_url is None and isinstance(provider, Mapping):
        base_url = provider.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise ValueError("provider must define responses_endpoint, responses_url, endpoint, or base_url")
    return urljoin(base_url.rstrip("/") + "/", RESPONSES_ENDPOINT.lstrip("/"))


def exec_originator_header_value(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    override = source.get(CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR)
    return override if override else CODEX_EXEC_ORIGINATOR


def model_client_http_sampler(
    model_session: ModelClientSession,
    config: HttpTransportConfig,
    *,
    opener: Any = None,
    max_retries: int | None = None,
    sleep: Any = None,
    on_retry_decision: Any = None,
    auth_manager: Any = None,
    config_factory: Any = None,
) -> SamplerFn:
    """Create a sampler using ``ModelClientSession`` plus stdlib HTTP."""

    effective_config = config
    if getattr(effective_config, "turn_state", None) is None:
        effective_config = replace(effective_config, turn_state=model_session.turn_state)
    auth_recovery = auth_manager.unauthorized_recovery() if auth_manager is not None else None

    async def sampler(sampling_request):
        async def transport(prepared):
            nonlocal effective_config
            while True:
                try:
                    return await send_prepared_http_sampling_request_live(prepared, effective_config, opener=opener)
                except CodexErr as exc:
                    if not _codex_err_is_unauthorized(exc):
                        raise
                    if auth_recovery is None or not auth_recovery.has_next():
                        raise
                    try:
                        await _maybe_await(auth_recovery.next())
                    except Exception as refresh_exc:
                        error = getattr(refresh_exc, "error", refresh_exc)
                        raise CodexErr("refresh_token_failed", payload=error) from refresh_exc
                    if callable(config_factory):
                        rebuilt = config_factory()
                        if getattr(rebuilt, "turn_state", None) is None:
                            rebuilt = replace(rebuilt, turn_state=model_session.turn_state)
                        effective_config = rebuilt

        if max_retries is None:
            return await sample_with_model_client_session(sampling_request, model_session, transport)
        retry_decision_callback = _http_sampling_retry_decision_callback(
            getattr(sampling_request, "session", None),
            getattr(sampling_request, "turn_context", None),
            on_retry_decision,
        )
        return await sample_with_model_client_session_retries(
            sampling_request,
            model_session,
            transport,
            max_retries=max_retries,
            sleep=sleep,
            on_retry_decision=retry_decision_callback,
        )

    return sampler


class _FallbackToHttp(Exception):
    pass


@dataclass(frozen=True)
class _JsonWsRequest:
    payload: Mapping[str, Any]

    def to_json_dict(self) -> dict[str, Any]:
        return dict(self.payload)


@dataclass(frozen=True)
class _AuthHeadersAdapter:
    auth: Any

    def add_auth_headers(self, headers: dict[str, str]) -> None:
        for key, value in _auth_headers_from_value(self.auth).items():
            headers[key] = value


def model_client_websocket_preferred_sampler(
    model_session: ModelClientSession,
    config: HttpTransportConfig,
    *,
    opener: Any = None,
    max_retries: int | None = None,
    sleep: Any = None,
    on_retry_decision: Any = None,
    auth_manager: Any = None,
    config_factory: Any = None,
    websocket_connector: Any = None,
    turn_metadata_header: str | None = None,
    stream_event_observer: Any = None,
) -> SamplerFn:
    """Create a Rust-shaped sampler that prefers Responses WebSocket.

    Rust source: ``codex-rs/core/src/client.rs::ModelClientSession::stream``.
    Contract: Responses transport first attempts ``stream_responses_websocket``
    when the provider supports websockets; HTTP is used only after a websocket
    fallback decision or when websockets are disabled.
    """

    effective_config = config
    auth_recovery = auth_manager.unauthorized_recovery() if auth_manager is not None else None
    async def sampler(sampling_request):
        if model_session.client.responses_websocket_enabled():
            nonlocal effective_config

            async def websocket_transport(prepared: PreparedSamplingRequest) -> PreparedSamplingResult:
                nonlocal effective_config
                try:
                    return await _send_prepared_websocket_sampling_request(
                        prepared,
                        model_session,
                        auth=_websocket_auth_for_config(effective_config),
                        connector=websocket_connector,
                        turn_metadata_header=turn_metadata_header,
                        stream_event_observer=stream_event_observer,
                    )
                except _FallbackToHttp:
                    raise
                except ApiError as exc:
                    if _api_error_is_unauthorized(exc) and auth_recovery is not None and auth_recovery.has_next():
                        try:
                            await _maybe_await(auth_recovery.next())
                        except Exception as refresh_exc:
                            error = getattr(refresh_exc, "error", refresh_exc)
                            raise CodexErr("refresh_token_failed", payload=error) from refresh_exc
                        if callable(config_factory):
                            rebuilt = config_factory()
                            if getattr(rebuilt, "turn_state", None) is None:
                                rebuilt = replace(rebuilt, turn_state=model_session.turn_state)
                            effective_config = rebuilt
                        model_session.reset_websocket_session()
                        return await websocket_transport(prepared)
                    raise map_api_error(exc) from exc

            async def http_fallback_transport(prepared: PreparedSamplingRequest) -> Any:
                _timing_trace("websocket_fallback_to_http")
                model_session.force_http_fallback(
                    getattr(sampling_request, "session_telemetry", None),
                    getattr(sampling_request, "model_info", None),
                )
                return await http_transport(prepared)

            async def http_transport(prepared: PreparedSamplingRequest) -> Any:
                nonlocal effective_config
                while True:
                    try:
                        _timing_trace("http_sampling_request_start")
                        return await send_prepared_http_sampling_request_live(prepared, effective_config, opener=opener)
                    except CodexErr as exc:
                        if not _codex_err_is_unauthorized(exc):
                            raise
                        if auth_recovery is None or not auth_recovery.has_next():
                            raise
                        try:
                            await _maybe_await(auth_recovery.next())
                        except Exception as refresh_exc:
                            error = getattr(refresh_exc, "error", refresh_exc)
                            raise CodexErr("refresh_token_failed", payload=error) from refresh_exc
                        if callable(config_factory):
                            rebuilt = config_factory()
                            if getattr(rebuilt, "turn_state", None) is None:
                                rebuilt = replace(rebuilt, turn_state=model_session.turn_state)
                            effective_config = rebuilt

            try:
                sampled = await sample_with_model_client_session_retries(
                    sampling_request,
                    model_session,
                    websocket_transport,
                    max_retries=http_sampling_stream_max_retries(model_session.client.state.provider)
                    if max_retries is None
                    else max_retries,
                    fallback_transport=http_fallback_transport,
                    responses_websocket_enabled=True,
                    sleep=sleep,
                    on_retry_decision=_http_sampling_retry_decision_callback(
                        getattr(sampling_request, "session", None),
                        getattr(sampling_request, "turn_context", None),
                        on_retry_decision,
                    ),
                    mode="http",
                )
                if isinstance(sampled.raw_result, PreparedSamplingResult):
                    return sampled.raw_result
                return sampled
            except _FallbackToHttp:
                model_session.force_http_fallback(
                    getattr(sampling_request, "session_telemetry", None),
                    getattr(sampling_request, "model_info", None),
                )
        http_sampler = model_client_http_sampler(
            model_session,
            effective_config,
            opener=opener,
            max_retries=max_retries,
            sleep=sleep,
            on_retry_decision=on_retry_decision,
            auth_manager=auth_manager,
            config_factory=config_factory,
        )
        return await http_sampler(sampling_request)

    return sampler


async def prewarm_model_client_websocket_session(
    model_session: ModelClientSession,
    config: HttpTransportConfig,
    *,
    model: str | None = None,
    request: Mapping[str, Any] | None = None,
    connector: Any = None,
    turn_metadata_header: str | None = None,
) -> PreparedSamplingResult | None:
    """Warm a ``ModelClientSession`` websocket before the first regular turn.

    Rust source:
    ``codex-rs/core/src/session_startup_prewarm.rs::schedule_startup_prewarm_inner``.
    Contract: startup prewarm creates a client session, sends a
    ``generate=false`` websocket request, and returns that same session for the
    first regular turn to consume.
    """

    if not model_session.client.responses_websocket_enabled():
        _timing_trace("prewarm_websocket_skipped", reason="websocket_disabled")
        return None
    if request is None:
        if not model:
            raise ValueError("model is required when request is not provided")
        request = {
            "model": model,
            "input": [],
            "stream": True,
            "store": False,
        }
    logical_request = dict(request)
    prepared = PreparedSamplingRequest(
        sampling_request=SimpleNamespace(stream_event_observer=None),
        prepared_request=model_session.prepare_http_request(logical_request),
        mode="responses_websocket",
    )
    _timing_trace("prewarm_websocket_request_built", input_len=len(logical_request.get("input") or ()))
    result = await _send_prepared_websocket_sampling_request(
        prepared,
        model_session,
        auth=_websocket_auth_for_config(config),
        connector=connector,
        turn_metadata_header=turn_metadata_header,
        warmup=True,
    )
    _timing_trace("prewarm_websocket_completed", events=len(result.stream_events))
    return result


async def _send_prepared_websocket_sampling_request(
    prepared: PreparedSamplingRequest,
    model_session: ModelClientSession,
    *,
    auth: Any,
    connector: Any = None,
    turn_metadata_header: str | None = None,
    stream_event_observer: Any = None,
    warmup: bool = False,
) -> PreparedSamplingResult:
    setup = await model_session.client.current_client_setup()
    api_provider = setup.api_provider or await _api_provider_from_model_provider(model_session.client.state.provider)
    api_auth = auth if auth is not None else setup.api_auth
    provider = _codex_api_provider(api_provider)

    needs_new = model_session.websocket_connection_needs_new()
    if needs_new:
        _timing_trace("websocket_connect_start", warmup=warmup)
        headers = model_session.client.build_websocket_headers(
            turn_state=model_session.turn_state,
            turn_metadata_header=turn_metadata_header,
        )
        websocket_client = ResponsesWebsocketClient.new(
            provider,
            _AuthHeadersAdapter(api_auth),
            connector=connector,
        )
        try:
            connection = websocket_client.connect(extra_headers=headers, turn_state=model_session.turn_state)
        except ApiError as exc:
            if _api_error_is_upgrade_required(exc):
                _timing_trace("websocket_connect_fallback_to_http", warmup=warmup)
                raise _FallbackToHttp() from exc
            _timing_trace("websocket_connect_failed", warmup=warmup, error=str(exc))
            raise
        model_session.apply_websocket_connection_lifecycle(True, connection=connection)
        _timing_trace("websocket_connect_done", warmup=warmup)
    else:
        model_session.apply_websocket_connection_lifecycle(False)
        _timing_trace("websocket_connect_reused", warmup=warmup)

    payload = model_session.client.build_websocket_payload(
        prepared.prepared_request,
        turn_metadata_header=turn_metadata_header,
    )
    if warmup:
        payload = dict(payload)
        payload["generate"] = False
    websocket_request, from_untraced_warmup = model_session.prepare_websocket_request(
        payload,
        prepared.prepared_request,
    )
    stamp_ws_stream_request_start_ms(websocket_request)
    connection = model_session.websocket_session.connection
    if connection is None:
        raise ApiError.stream("websocket connection is unavailable")
    _timing_trace("websocket_stream_request_start", warmup=warmup, reused=model_session.websocket_session.connection_reused())
    stream = connection.stream_request(
        _JsonWsRequest(websocket_request),
        model_session.websocket_session.connection_reused(),
    )
    result = await _prepared_sampling_result_from_response_stream(
        prepared,
        stream,
        stream_event_observer=stream_event_observer,
    )
    completed_id = _completed_response_id_from_stream_events(result.stream_events)
    if completed_id is not None:
        model_session.websocket_session.last_response = LastResponse(
            completed_id,
            result.response_items,
        )
        model_session.websocket_session.last_response_from_untraced_warmup = warmup
    model_session.websocket_session.last_request = dict(prepared.prepared_request)
    _timing_trace(
        "websocket_stream_request_done",
        warmup=warmup,
        completed_id=completed_id,
        items=len(result.response_items),
        events=len(result.stream_events),
    )
    return result


async def _prepared_sampling_result_from_response_stream(
    prepared: PreparedSamplingRequest,
    stream: Any,
    *,
    stream_event_observer: Any = None,
) -> PreparedSamplingResult:
    response_items: list[ResponseItem] = []
    stream_events: list[dict[str, Any]] = []
    server_model: str | None = None
    server_models: list[str] = []
    models_etag: str | None = None
    model_verifications: list[Any] = []
    rate_limits: list[Any] = []
    server_reasoning_included: bool | None = None
    end_turn: bool | None = None
    live_stream_events_emitted = False

    first_event = True
    for event in stream:
        if first_event:
            _timing_trace("websocket_stream_first_event")
            first_event = False
        if isinstance(event, ApiError):
            _timing_trace("websocket_stream_api_error", error=str(event))
            raise event
        if not isinstance(event, ResponseEvent):
            continue
        kind = event.kind
        value = event.value
        if kind == "server_model":
            server_model = str(value)
            server_models.append(server_model)
            stream_events.append({"type": "server_model", "server_model": server_model})
        elif kind == "models_etag":
            models_etag = str(value)
            stream_events.append({"type": "models_etag", "models_etag": models_etag})
        elif kind == "model_verifications":
            values = tuple(value or ())
            model_verifications.extend(values)
            stream_events.append({"type": "model_verifications", "model_verifications": values})
        elif kind == "rate_limits":
            snapshot = _protocol_rate_limit_snapshot_or_none(value)
            if snapshot is not None:
                event = {"type": "rate_limits", "rate_limits": snapshot}
                rate_limits.append(snapshot)
                stream_events.append(event)
                live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind == "server_reasoning_included":
            server_reasoning_included = bool(value)
            event = {"type": "server_reasoning_included", "server_reasoning_included": True}
            stream_events.append(event)
            live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind == "output_item_added":
            item = _response_item_or_none(value)
            if item is not None:
                event = {"type": "output_item_added", "item": item}
                stream_events.append(event)
                live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind == "output_item_done":
            item = _response_item_or_none(value)
            if item is not None:
                response_items.append(item)
                event = {"type": "output_item_done", "item": item}
                stream_events.append(event)
                live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind == "output_text_delta":
            event = {"type": "output_text_delta", "delta": str(value)}
            stream_events.append(event)
            live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind == "tool_call_input_delta":
            if isinstance(value, Mapping):
                event = {"type": "tool_call_input_delta", **dict(value)}
                stream_events.append(event)
                live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind in {"reasoning_summary_delta", "reasoning_content_delta"}:
            if isinstance(value, Mapping):
                event = {"type": kind, **dict(value)}
                stream_events.append(event)
                live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted
        elif kind == "completed":
            if isinstance(value, Mapping):
                end_turn_value = value.get("end_turn")
                end_turn = end_turn_value if isinstance(end_turn_value, bool) else None
                event = {"type": "completed", **dict(value)}
                stream_events.append(event)
                live_stream_events_emitted = await _notify_stream_event_observers(prepared, stream_event_observer, event) or live_stream_events_emitted

    if not any(event.get("type") == "completed" for event in stream_events):
        raise ApiError.stream("stream closed before response.completed")

    return PreparedSamplingResult(
        prepared_request=prepared.prepared_request,
        response_items=tuple(response_items),
        raw_result=None,
        mode="responses_websocket",
        rate_limits=tuple(rate_limits),
        server_model=server_model,
        server_models=tuple(server_models),
        server_reasoning_included=server_reasoning_included,
        models_etag=models_etag,
        model_verifications=tuple(model_verifications),
        end_turn=end_turn,
        stream_events=tuple(stream_events),
        live_stream_events_emitted=live_stream_events_emitted,
    )


async def _notify_stream_event_observers(
    prepared: PreparedSamplingRequest,
    observer: Any,
    event: Mapping[str, Any],
) -> bool:
    internal_emitted = await _notify_stream_event_observer(
        getattr(prepared.sampling_request, "stream_event_observer", None),
        event,
    )
    external_emitted = await _notify_stream_event_observer(observer, event)
    return internal_emitted or external_emitted


async def _notify_stream_event_observer(observer: Any, event: Mapping[str, Any]) -> bool:
    if not callable(observer):
        return False
    result = observer(dict(event))
    if inspect.isawaitable(result):
        await result
    return True


def _response_item_or_none(value: Any) -> ResponseItem | None:
    if isinstance(value, ResponseItem):
        return value
    if isinstance(value, Mapping):
        try:
            return ResponseItem.from_mapping(value)
        except Exception:
            return None
    return None


def _protocol_rate_limit_snapshot_or_none(value: Any) -> RateLimitSnapshot | None:
    if isinstance(value, RateLimitSnapshot):
        return value
    primary = _protocol_rate_limit_window_or_none(getattr(value, "primary", None))
    secondary = _protocol_rate_limit_window_or_none(getattr(value, "secondary", None))
    credits = _protocol_credits_snapshot_or_none(getattr(value, "credits", None))
    limit_id = getattr(value, "limit_id", None)
    limit_name = getattr(value, "limit_name", None)
    plan_type = getattr(value, "plan_type", None)
    reached_type = getattr(value, "rate_limit_reached_type", None)
    if not any(item is not None for item in (primary, secondary, credits, limit_id, limit_name, plan_type, reached_type)):
        return None
    return RateLimitSnapshot(
        limit_id=limit_id if isinstance(limit_id, str) else None,
        limit_name=limit_name if isinstance(limit_name, str) else None,
        primary=primary,
        secondary=secondary,
        credits=credits,
        plan_type=_parse_account_plan_type_or_none(plan_type),
        rate_limit_reached_type=_parse_rate_limit_reached_type_or_none(reached_type),
    )


def _protocol_rate_limit_window_or_none(value: Any) -> RateLimitWindow | None:
    if isinstance(value, RateLimitWindow):
        return value
    used_percent = getattr(value, "used_percent", None)
    if not isinstance(used_percent, int | float):
        return None
    window_minutes = getattr(value, "window_minutes", None)
    resets_at = getattr(value, "resets_at", None)
    return RateLimitWindow(
        used_percent=float(used_percent),
        window_minutes=window_minutes if isinstance(window_minutes, int) else None,
        resets_at=resets_at if isinstance(resets_at, int) else None,
    )


def _protocol_credits_snapshot_or_none(value: Any) -> CreditsSnapshot | None:
    if isinstance(value, CreditsSnapshot):
        return value
    has_credits = getattr(value, "has_credits", None)
    unlimited = getattr(value, "unlimited", None)
    if not isinstance(has_credits, bool) or not isinstance(unlimited, bool):
        return None
    balance = getattr(value, "balance", None)
    return CreditsSnapshot(
        has_credits=has_credits,
        unlimited=unlimited,
        balance=balance if isinstance(balance, str) else None,
    )


def _parse_account_plan_type_or_none(value: Any) -> AccountPlanType | None:
    if isinstance(value, AccountPlanType):
        return value
    if not isinstance(value, str):
        return None
    try:
        return AccountPlanType.parse(value)
    except ValueError:
        return None


def _parse_rate_limit_reached_type_or_none(value: Any) -> RateLimitReachedType | None:
    if isinstance(value, RateLimitReachedType):
        return value
    if not isinstance(value, str):
        return None
    try:
        return RateLimitReachedType.parse(value)
    except ValueError:
        return None


def _completed_response_id_from_stream_events(events: Sequence[Any]) -> str | None:
    for event in reversed(tuple(events)):
        if isinstance(event, Mapping) and event.get("type") == "completed":
            response_id = event.get("response_id")
            return response_id if isinstance(response_id, str) else None
    return None


def _api_error_is_upgrade_required(error: ApiError) -> bool:
    transport = error.transport if error.kind == "transport" else None
    return isinstance(transport, TransportError) and transport.kind == "http" and transport.status == 426


def _api_error_is_unauthorized(error: ApiError) -> bool:
    transport = error.transport if error.kind == "transport" else None
    return isinstance(transport, TransportError) and transport.kind == "http" and transport.status == 401


def _websocket_auth_for_config(config: HttpTransportConfig) -> Any:
    headers = dict(config.headers or {})
    auth_header = headers.get("Authorization") or headers.get("authorization")
    account_id = headers.get("ChatGPT-Account-ID") or headers.get("chatgpt-account-id")
    fedramp = (headers.get("X-OpenAI-Fedramp") or headers.get("x-openai-fedramp")) == "true"
    return {
        **({"Authorization": auth_header} if auth_header else {}),
        **({"ChatGPT-Account-ID": account_id} if account_id else {}),
        **({"X-OpenAI-Fedramp": "true"} if fedramp else {}),
    }


def _auth_headers_from_value(auth: Any) -> dict[str, str]:
    if auth is None:
        return {}
    if isinstance(auth, Mapping):
        if "Authorization" in auth or "authorization" in auth:
            return {str(key): str(value) for key, value in auth.items()}
        if "token" in auth:
            return {"Authorization": f"Bearer {auth['token']}"}
        return {str(key): str(value) for key, value in auth.items()}
    to_auth_headers = getattr(auth, "to_auth_headers", None)
    if callable(to_auth_headers):
        return {str(key): str(value) for key, value in dict(to_auth_headers() or {}).items()}
    add_auth_headers = getattr(auth, "add_auth_headers", None)
    if callable(add_auth_headers):
        headers: dict[str, str] = {}
        add_auth_headers(headers)
        return headers
    if isinstance(auth, str):
        return {"Authorization": f"Bearer {auth}"}
    return {}


async def _api_provider_from_model_provider(provider: Any) -> Any:
    api_provider = getattr(provider, "api_provider", None)
    if callable(api_provider):
        value = api_provider()
        return await value if inspect.isawaitable(value) else value
    return provider


def _codex_api_provider(value: Any) -> Any:
    if hasattr(value, "websocket_url_for_path"):
        return value
    base_url = getattr(value, "base_url", None)
    if base_url is None and isinstance(value, Mapping):
        base_url = value.get("base_url")
    if not isinstance(base_url, str) or not base_url:
        raise ApiError.stream("websocket provider missing base_url")
    headers = getattr(value, "headers", None)
    if headers is None and isinstance(value, Mapping):
        headers = value.get("headers")
    query_params = getattr(value, "query_params", None)
    if query_params is None and isinstance(value, Mapping):
        query_params = value.get("query_params")
    idle_ms = getattr(value, "stream_idle_timeout_ms", None)
    if idle_ms is None:
        idle_method = getattr(value, "stream_idle_timeout", None)
        if callable(idle_method):
            idle_ms = idle_method()
    idle_seconds = (float(idle_ms) / 1000.0) if idle_ms is not None else None
    return CodexApiProvider(
        name=str(getattr(value, "name", "OpenAI")),
        base_url=base_url,
        query_params=query_params,
        headers=dict(headers or {}),
        retry=RetryConfig(max_attempts=1, base_delay=0.0, retry_429=False, retry_5xx=False, retry_transport=False),
        stream_idle_timeout=idle_seconds,
    )


def _codex_err_is_unauthorized(error: CodexErr) -> bool:
    payload = getattr(error, "payload", None)
    return (
        getattr(error, "kind", None) == "unexpected_status"
        and isinstance(payload, UnexpectedResponseError)
        and payload.status == 401
    )


def http_sampling_stream_max_retries(provider: Any) -> int:
    """Return the Rust-shaped effective stream retry count for a provider."""

    configured = _provider_stream_max_retries(provider)
    if configured is None:
        return DEFAULT_STREAM_MAX_RETRIES
    if isinstance(configured, bool) or not isinstance(configured, int):
        raise TypeError("stream_max_retries must be an integer")
    if configured < 0:
        raise ValueError("stream_max_retries must be non-negative")
    return min(configured, MAX_STREAM_MAX_RETRIES)


def _provider_stream_max_retries(provider: Any) -> Any:
    info = _provider_info(provider)
    for source in (info, provider):
        if source is None:
            continue
        value = _stream_max_retries_value(source)
        if value is not None:
            return value
    return None


def _provider_info(provider: Any) -> Any:
    if isinstance(provider, Mapping):
        value = provider.get("info")
        return value() if callable(value) else value
    value = getattr(provider, "info", None)
    return value() if callable(value) else value


def _stream_max_retries_value(source: Any) -> Any:
    if isinstance(source, Mapping):
        value = source.get("stream_max_retries")
        return value() if callable(value) else value
    value = getattr(source, "stream_max_retries", None)
    return value() if callable(value) else value


def _http_sampling_retry_decision_callback(sess: Any, turn_context: Any, callback: Any):
    async def on_decision(decision: Any) -> None:
        await _emit_http_sampling_retry_decision(sess, turn_context, decision)
        if callback is not None:
            await _maybe_await(callback(decision))

    return on_decision


async def _emit_http_sampling_retry_decision(sess: Any, turn_context: Any, decision: Any) -> None:
    if sess is None or turn_context is None:
        return
    warning_message = getattr(decision, "warning_message", None)
    if isinstance(warning_message, str) and warning_message:
        await _send_session_event(sess, turn_context, EventMsg.with_payload("warning", WarningEvent(warning_message)))
    notify_message = getattr(decision, "notify_message", None)
    error = getattr(decision, "error", None)
    if isinstance(notify_message, str) and notify_message and isinstance(error, CodexErr):
        notifier = getattr(sess, "notify_stream_error", None)
        if callable(notifier):
            await _maybe_await(notifier(turn_context, notify_message, error))
            return
        await _send_session_event(
            sess,
            turn_context,
            EventMsg.with_payload(
                "stream_error",
                StreamErrorEvent(
                    message=notify_message,
                    codex_error_info=CodexErrorInfo.response_stream_disconnected(error.http_status_code_value()),
                    additional_details=str(error),
                ),
            ),
        )


async def _send_session_event(sess: Any, turn_context: Any, event: EventMsg) -> None:
    sender = getattr(sess, "send_event", None)
    if callable(sender):
        await _maybe_await(sender(turn_context, event))


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def run_user_turn_http_sampling_from_session(
    sess: Any,
    input: tuple[UserInput, ...] | list[UserInput],
    model_client: ModelClient,
    provider: Any,
    model_info: Any,
    *,
    auth: Any = None,
    endpoint: str | None = None,
    timeout: float | None = None,
    opener: Any = None,
    built_tools: BuiltToolsFn | None = None,
    effort: Any = None,
    summary: Any = None,
    service_tier: str | None = None,
    thread_settings: Any = None,
    responsesapi_client_metadata: Mapping[str, str] | None = None,
    additional_context: Mapping[str, Any] | None = None,
    environments: tuple[Any, ...] | list[Any] | None = None,
    turn_metadata_header: str | None = None,
    output_schema: Any = None,
    output_schema_strict: bool | None = None,
    max_tool_followups: int | None = None,
    sampling_max_retries: int | None = None,
    retry_sleep: Any = None,
    on_retry_decision: Any = None,
) -> UserTurnSamplingResult:
    """Run a user turn through the stdlib HTTP sampler path."""

    config = http_transport_config_from_provider(
        model_client,
        provider,
        auth=auth,
        endpoint=endpoint,
        timeout=timeout,
        turn_metadata_header=turn_metadata_header,
    )
    if sampling_max_retries is None:
        sampling_max_retries = http_sampling_stream_max_retries(provider)
    sampler = model_client_http_sampler(
        model_client.new_session(),
        config,
        opener=opener,
        max_retries=sampling_max_retries,
        sleep=retry_sleep,
        on_retry_decision=on_retry_decision,
    )
    return await run_user_turn_sampling_from_session(
        sess,
        input,
        model_client,
        provider,
        model_info,
        sampler,
        built_tools=built_tools,
        effort=effort,
        summary=summary,
        service_tier=service_tier,
        thread_settings=thread_settings,
        responsesapi_client_metadata=responsesapi_client_metadata,
        additional_context=additional_context,
        environments=environments,
        output_schema=output_schema,
        output_schema_strict=output_schema_strict,
        max_tool_followups=max_tool_followups,
        emit_user_prompt_turn_item=False,
        emit_response_item_turn_item=False,
    )


def response_items_from_responses_payload(payload: Any) -> tuple[ResponseItem, ...]:
    """Extract model output items from a Responses API-like payload."""

    if not isinstance(payload, Mapping):
        raise TypeError("response payload must be a mapping")
    output = payload.get("output")
    if output is None:
        output = payload.get("response_items")
    if output is None:
        return ()
    if isinstance(output, Mapping):
        output = (output,)
    if isinstance(output, (str, bytes)) or not isinstance(output, (list, tuple)):
        raise TypeError("response output must be an object or sequence")
    return tuple(item if isinstance(item, ResponseItem) else ResponseItem.from_mapping(item) for item in output)


__all__ = [
    "CODEX_EXEC_ORIGINATOR",
    "CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR",
    "HttpTransportConfig",
    "exec_originator_header_value",
    "http_sampling_stream_max_retries",
    "http_transport_config_from_provider",
    "model_client_http_sampler",
    "model_client_websocket_preferred_sampler",
    "prewarm_model_client_websocket_session",
    "prepare_request_body_for_transport",
    "response_items_from_responses_payload",
    "run_user_turn_http_sampling_from_session",
    "send_prepared_http_sampling_request",
]

