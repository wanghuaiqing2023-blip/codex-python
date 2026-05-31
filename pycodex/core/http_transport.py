"""Stdlib HTTP transport helpers for prepared sampling requests."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from urllib.parse import urljoin

from pycodex.core.client import ModelClient, ModelClientSession, RESPONSES_ENDPOINT, build_responses_headers, build_session_headers, insert_header_if_valid
from pycodex.core.turn_sampler import PreparedSamplingRequest, PreparedSamplingResult
from pycodex.core.turn_sampler import sample_with_model_client_session
from pycodex.core.turn_runtime import BuiltToolsFn, SamplerFn, UserTurnSamplingResult
from pycodex.core.turn_runtime import run_user_turn_sampling_from_session
from pycodex.protocol import UserInput
from pycodex.protocol import ResponseItem

CODEX_EXEC_ORIGINATOR = "codex_exec"
CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR = "CODEX_INTERNAL_ORIGINATOR_OVERRIDE"


@dataclass(frozen=True)
class HttpTransportConfig:
    """Configuration for a prepared Responses API HTTP request."""

    endpoint: str
    headers: Mapping[str, str] | None = None
    timeout: float | None = None


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
    headers = build_responses_headers(
        model_client.state.beta_features_header,
        None,
        turn_metadata_header,
    )
    insert_header_if_valid(headers, "x-codex-installation-id", str(model_client.state.installation_id))
    insert_header_if_valid(headers, "x-client-request-id", str(model_client.state.thread_id))
    headers.update(build_session_headers(str(model_client.state.session_id), str(model_client.state.thread_id)))
    headers.update(model_client.build_responses_identity_headers())
    if model_client.state.include_timing_metrics:
        insert_header_if_valid(headers, "x-responsesapi-include-timing-metrics", "true")
    headers.update(_auth_headers_from_value(auth if auth is not None else getattr(provider, "auth", None)))
    insert_header_if_valid(headers, "Originator", exec_originator_header_value())
    return HttpTransportConfig(resolved_endpoint, headers=headers, timeout=timeout)


def send_prepared_http_sampling_request(
    prepared: PreparedSamplingRequest,
    config: HttpTransportConfig,
    *,
    opener: Any = None,
) -> PreparedSamplingResult:
    """Send a prepared sampling request with the Python standard library."""

    json_request = _to_json_compatible(prepared.prepared_request)
    body = json.dumps(json_request, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {"Content-Type": "application/json", **dict(config.headers or {})}
    request = Request(config.endpoint, data=body, headers=headers, method="POST")
    open_fn = urlopen if opener is None else opener
    try:
        response = open_fn(request, timeout=config.timeout) if config.timeout is not None else open_fn(request)
    except HTTPError as exc:
        raise RuntimeError(_http_error_message(exc)) from exc
    except URLError as exc:
        reason = getattr(exc, "reason", exc)
        raise RuntimeError(f"Responses API request failed: {reason}") from exc
    with response:
        payload = response.read()
    decoded = json.loads(payload.decode("utf-8"))
    response_items = response_items_from_responses_payload(decoded)
    return PreparedSamplingResult(
        prepared_request=prepared.prepared_request,
        response_items=response_items,
        raw_result=decoded,
        mode=prepared.mode,
    )


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


def _auth_headers_from_value(auth: Any) -> dict[str, str]:
    if auth is None:
        return {}
    if isinstance(auth, str):
        return {"Authorization": f"Bearer {auth}"}
    if isinstance(auth, Mapping):
        if "headers" in auth:
            return {str(key): str(value) for key, value in dict(auth.get("headers") or {}).items()}
        if "api_key" in auth:
            return {"Authorization": f"Bearer {auth['api_key']}"}
        if "bearer_token" in auth:
            return {"Authorization": f"Bearer {auth['bearer_token']}"}
        return {str(key): str(value) for key, value in auth.items()}
    to_auth_headers = getattr(auth, "to_auth_headers", None)
    if callable(to_auth_headers):
        return {str(key): str(value) for key, value in dict(to_auth_headers() or {}).items()}
    add_auth_headers = getattr(auth, "add_auth_headers", None)
    if callable(add_auth_headers):
        headers: dict[str, str] = {}
        add_auth_headers(headers)
        return {str(key): str(value) for key, value in headers.items()}
    api_key = getattr(auth, "api_key", None) or getattr(auth, "openai_api_key", None)
    if isinstance(api_key, str) and api_key:
        return {"Authorization": f"Bearer {api_key}"}
    bearer_token = getattr(auth, "bearer_token", None) or getattr(auth, "access_token", None)
    if isinstance(bearer_token, str) and bearer_token:
        return {"Authorization": f"Bearer {bearer_token}"}
    headers = getattr(auth, "headers", None)
    if headers is not None:
        return {str(key): str(value) for key, value in dict(headers or {}).items()}
    return {}


def exec_originator_header_value(env: Mapping[str, str] | None = None) -> str:
    source = os.environ if env is None else env
    override = source.get(CODEX_INTERNAL_ORIGINATOR_OVERRIDE_ENV_VAR)
    return override if override else CODEX_EXEC_ORIGINATOR


def model_client_http_sampler(
    model_session: ModelClientSession,
    config: HttpTransportConfig,
    *,
    opener: Any = None,
) -> SamplerFn:
    """Create a sampler using ``ModelClientSession`` plus stdlib HTTP."""

    async def sampler(sampling_request):
        return await sample_with_model_client_session(
            sampling_request,
            model_session,
            lambda prepared: send_prepared_http_sampling_request(prepared, config, opener=opener),
        )

    return sampler


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
    output_schema_strict: bool = True,
    max_tool_followups: int = 8,
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
    sampler = model_client_http_sampler(model_client.new_session(), config, opener=opener)
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
    "http_transport_config_from_provider",
    "model_client_http_sampler",
    "response_items_from_responses_payload",
    "run_user_turn_http_sampling_from_session",
    "send_prepared_http_sampling_request",
]
