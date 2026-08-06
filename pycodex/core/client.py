"""Session-scoped model client helpers ported from ``core/src/client.rs``.

The Rust client owns real HTTP/WebSocket transports.  This Python port keeps the
transport-independent state machine and request/header construction logic:
window generation, prompt-cache keys, websocket fallback/cache state, turn-state
headers, sub-agent identity headers, and incremental websocket request deltas.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field, replace
from inspect import isawaitable, iscoroutinefunction
from enum import Enum
from typing import Any, Callable, Mapping, MutableMapping, Sequence

from pycodex.core.attestation import (
    AttestationContext,
    generate_attestation_header_for_request,
    normalize_attestation_header_value,
    X_OAI_ATTESTATION_HEADER,
)
from pycodex.core.client_common import Prompt
from pycodex.core.event_mapping import parse_turn_item
from pycodex.codex_api.endpoint.responses import response_items_from_responses_payload
from pycodex.protocol import (
    AgentMessageContent,
    AgentMessageItem,
    ContentItem,
    InternalSessionSource,
    PlanItem,
    ResponseItem,
    ServiceTier,
    SessionSource,
    SubAgentSource,
    ThreadId,
    TurnItem,
)


OPENAI_BETA_HEADER = "OpenAI-Beta"
X_CODEX_INSTALLATION_ID_HEADER = "x-codex-installation-id"
X_CODEX_TURN_STATE_HEADER = "x-codex-turn-state"
X_CODEX_TURN_METADATA_HEADER = "x-codex-turn-metadata"
X_CODEX_PARENT_THREAD_ID_HEADER = "x-codex-parent-thread-id"
X_CODEX_WINDOW_ID_HEADER = "x-codex-window-id"
X_OPENAI_MEMGEN_REQUEST_HEADER = "x-openai-memgen-request"
X_OPENAI_SUBAGENT_HEADER = "x-openai-subagent"
X_RESPONSESAPI_INCLUDE_TIMING_METRICS_HEADER = "x-responsesapi-include-timing-metrics"
X_CODEX_WS_STREAM_REQUEST_START_MS_CLIENT_METADATA_KEY = "x-codex-ws-stream-request-start-ms"
WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY = "ws_request_header_traceparent"
WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY = "ws_request_header_tracestate"
RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE = "responses_websockets=2026-02-06"
RESPONSES_ENDPOINT = "/responses"
RESPONSES_COMPACT_ENDPOINT = "/responses/compact"
COMPACT_REQUEST_TIMEOUT_IDLE_MULTIPLIER = 4
MEMORIES_SUMMARIZE_ENDPOINT = "/memories/trace_summarize"
RESPONSE_STREAM_CHANNEL_CAPACITY = 1600
STREAM_DROPPED_REASON = "response stream dropped before provider terminal event"


def auth_headers_from_value(auth: Any) -> dict[str, str]:
    if auth is None:
        return {}
    if isinstance(auth, str):
        return {"Authorization": f"Bearer {auth}"}
    if isinstance(auth, Mapping):
        if "headers" in auth:
            headers = auth.get("headers")
            if isinstance(headers, Mapping):
                return {str(key): str(value) for key, value in headers.items()}
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



def sideband_websocket_auth_headers(api_auth: Any) -> dict[str, str]:
    """Build sideband WebSocket auth headers from the API auth material.

    Mirrors Rust `sideband_websocket_auth_headers`: API-key sessions send the
    bearer API key, while ChatGPT-auth style providers can contribute their
    bearer/account headers through the same auth-header protocol used by normal
    requests.
    """
    return auth_headers_from_value(api_auth)

@dataclass(frozen=True, slots=True)
class CompactConversationRequestSettings:
    effort: Any = None
    summary: Any = None
    service_tier: str | None = None


@dataclass(frozen=True, slots=True)
class RequestRouteTelemetry:
    endpoint: str

    @classmethod
    def for_endpoint(cls, endpoint: str) -> "RequestRouteTelemetry":
        return cls(endpoint)


@dataclass(frozen=True, slots=True)
class LastResponse:
    response_id: str
    items_added: tuple[ResponseItem, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.response_id, str):
            raise TypeError("response_id must be a string")
        object.__setattr__(self, "items_added", tuple(self.items_added))


@dataclass(slots=True)
class TurnState:
    """OnceLock-like holder for ``x-codex-turn-state``."""

    value: str | None = None

    def set(self, value: str) -> bool:
        if not isinstance(value, str):
            raise TypeError("turn state must be a string")
        if self.value is not None:
            return False
        self.value = value
        return True

    def get(self) -> str | None:
        return self.value


@dataclass(slots=True)
class WebsocketSession:
    connection: Any = None
    last_request: Mapping[str, Any] | None = None
    last_response: LastResponse | None = None
    last_response_pending: bool = False
    last_response_from_untraced_warmup: bool = False
    _connection_reused: bool = False

    def set_connection_reused(self, connection_reused: bool) -> None:
        if not isinstance(connection_reused, bool):
            raise TypeError("connection_reused must be a bool")
        self._connection_reused = connection_reused

    def connection_reused(self) -> bool:
        return self._connection_reused

    def reset(self) -> None:
        self.close()
        self.connection = None
        self.last_request = None
        self.last_response = None
        self.last_response_pending = False
        self.last_response_from_untraced_warmup = False
        self.set_connection_reused(False)

    def close(self) -> None:
        connection = self.connection
        if connection is None:
            return
        closer = getattr(connection, "close", None)
        if callable(closer):
            result = closer()
            if isawaitable(result):
                try:
                    result.close()
                except Exception:
                    pass


class WebsocketStreamOutcome(str, Enum):
    STREAM = "stream"
    FALLBACK_TO_HTTP = "fallback_to_http"


@dataclass(frozen=True, slots=True)
class RealtimeWebrtcCallStart:
    sdp: str
    call_id: str
    sideband_headers: Mapping[str, str]


@dataclass(frozen=True, slots=True)
class CurrentClientSetup:
    auth: Any = None
    api_provider: Any = None
    api_auth: Any = None


@dataclass(slots=True)
class ModelClientState:
    session_id: Any
    thread_id: Any
    installation_id: str
    provider: Any = None
    auth_env_telemetry: Any = None
    session_source: SessionSource = field(default_factory=SessionSource.default)
    model_verbosity: Any = None
    enable_request_compression: bool = False
    include_timing_metrics: bool = False
    beta_features_header: str | None = None
    include_attestation: bool = False
    attestation_provider: Any = None
    disable_websockets: bool = False
    window_generation: int = 0
    cached_websocket_session: WebsocketSession = field(default_factory=WebsocketSession)
    last_request_diagnostics: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.installation_id, str):
            raise TypeError("installation_id must be a string")
        if not isinstance(self.enable_request_compression, bool):
            raise TypeError("enable_request_compression must be a bool")
        if not isinstance(self.include_timing_metrics, bool):
            raise TypeError("include_timing_metrics must be a bool")
        if self.beta_features_header is not None and not isinstance(self.beta_features_header, str):
            raise TypeError("beta_features_header must be a string or None")
        if not isinstance(self.include_attestation, bool):
            raise TypeError("include_attestation must be a bool")
        if not isinstance(self.disable_websockets, bool):
            raise TypeError("disable_websockets must be a bool")
        if isinstance(self.window_generation, bool) or not isinstance(self.window_generation, int):
            raise TypeError("window_generation must be an int")
        if not isinstance(self.last_request_diagnostics, dict):
            raise TypeError("last_request_diagnostics must be a dict")
        if self.window_generation < 0:
            raise ValueError("window_generation must be non-negative")
        if not isinstance(self.cached_websocket_session, WebsocketSession):
            raise TypeError("cached_websocket_session must be WebsocketSession")


class ModelClient:
    """Session-scoped state for model-provider API calls."""

    def __init__(
        self,
        *,
        session_id: Any,
        thread_id: Any,
        installation_id: str,
        provider: Any = None,
        session_source: SessionSource | None = None,
        model_verbosity: Any = None,
        enable_request_compression: bool = False,
        include_timing_metrics: bool = False,
        beta_features_header: str | None = None,
        attestation_provider: Any = None,
        prompt_cache_key_override: str | None = None,
    ) -> None:
        include_attestation = bool(getattr(provider, "supports_attestation", lambda: False)())
        self.state = ModelClientState(
            session_id=session_id,
            thread_id=thread_id,
            installation_id=installation_id,
            provider=provider,
            session_source=session_source or SessionSource.default(),
            model_verbosity=model_verbosity,
            enable_request_compression=enable_request_compression,
            include_timing_metrics=include_timing_metrics,
            beta_features_header=beta_features_header,
            include_attestation=include_attestation,
            attestation_provider=attestation_provider,
        )
        self.prompt_cache_key_override = prompt_cache_key_override

    def with_prompt_cache_key_override(self, prompt_cache_key_override: str | None) -> "ModelClient":
        if prompt_cache_key_override is not None and not isinstance(prompt_cache_key_override, str):
            raise TypeError("prompt_cache_key_override must be a string or None")
        self.prompt_cache_key_override = prompt_cache_key_override
        return self

    def prompt_cache_key(self) -> str:
        if self.prompt_cache_key_override is not None:
            return self.prompt_cache_key_override
        return str(self.state.thread_id)

    def new_session(self) -> "ModelClientSession":
        return ModelClientSession(
            client=self,
            websocket_session=self.take_cached_websocket_session(),
            turn_state=TurnState(),
        )

    def auth_manager(self) -> Any:
        auth_manager = getattr(self.state.provider, "auth_manager", None)
        return auth_manager() if callable(auth_manager) else auth_manager

    def set_window_generation(self, window_generation: int) -> None:
        if isinstance(window_generation, bool) or not isinstance(window_generation, int) or window_generation < 0:
            raise ValueError("window_generation must be a non-negative integer")
        self.state.window_generation = window_generation
        self.close_cached_websocket_session()

    def advance_window_generation(self) -> None:
        self.state.window_generation += 1
        self.close_cached_websocket_session()

    def current_window_id(self) -> str:
        return f"{self.state.thread_id}:{self.state.window_generation}"

    def take_cached_websocket_session(self) -> WebsocketSession:
        session = self.state.cached_websocket_session
        self.state.cached_websocket_session = WebsocketSession()
        return session

    def store_cached_websocket_session(self, websocket_session: WebsocketSession) -> None:
        if not isinstance(websocket_session, WebsocketSession):
            raise TypeError("websocket_session must be WebsocketSession")
        self.state.cached_websocket_session = websocket_session

    def close_cached_websocket_session(self) -> None:
        self.state.cached_websocket_session.reset()
        self.state.cached_websocket_session = WebsocketSession()

    def responses_websocket_enabled(self) -> bool:
        provider_info = _provider_info(self.state.provider)
        supports = _provider_supports_websockets(provider_info)
        return supports and not self.state.disable_websockets

    async def current_client_setup(self) -> CurrentClientSetup:
        provider = self.state.provider
        return CurrentClientSetup(
            auth=await _call_provider_hook(provider, "auth"),
            api_provider=await _call_provider_hook(provider, "api_provider"),
            api_auth=await _call_provider_hook(provider, "api_auth"),
        )

    def force_http_fallback(self, session_telemetry: Any = None, model_info: Any = None) -> bool:
        activated = self.responses_websocket_enabled() and not self.state.disable_websockets
        if activated:
            counter = getattr(session_telemetry, "counter", None)
            if callable(counter):
                counter("codex.transport.fallback_to_http", 1, (("from_wire_api", "responses_websocket"),))
            self.state.disable_websockets = True
            self.close_cached_websocket_session()
        return activated

    def build_subagent_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        subagent = subagent_header_value(self.state.session_source)
        insert_header_if_valid(headers, X_OPENAI_SUBAGENT_HEADER, subagent)
        if (
            self.state.session_source.type == "internal"
            and self.state.session_source.internal_source == InternalSessionSource.MEMORY_CONSOLIDATION
        ):
            insert_header_if_valid(headers, X_OPENAI_MEMGEN_REQUEST_HEADER, "true")
        return headers

    def build_responses_identity_headers(self) -> dict[str, str]:
        headers = self.build_subagent_headers()
        parent_thread_id = parent_thread_id_header_value(self.state.session_source)
        insert_header_if_valid(headers, X_CODEX_PARENT_THREAD_ID_HEADER, parent_thread_id)
        insert_header_if_valid(headers, X_CODEX_WINDOW_ID_HEADER, self.current_window_id())
        return headers

    def build_ws_client_metadata(self, turn_metadata_header: str | None = None) -> dict[str, str]:
        metadata = {
            X_CODEX_INSTALLATION_ID_HEADER: self.state.installation_id,
            X_CODEX_WINDOW_ID_HEADER: self.current_window_id(),
        }
        subagent = subagent_header_value(self.state.session_source)
        if subagent is not None:
            metadata[X_OPENAI_SUBAGENT_HEADER] = subagent
        parent_thread_id = parent_thread_id_header_value(self.state.session_source)
        if parent_thread_id is not None:
            metadata[X_CODEX_PARENT_THREAD_ID_HEADER] = parent_thread_id
        parsed_turn_metadata = parse_turn_metadata_header(turn_metadata_header)
        if parsed_turn_metadata is not None:
            metadata[X_CODEX_TURN_METADATA_HEADER] = parsed_turn_metadata
        return metadata

    def build_websocket_payload(
        self,
        request: Mapping[str, Any],
        trace: Any | None = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(request, Mapping):
            raise TypeError("request must be a mapping")
        payload = dict(request)
        payload["client_metadata"] = response_create_client_metadata(
            self.build_ws_client_metadata(turn_metadata_header),
            trace,
        )
        return payload

    def _build_websocket_headers_base(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, str]:
        headers = build_responses_headers(
            self.state.beta_features_header,
            turn_state,
            parse_turn_metadata_header(turn_metadata_header),
        )
        insert_header_if_valid(headers, "x-client-request-id", str(self.state.thread_id))
        insert_header_if_valid(headers, X_CODEX_INSTALLATION_ID_HEADER, str(self.state.installation_id))
        headers.update(build_session_headers(str(self.state.session_id), str(self.state.thread_id)))
        headers.update(self.build_responses_identity_headers())
        insert_header_if_valid(headers, OPENAI_BETA_HEADER, RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE)
        if self.state.include_timing_metrics:
            insert_header_if_valid(headers, X_RESPONSESAPI_INCLUDE_TIMING_METRICS_HEADER, "true")
        return headers

    def _build_compact_headers_base(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, str]:
        headers = build_responses_headers(
            self.state.beta_features_header,
            turn_state,
            parse_turn_metadata_header(turn_metadata_header),
        )
        insert_header_if_valid(headers, X_CODEX_INSTALLATION_ID_HEADER, str(self.state.installation_id))
        headers.update(build_session_headers(str(self.state.session_id), str(self.state.thread_id)))
        headers.update(self.build_responses_identity_headers())
        return headers

    def build_auth_headers(self, auth: Any | None = None) -> dict[str, str]:
        provider_auth = getattr(self.state.provider, "auth", None)
        return auth_headers_from_value(auth if auth is not None else provider_auth)

    async def build_compact_request_headers_async(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
        auth: Any | None = None,
    ) -> dict[str, str]:
        headers = self._build_compact_headers_base(turn_state, turn_metadata_header)
        headers.update(self.build_auth_headers(auth=auth))
        thread_id = self._coerce_thread_id_for_attestation(self.state.thread_id)
        if thread_id is None:
            return headers

        attestation_header = await generate_attestation_header_for_request(
            include_attestation=self.state.include_attestation,
            attestation_provider=self.state.attestation_provider,
            thread_id=thread_id,
        )
        insert_header_if_valid(headers, X_OAI_ATTESTATION_HEADER, attestation_header)
        return headers

    def build_compact_request_headers(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
        auth: Any | None = None,
    ) -> dict[str, str]:
        if self.state.attestation_provider is not None and self.state.include_attestation:
            header_for_request = getattr(self.state.attestation_provider, "header_for_request", None)
            if callable(header_for_request):
                try:
                    loop_running = asyncio.get_running_loop()
                except RuntimeError:
                    loop_running = None
                if loop_running is None:
                    return asyncio.run(
                        self.build_compact_request_headers_async(
                            turn_state=turn_state,
                            turn_metadata_header=turn_metadata_header,
                            auth=auth,
                        )
                    )
                thread_id = self._coerce_thread_id_for_attestation(self.state.thread_id)
                if thread_id is None:
                    headers = self._build_compact_headers_base(turn_state, turn_metadata_header)
                    headers.update(self.build_auth_headers(auth=auth))
                    return headers
                result = header_for_request(AttestationContext(thread_id=thread_id))
                if isawaitable(result):
                    headers = self._build_compact_headers_base(turn_state, turn_metadata_header)
                    headers.update(self.build_auth_headers(auth=auth))
                    return headers
                headers = self._build_compact_headers_base(turn_state, turn_metadata_header)
                headers.update(self.build_auth_headers(auth=auth))
                insert_header_if_valid(
                    headers,
                    X_OAI_ATTESTATION_HEADER,
                    normalize_attestation_header_value(result),
                )
                return headers
        headers = self._build_compact_headers_base(turn_state, turn_metadata_header)
        headers.update(self.build_auth_headers(auth=auth))
        return headers

    @staticmethod
    def _coerce_thread_id_for_attestation(thread_id: Any) -> ThreadId | None:
        if isinstance(thread_id, ThreadId):
            return thread_id
        if isinstance(thread_id, str):
            try:
                return ThreadId.from_string(thread_id)
            except Exception:
                return None
        return None

    async def build_websocket_headers_async(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, str]:
        headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
        thread_id = self._coerce_thread_id_for_attestation(self.state.thread_id)
        if thread_id is None:
            return headers

        attestation_header = await generate_attestation_header_for_request(
            include_attestation=self.state.include_attestation,
            attestation_provider=self.state.attestation_provider,
            thread_id=thread_id,
        )
        insert_header_if_valid(headers, X_OAI_ATTESTATION_HEADER, attestation_header)
        return headers

    def build_websocket_headers(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, str]:
        if self.state.attestation_provider is not None and self.state.include_attestation:
            header_for_request = getattr(self.state.attestation_provider, "header_for_request", None)
            if callable(header_for_request):
                try:
                    loop_running = asyncio.get_running_loop()
                except RuntimeError:
                    loop_running = None
                if loop_running is None:
                    return asyncio.run(
                        self.build_websocket_headers_async(
                            turn_state=turn_state,
                            turn_metadata_header=turn_metadata_header,
                        )
                    )
                if iscoroutinefunction(header_for_request):
                    return self._build_websocket_headers_base(turn_state, turn_metadata_header)
                thread_id = self._coerce_thread_id_for_attestation(self.state.thread_id)
                if thread_id is None:
                    return self._build_websocket_headers_base(turn_state, turn_metadata_header)
                result = header_for_request(AttestationContext(thread_id=thread_id))
                if isawaitable(result):
                    # Can't block here from an active loop; keep behavior safe by omitting attestation.
                    if hasattr(result, "aclose"):
                        result.aclose()
                    elif hasattr(result, "close"):
                        result.close()
                    return self._build_websocket_headers_base(turn_state, turn_metadata_header)
                headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
                insert_header_if_valid(
                    headers,
                    X_OAI_ATTESTATION_HEADER,
                    normalize_attestation_header_value(result),
                )
                return headers
        return self._build_websocket_headers_base(turn_state, turn_metadata_header)

    async def build_realtime_call_headers_async(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
        auth: Any | None = None,
    ) -> dict[str, str]:
        headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
        headers.update(self.build_auth_headers(auth=auth))
        thread_id = self._coerce_thread_id_for_attestation(self.state.thread_id)
        if thread_id is None:
            return headers

        attestation_header = await generate_attestation_header_for_request(
            include_attestation=self.state.include_attestation,
            attestation_provider=self.state.attestation_provider,
            thread_id=thread_id,
        )
        insert_header_if_valid(headers, X_OAI_ATTESTATION_HEADER, attestation_header)
        return headers

    def build_realtime_call_headers(
        self,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
        auth: Any | None = None,
    ) -> dict[str, str]:
        if self.state.attestation_provider is not None and self.state.include_attestation:
            header_for_request = getattr(self.state.attestation_provider, "header_for_request", None)
            if callable(header_for_request):
                try:
                    loop_running = asyncio.get_running_loop()
                except RuntimeError:
                    loop_running = None
                if loop_running is None:
                    return asyncio.run(
                        self.build_realtime_call_headers_async(
                            turn_state=turn_state,
                            turn_metadata_header=turn_metadata_header,
                            auth=auth,
                        )
                    )
                thread_id = self._coerce_thread_id_for_attestation(self.state.thread_id)
                if thread_id is None:
                    headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
                    headers.update(self.build_auth_headers(auth=auth))
                    return headers
                result = header_for_request(AttestationContext(thread_id=thread_id))
                if isawaitable(result):
                    headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
                    headers.update(self.build_auth_headers(auth=auth))
                    return headers
                headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
                headers.update(self.build_auth_headers(auth=auth))
                insert_header_if_valid(
                    headers,
                    X_OAI_ATTESTATION_HEADER,
                    normalize_attestation_header_value(result),
                )
                return headers
        headers = self._build_websocket_headers_base(turn_state, turn_metadata_header)
        headers.update(self.build_auth_headers(auth=auth))
        return headers

    def build_realtime_call_sideband_headers(
        self,
        api_auth: Any,
        *,
        turn_state: TurnState | None = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, str]:
        headers = self.build_realtime_call_headers(
            turn_state=turn_state,
            turn_metadata_header=turn_metadata_header,
            auth=api_auth,
        )
        headers.update(sideband_websocket_auth_headers(api_auth))
        return headers

    def build_responses_request(
        self,
        provider: Any,
        prompt: Prompt,
        model_info: Any,
        effort: Any = None,
        summary: Any = None,
        service_tier: str | None = None,
    ) -> dict[str, Any]:
        model_slug = getattr(model_info, "slug", str(model_info))
        request_service_tier = _service_tier_for_request(model_info, service_tier)
        reasoning = build_reasoning(model_info, effort, summary)
        verbosity = None
        self.state.last_request_diagnostics = {}
        if getattr(model_info, "support_verbosity", False):
            verbosity = self.state.model_verbosity
            if verbosity is None:
                verbosity = getattr(model_info, "default_verbosity", None)
        elif self.state.model_verbosity is not None:
            self.state.last_request_diagnostics["model_verbosity_ignored"] = {
                "model": model_slug,
                "verbosity": self.state.model_verbosity,
                "reason": "model does not support verbosity",
            }
        return {
            "model": model_slug,
            "instructions": prompt.base_instructions.text,
            "input": prompt.get_formatted_input(),
            "tools": create_tools_json_for_responses_api(prompt.tools),
            "tool_choice": "auto",
            "parallel_tool_calls": prompt.parallel_tool_calls,
            "reasoning": reasoning,
            "store": bool(getattr(provider, "is_azure_responses_endpoint", lambda: False)()),
            "stream": True,
            "include": ["reasoning.encrypted_content"] if reasoning is not None else [],
            "service_tier": request_service_tier,
            "prompt_cache_key": self.prompt_cache_key(),
            "text": create_text_param_for_request(verbosity, prompt.output_schema, prompt.output_schema_strict),
            "client_metadata": {X_CODEX_INSTALLATION_ID_HEADER: self.state.installation_id},
        }


@dataclass(slots=True)
class ModelClientSession:
    client: ModelClient
    websocket_session: WebsocketSession
    turn_state: TurnState = field(default_factory=TurnState)

    def reset_websocket_session(self) -> None:
        self.websocket_session.reset()

    def force_http_fallback(self, session_telemetry: Any = None, model_info: Any = None) -> bool:
        activated = self.client.force_http_fallback(
            session_telemetry=session_telemetry,
            model_info=model_info,
        )
        self.reset_websocket_session()
        return activated

    async def send_response_processed(self, response_id: str) -> Any:
        if not isinstance(response_id, str):
            raise TypeError("response_id must be a string")
        connection = self.websocket_session.connection
        if connection is None:
            return None
        sender = getattr(connection, "send_response_processed", None)
        if not callable(sender):
            return None
        result = sender(response_id)
        return await result if isawaitable(result) else result

    def close(self) -> None:
        self.client.store_cached_websocket_session(self.websocket_session)
        self.websocket_session = WebsocketSession()

    def websocket_connection_needs_new(self) -> bool:
        connection = self.websocket_session.connection
        if connection is None:
            return True
        is_closed = getattr(connection, "is_closed", None)
        if callable(is_closed):
            return bool(is_closed())
        if is_closed is not None:
            return bool(is_closed)
        return False

    def preconnect_websocket(self, connection: Any = None) -> dict[str, Any]:
        if not self.client.responses_websocket_enabled():
            return {"preconnected": False, "reason": "websocket_disabled"}
        if self.websocket_session.connection is not None:
            return {
                "preconnected": False,
                "reason": "connection_already_present",
                "connection_reused": self.websocket_session.connection_reused(),
            }
        if connection is None:
            return {"preconnected": False, "reason": "missing_connection"}
        self.websocket_session.connection = connection
        self.websocket_session.set_connection_reused(False)
        return {"preconnected": True, "connection_reused": False}

    async def preconnect_websocket_with_connector(
        self,
        connector: Any,
        *,
        session_telemetry: Any = None,
        model_info: Any = None,
        turn_metadata_header: str | None = None,
    ) -> dict[str, Any]:
        """Rust ``ModelClientSession::preconnect_websocket`` outer boundary.

        The concrete WebSocket transport is injected as ``connector``. It may
        be a callable accepting keyword arguments, or an object exposing
        ``connect_websocket``. The returned connection is installed through the
        existing ``preconnect_websocket`` helper so disabled/already-connected
        semantics stay in one place.
        """

        if not self.client.responses_websocket_enabled():
            return {"preconnected": False, "reason": "websocket_disabled"}
        if self.websocket_session.connection is not None:
            return {
                "preconnected": False,
                "reason": "connection_already_present",
                "connection_reused": self.websocket_session.connection_reused(),
            }
        setup = await self.client.current_client_setup()
        connect = connector if callable(connector) else getattr(connector, "connect_websocket", None)
        if not callable(connect):
            raise TypeError("connector must be callable or expose connect_websocket")
        connection = connect(
            session_telemetry=session_telemetry,
            model_info=model_info,
            api_provider=setup.api_provider,
            api_auth=setup.api_auth,
            turn_state=self.turn_state,
            turn_metadata_header=turn_metadata_header,
        )
        if isawaitable(connection):
            connection = await connection
        return self.preconnect_websocket(connection)

    def prewarm_websocket(
        self,
        features: Any,
        *,
        payload: Mapping[str, Any],
        request: Mapping[str, Any],
        event_apply_plans: Sequence[Any],
        connection: Any = None,
        session_telemetry: Any = None,
        model_info: Any = None,
        trace: Any | None = None,
        turn_metadata_header: str | None = None,
        outcome_ok: bool = True,
        cancellation_requested: bool = False,
        unified_diff: str | None = None,
        websocket_outcome: WebsocketStreamOutcome = WebsocketStreamOutcome.STREAM,
        **hook_overrides: Any,
    ) -> dict[str, Any]:
        if not self.client.responses_websocket_enabled():
            return {"prewarmed": False, "reason": "websocket_disabled"}
        if self.websocket_session.last_request is not None:
            return {"prewarmed": False, "reason": "last_request_present"}
        preconnect_result = None
        if connection is not None:
            preconnect_result = self.preconnect_websocket(connection)
        warmup_payload = dict(payload)
        warmup_payload["generate"] = False
        warmup_request = dict(request)
        result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
            self,
            features,
            payload=warmup_payload,
            request=warmup_request,
            event_apply_plans=event_apply_plans,
            outcome_ok=outcome_ok,
            cancellation_requested=cancellation_requested,
            unified_diff=unified_diff,
            session_telemetry=session_telemetry,
            model_info=model_info,
            warmup=True,
            trace=trace,
            turn_metadata_header=turn_metadata_header,
            websocket_outcome=websocket_outcome,
            **hook_overrides,
        )
        completed = (
            result.websocket_outcome == WebsocketStreamOutcome.STREAM
            and result.runtime_state_summary is not None
            and result.runtime_state_summary.get("completed_response_id") is not None
        )
        reason = (
            "completed"
            if completed
            else "fallback_to_http"
            if result.websocket_outcome == WebsocketStreamOutcome.FALLBACK_TO_HTTP
            else "stream_failed"
            if result.websocket_stream_result is not None
            and result.websocket_stream_result.get("status") == "failed"
            else "stream_cancelled"
            if result.websocket_stream_result is not None
            and result.websocket_stream_result.get("status") == "cancelled"
            else "missing_completed"
        )
        return {
            "prewarmed": completed,
            "reason": reason,
            "preconnect": preconnect_result,
            "result": result,
        }

    def apply_websocket_connection_lifecycle(self, needs_new: bool, connection: Any = None) -> dict[str, bool]:
        if not isinstance(needs_new, bool):
            raise TypeError("needs_new must be a bool")
        if needs_new:
            self.websocket_session.last_request = None
            self.websocket_session.last_response = None
            self.websocket_session.last_response_pending = False
            self.websocket_session.last_response_from_untraced_warmup = False
            self.websocket_session.connection = connection
            self.websocket_session.set_connection_reused(False)
            return {
                "needs_new": True,
                "connection_reused": False,
                "incremental_state_reset": True,
            }
        self.websocket_session.set_connection_reused(True)
        return {
            "needs_new": False,
            "connection_reused": True,
            "incremental_state_reset": False,
        }

    def sampling_request_runtime_hook_adapter(
        self,
        state: Any | None = None,
        **hook_overrides: Any,
    ) -> Any:
        if state is None:
            state = SamplingRuntimeEventApplicationState()
        if not isinstance(state, SamplingRuntimeEventApplicationState):
            raise TypeError("state must be a SamplingRuntimeEventApplicationState or None")
        return SamplingRequestRuntimeHookAdapter(
            websocket_session=self.websocket_session,
            event_application_state=state,
            **hook_overrides,
        )

    def get_incremental_items(
        self,
        request: Mapping[str, Any],
        last_response: LastResponse | None,
        allow_empty_delta: bool,
    ) -> list[ResponseItem] | None:
        previous_request = self.websocket_session.last_request
        if previous_request is None:
            return None

        previous_without_input = dict(previous_request)
        request_without_input = dict(request)
        previous_input = list(previous_without_input.pop("input", ()))
        request_input = list(request_without_input.pop("input", ()))
        if previous_without_input != request_without_input:
            return None

        baseline = list(previous_input)
        if last_response is not None:
            baseline.extend(last_response.items_added)
        if _starts_with(request_input, baseline) and (allow_empty_delta or len(baseline) < len(request_input)):
            return request_input[len(baseline) :]
        return None

    def get_last_response(self) -> LastResponse | None:
        response = self.websocket_session.last_response
        self.websocket_session.last_response = None
        self.websocket_session.last_response_pending = False
        return response

    def prepare_websocket_request(
        self,
        payload: Mapping[str, Any],
        request: Mapping[str, Any],
    ) -> tuple[dict[str, Any], bool]:
        last_response = self.get_last_response()
        serialized_payload = serialize_responses_request(payload)
        if last_response is None:
            return response_create_ws_request(serialized_payload), False
        incremental_items = self.get_incremental_items(request, last_response, allow_empty_delta=True)
        if incremental_items is None or not last_response.response_id:
            return response_create_ws_request(serialized_payload), False
        prepared = dict(serialized_payload)
        prepared["previous_response_id"] = last_response.response_id
        # Fixed Rust baseline 1c7832f constructs ResponseCreateWsRequest with
        # typed items and serde serializes both full and incremental requests
        # at the same transport boundary. Python returns the wire mapping here,
        # so the incremental slice must pass through the same serializer.
        prepared["input"] = serialize_responses_request({"input": incremental_items})["input"]
        return response_create_ws_request(prepared), self.websocket_session.last_response_from_untraced_warmup

    def prepare_http_request(self, request: Mapping[str, Any]) -> dict[str, Any]:
        return serialize_responses_request(request)


def parse_turn_metadata_header(turn_metadata_header: str | None) -> str | None:
    if turn_metadata_header is None:
        return None
    if not isinstance(turn_metadata_header, str):
        raise TypeError("turn_metadata_header must be a string or None")
    if not _valid_header_value(turn_metadata_header):
        return None
    return turn_metadata_header


def _valid_header_value(value: str) -> bool:
    return "\r" not in value and "\n" not in value


def insert_header_if_valid(headers: dict[str, str], name: str, value: str | None) -> None:
    if value is not None and _valid_header_value(value):
        headers[name] = value


def build_session_headers(session_id: str | None, thread_id: str | None) -> dict[str, str]:
    """Return Rust codex-api session headers for Responses requests."""

    headers: dict[str, str] = {}
    if session_id is not None:
        insert_header_if_valid(headers, "session-id", str(session_id))
    if thread_id is not None:
        insert_header_if_valid(headers, "thread-id", str(thread_id))
    return headers

def build_responses_headers(
    beta_features_header: str | None,
    turn_state: TurnState | None,
    turn_metadata_header: str | None,
) -> dict[str, str]:
    headers: dict[str, str] = {}
    if beta_features_header and _valid_header_value(beta_features_header):
        insert_header_if_valid(headers, "x-codex-beta-features", beta_features_header)
    if turn_state is not None and turn_state.get():
        state = turn_state.get() or ""
        if _valid_header_value(state):
            insert_header_if_valid(headers, X_CODEX_TURN_STATE_HEADER, state)
    if turn_metadata_header is not None and _valid_header_value(turn_metadata_header):
        insert_header_if_valid(headers, X_CODEX_TURN_METADATA_HEADER, turn_metadata_header)
    return headers


def subagent_header_value(session_source: SessionSource) -> str | None:
    if session_source.type == "subagent" and session_source.subagent_source is not None:
        source = session_source.subagent_source
        if source.type == "thread_spawn":
            return "collab_spawn"
        if source.type == "other":
            return source.other
        return source.type
    if (
        session_source.type == "internal"
        and session_source.internal_source == InternalSessionSource.MEMORY_CONSOLIDATION
    ):
        return "memory_consolidation"
    return None


def parent_thread_id_header_value(session_source: SessionSource) -> str | None:
    if session_source.type == "subagent" and session_source.subagent_source is not None:
        source = session_source.subagent_source
        if source.type == "thread_spawn" and source.parent_thread_id is not None:
            return str(source.parent_thread_id)
    return None


def sideband_websocket_auth_headers(api_auth: Any) -> dict[str, str]:
    return auth_headers_from_value(api_auth)


def build_reasoning(model_info: Any, effort: Any, summary: Any) -> dict[str, Any] | None:
    if not getattr(model_info, "supports_reasoning_summaries", False):
        return None
    default_effort = getattr(model_info, "default_reasoning_level", None)
    effective_summary = None if _reasoning_summary_is_none(summary) else summary
    reasoning: dict[str, Any] = {}
    effective_effort = effort or default_effort
    if effective_effort is not None:
        reasoning["effort"] = effective_effort
    if effective_summary is not None:
        reasoning["summary"] = effective_summary
    return reasoning


def _reasoning_summary_is_none(summary: Any) -> bool:
    if summary is None:
        return True
    if isinstance(summary, Enum):
        return str(summary.value).lower() == "none"
    return str(summary).lower() in {"none", "reasoningsummary.none"}


def create_text_param_for_request(
    verbosity: Any,
    output_schema: Any,
    output_schema_strict: bool,
) -> dict[str, Any] | None:
    if not isinstance(output_schema_strict, bool):
        raise TypeError("output_schema_strict must be a bool")
    if verbosity is None and output_schema is None:
        return None
    text: dict[str, Any] = {}
    if verbosity is not None:
        text["verbosity"] = verbosity
    if output_schema is not None:
        text["format"] = {
            "type": "json_schema",
            "strict": output_schema_strict,
            "schema": output_schema,
            "name": "codex_output_schema",
        }
    return text


def create_tools_json_for_responses_api(tools: Sequence[Any]) -> list[dict[str, Any]]:
    """Serialize tool specs into Responses API-compatible JSON objects."""
    tools_json: list[dict[str, Any]] = []
    for tool in tools:
        if hasattr(tool, "to_mapping"):
            value = tool.to_mapping()
        elif isinstance(tool, Mapping):
            value = dict(tool)
        else:
            raise TypeError("tool must be a mapping or expose to_mapping()")
        if not isinstance(value, Mapping):
            raise TypeError("tool.to_mapping() must return a mapping")
        serialized = _serialize_tool_spec_value(value)
        if not isinstance(serialized, Mapping):
            raise TypeError("tool serialization must produce a mapping")
        tools_json.append(dict(serialized))
    return tools_json


def _serialize_tool_spec_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Mapping):
        tool_type = value.get("type")
        return {
            str(key): _serialize_tool_spec_value(item)
            for key, item in value.items()
            if item is not None and not (tool_type == "function" and key == "output_schema")
        }
    if isinstance(value, (list, tuple)):
        return [_serialize_tool_spec_value(item) for item in value]
    return value


def serialize_responses_request(request: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(request, Mapping):
        raise TypeError("request must be a mapping")
    serialized = {str(key): _serialize_request_value(value) for key, value in request.items()}
    _strip_skipped_response_item_ids(serialized.get("input"))
    _strip_internal_response_item_fields(serialized.get("input"))
    if serialized.get("instructions") == "":
        serialized.pop("instructions", None)
    for key in (
        "service_tier",
        "prompt_cache_key",
        "text",
        "client_metadata",
        "previous_response_id",
        "generate",
    ):
        if serialized.get(key) is None:
            serialized.pop(key, None)
    return serialized


_RESPONSE_ITEM_ID_SKIPPED_ON_REQUEST_TYPES = {
    "reasoning",
    "message",
    "web_search_call",
    "function_call",
    "tool_search_call",
    "local_shell_call",
    "custom_tool_call",
}


def _strip_skipped_response_item_ids(input_value: Any) -> None:
    if not isinstance(input_value, list):
        return
    for item in input_value:
        if not isinstance(item, dict):
            continue
        if item.get("type") in _RESPONSE_ITEM_ID_SKIPPED_ON_REQUEST_TYPES:
            item.pop("id", None)


def _strip_internal_response_item_fields(input_value: Any) -> None:
    """Match Rust ``ResponseItem`` wire serialization for tool outputs."""

    if not isinstance(input_value, list):
        return
    for item in input_value:
        if not isinstance(item, dict):
            continue
        if item.get("type") in {"function_call_output", "custom_tool_call_output"}:
            item.pop("success", None)


def _serialize_request_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ResponseItem):
        return _serialize_request_value(_response_item_request_mapping(value))
    if isinstance(value, Mapping):
        return {
            str(key): _serialize_request_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_serialize_request_value(item) for item in value]
    return value


def _response_item_request_mapping(item: ResponseItem) -> dict[str, Any]:
    return item.to_mapping()


def response_create_client_metadata(
    client_metadata: Mapping[str, str] | None,
    trace: Any | None,
) -> dict[str, str] | None:
    if client_metadata is None:
        metadata: dict[str, str] = {}
    elif isinstance(client_metadata, Mapping):
        metadata = {}
        for key, value in client_metadata.items():
            if not isinstance(key, str):
                raise TypeError("client_metadata keys must be strings")
            if not isinstance(value, str):
                raise TypeError("client_metadata values must be strings")
            metadata[key] = value
    else:
        raise TypeError("client_metadata must be a mapping or None")

    traceparent = _trace_field(trace, "traceparent")
    if traceparent is not None:
        metadata[WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] = traceparent
    tracestate = _trace_field(trace, "tracestate")
    if tracestate is not None:
        metadata[WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY] = tracestate
    return metadata or None


def response_create_ws_request(payload: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be a mapping")
    request = dict(payload)
    request["type"] = "response.create"
    return request


def response_processed_ws_request(response_id: str) -> dict[str, str]:
    if not isinstance(response_id, str):
        raise TypeError("response_id must be a string")
    return {"type": "response.processed", "response_id": response_id}


def response_processed_request_for_sampling_turn(
    features: Any,
    *,
    outcome_ok: bool,
    completed_response_id: str | None,
) -> dict[str, str] | None:
    if not isinstance(outcome_ok, bool):
        raise TypeError("outcome_ok must be a bool")
    if completed_response_id is not None and not isinstance(completed_response_id, str):
        raise TypeError("completed_response_id must be a string or None")
    enabled = getattr(features, "enabled", None)
    if not callable(enabled):
        raise TypeError("features must expose enabled(feature)")
    feature = _feature_responses_websocket_response_processed()
    if not enabled(feature) or not outcome_ok or completed_response_id is None:
        return None
    return response_processed_ws_request(completed_response_id)


def sampling_turn_tail_actions(
    *,
    should_emit_token_count: bool,
    cancellation_requested: bool,
    should_emit_turn_diff: bool,
    unified_diff: str | None,
) -> list[dict[str, Any]]:
    if not isinstance(should_emit_token_count, bool):
        raise TypeError("should_emit_token_count must be a bool")
    if not isinstance(cancellation_requested, bool):
        raise TypeError("cancellation_requested must be a bool")
    if not isinstance(should_emit_turn_diff, bool):
        raise TypeError("should_emit_turn_diff must be a bool")
    if unified_diff is not None and not isinstance(unified_diff, str):
        raise TypeError("unified_diff must be a string or None")
    actions: list[dict[str, Any]] = []
    if should_emit_token_count:
        actions.append({"type": "send_token_count"})
    if cancellation_requested:
        actions.append({"type": "turn_aborted"})
        return actions
    if should_emit_turn_diff and unified_diff is not None:
        actions.append({"type": "turn_diff", "unified_diff": unified_diff})
    return actions


@dataclass(frozen=True)
class SamplingPostDrainTailPlan:
    actions: tuple[dict[str, Any], ...]
    should_send_token_count_before_cancellation: bool = False
    should_return_turn_aborted: bool = False
    should_read_turn_diff: bool = False
    should_emit_turn_diff: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.actions, tuple):
            object.__setattr__(self, "actions", tuple(self.actions))
        for action in self.actions:
            if not isinstance(action, dict):
                raise TypeError("actions must contain dict values")
        for field_name in (
            "should_send_token_count_before_cancellation",
            "should_return_turn_aborted",
            "should_read_turn_diff",
            "should_emit_turn_diff",
        ):
            if not isinstance(getattr(self, field_name), bool):
                raise TypeError(f"{field_name} must be a bool")


@dataclass(frozen=True)
class SamplingLoopTailPlan:
    response_processed_request: dict[str, str] | None = None
    should_drain_in_flight: bool = True
    post_drain_tail_plan: SamplingPostDrainTailPlan | None = None

    def __post_init__(self) -> None:
        if self.response_processed_request is not None and not isinstance(self.response_processed_request, dict):
            raise TypeError("response_processed_request must be a dict or None")
        if not isinstance(self.should_drain_in_flight, bool):
            raise TypeError("should_drain_in_flight must be a bool")
        if self.post_drain_tail_plan is not None and not isinstance(
            self.post_drain_tail_plan,
            SamplingPostDrainTailPlan,
        ):
            raise TypeError("post_drain_tail_plan must be a SamplingPostDrainTailPlan or None")


@dataclass(frozen=True)
class SamplingRequestPlan:
    event_apply_plans: tuple[Any, ...]
    loop_tail_plan: SamplingLoopTailPlan
    outcome_ok: bool
    result_needs_follow_up: bool = False
    result_last_agent_message: str | None = None
    completed_response_id: str | None = None
    should_return_turn_aborted: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.event_apply_plans, tuple):
            object.__setattr__(self, "event_apply_plans", tuple(self.event_apply_plans))
        if not isinstance(self.loop_tail_plan, SamplingLoopTailPlan):
            raise TypeError("loop_tail_plan must be a SamplingLoopTailPlan")
        if not isinstance(self.outcome_ok, bool):
            raise TypeError("outcome_ok must be a bool")
        if not isinstance(self.result_needs_follow_up, bool):
            raise TypeError("result_needs_follow_up must be a bool")
        if self.result_last_agent_message is not None and not isinstance(self.result_last_agent_message, str):
            raise TypeError("result_last_agent_message must be a string or None")
        if self.completed_response_id is not None and not isinstance(self.completed_response_id, str):
            raise TypeError("completed_response_id must be a string or None")
        if not isinstance(self.should_return_turn_aborted, bool):
            raise TypeError("should_return_turn_aborted must be a bool")


@dataclass(frozen=True)
class SamplingRequestRuntimePlan:
    steps: tuple[dict[str, Any], ...]
    required_hooks: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.steps, tuple):
            object.__setattr__(self, "steps", tuple(self.steps))
        for step in self.steps:
            if not isinstance(step, dict):
                raise TypeError("steps must contain dict values")
        if not isinstance(self.required_hooks, tuple):
            object.__setattr__(self, "required_hooks", tuple(self.required_hooks))
        for hook in self.required_hooks:
            if not isinstance(hook, str):
                raise TypeError("required_hooks must contain strings")


@dataclass(frozen=True)
class SamplingRequestRuntimeExecutionResult:
    step_results: tuple[dict[str, Any], ...]
    final_result: Any = None
    returned_turn_aborted: bool = False
    phase_results: tuple[dict[str, Any], ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.step_results, tuple):
            object.__setattr__(self, "step_results", tuple(self.step_results))
        for result in self.step_results:
            if not isinstance(result, dict):
                raise TypeError("step_results must contain dict values")
        if not isinstance(self.returned_turn_aborted, bool):
            raise TypeError("returned_turn_aborted must be a bool")
        if not isinstance(self.phase_results, tuple):
            object.__setattr__(self, "phase_results", tuple(self.phase_results))
        for result in self.phase_results:
            if not isinstance(result, dict):
                raise TypeError("phase_results must contain dict values")


@dataclass(frozen=True)
class SamplingRequestRuntimeSessionLifecycleResult:
    websocket_request: dict[str, Any]
    from_untraced_warmup: bool
    runtime_result: SamplingRequestRuntimeExecutionResult
    websocket_outcome: WebsocketStreamOutcome = WebsocketStreamOutcome.STREAM
    http_request: dict[str, Any] | None = None
    http_fallback_activated: bool = False
    runtime_state_summary: dict[str, Any] | None = None
    completed_response_from_untraced_warmup: bool = False
    websocket_connection_reused: bool = False
    websocket_connection_lifecycle: dict[str, bool] | None = None
    websocket_request_start_ms_stamped: bool = False
    inference_trace_started_request: dict[str, Any] | None = None
    inference_trace_started_request_source: str | None = None
    websocket_last_request_recorded: bool = False
    websocket_stream_request_attempt: dict[str, Any] | None = None
    websocket_stream_request_attempt_outcome: dict[str, Any] | None = None
    websocket_last_response_receiver_registered: bool = False
    inference_trace_completed: dict[str, Any] | None = None
    inference_trace_failed: dict[str, Any] | None = None
    inference_trace_cancelled: dict[str, Any] | None = None
    websocket_stream_result: dict[str, Any] | None = None
    websocket_last_response_delivery: dict[str, Any] | None = None
    websocket_completed_telemetry: dict[str, Any] | None = None
    websocket_failed_telemetry: dict[str, Any] | None = None
    websocket_feedback_tags: dict[str, str] | None = None
    websocket_response_processed_request: dict[str, str] | None = None
    websocket_response_processed_result: Any = None

    def __post_init__(self) -> None:
        if not isinstance(self.websocket_request, dict):
            raise TypeError("websocket_request must be a dict")
        if not isinstance(self.from_untraced_warmup, bool):
            raise TypeError("from_untraced_warmup must be a bool")
        if not isinstance(self.runtime_result, SamplingRequestRuntimeExecutionResult):
            raise TypeError("runtime_result must be SamplingRequestRuntimeExecutionResult")
        if not isinstance(self.websocket_outcome, WebsocketStreamOutcome):
            raise TypeError("websocket_outcome must be WebsocketStreamOutcome")
        if self.http_request is not None and not isinstance(self.http_request, dict):
            raise TypeError("http_request must be a dict or None")
        if not isinstance(self.http_fallback_activated, bool):
            raise TypeError("http_fallback_activated must be a bool")
        if self.runtime_state_summary is not None and not isinstance(self.runtime_state_summary, dict):
            raise TypeError("runtime_state_summary must be a dict or None")
        if not isinstance(self.completed_response_from_untraced_warmup, bool):
            raise TypeError("completed_response_from_untraced_warmup must be a bool")
        if not isinstance(self.websocket_connection_reused, bool):
            raise TypeError("websocket_connection_reused must be a bool")
        if self.websocket_connection_lifecycle is not None and not isinstance(
            self.websocket_connection_lifecycle, dict
        ):
            raise TypeError("websocket_connection_lifecycle must be a dict or None")
        if not isinstance(self.websocket_request_start_ms_stamped, bool):
            raise TypeError("websocket_request_start_ms_stamped must be a bool")
        if self.inference_trace_started_request is not None and not isinstance(
            self.inference_trace_started_request, dict
        ):
            raise TypeError("inference_trace_started_request must be a dict or None")
        if self.inference_trace_started_request_source is not None and not isinstance(
            self.inference_trace_started_request_source, str
        ):
            raise TypeError("inference_trace_started_request_source must be a string or None")
        if not isinstance(self.websocket_last_request_recorded, bool):
            raise TypeError("websocket_last_request_recorded must be a bool")
        if self.websocket_stream_request_attempt is not None and not isinstance(
            self.websocket_stream_request_attempt, dict
        ):
            raise TypeError("websocket_stream_request_attempt must be a dict or None")
        if self.websocket_stream_request_attempt_outcome is not None and not isinstance(
            self.websocket_stream_request_attempt_outcome, dict
        ):
            raise TypeError("websocket_stream_request_attempt_outcome must be a dict or None")
        if not isinstance(self.websocket_last_response_receiver_registered, bool):
            raise TypeError("websocket_last_response_receiver_registered must be a bool")
        if self.inference_trace_completed is not None and not isinstance(self.inference_trace_completed, dict):
            raise TypeError("inference_trace_completed must be a dict or None")
        if self.inference_trace_failed is not None and not isinstance(self.inference_trace_failed, dict):
            raise TypeError("inference_trace_failed must be a dict or None")
        if self.inference_trace_cancelled is not None and not isinstance(self.inference_trace_cancelled, dict):
            raise TypeError("inference_trace_cancelled must be a dict or None")
        if self.websocket_stream_result is not None and not isinstance(self.websocket_stream_result, dict):
            raise TypeError("websocket_stream_result must be a dict or None")
        if self.websocket_last_response_delivery is not None and not isinstance(
            self.websocket_last_response_delivery, dict
        ):
            raise TypeError("websocket_last_response_delivery must be a dict or None")
        if self.websocket_completed_telemetry is not None and not isinstance(
            self.websocket_completed_telemetry, dict
        ):
            raise TypeError("websocket_completed_telemetry must be a dict or None")
        if self.websocket_failed_telemetry is not None and not isinstance(
            self.websocket_failed_telemetry, dict
        ):
            raise TypeError("websocket_failed_telemetry must be a dict or None")
        if self.websocket_feedback_tags is not None and not isinstance(self.websocket_feedback_tags, dict):
            raise TypeError("websocket_feedback_tags must be a dict or None")
        if self.websocket_feedback_tags is not None:
            for key, value in self.websocket_feedback_tags.items():
                if not isinstance(key, str) or not isinstance(value, str):
                    raise TypeError("websocket_feedback_tags must contain string keys and values")
        if self.websocket_response_processed_request is not None and not isinstance(
            self.websocket_response_processed_request,
            dict,
        ):
            raise TypeError("websocket_response_processed_request must be a dict or None")


@dataclass(slots=True)
class SamplingRuntimeEventApplicationState:
    applied_event_types: tuple[str, ...] = ()
    completed_response_id: str | None = None
    result_needs_follow_up: bool = False
    result_last_agent_message: str | None = None
    should_emit_token_count: bool = False
    should_emit_turn_diff: bool = False
    token_usage_to_record: Any = None
    metadata_events: tuple[dict[str, Any], ...] = ()
    server_reasoning_included: bool | None = None
    rate_limits_to_record: Any = None
    models_etag_to_refresh: str | None = None
    output_item_done_events: tuple[dict[str, Any], ...] = ()
    completed_output_items: tuple[ResponseItem, ...] = ()
    should_continue_loop: bool = False
    preempt_for_mailbox_mail: bool = False
    output_result: Any = None
    state_after_output_result: Any = None
    mailbox_preemption_plan: Any = None
    output_item_added_events: tuple[dict[str, Any], ...] = ()
    output_text_delta_events: tuple[dict[str, Any], ...] = ()
    active_tool_argument_diff_consumer: tuple[str, object] | None = None
    should_reset_tool_argument_diff_consumer: bool = False
    active_item: Any = None
    active_item_is_streaming_to_client: bool = False
    pending_agent_message_item: Any = None
    pending_agent_message_items: tuple[Any, ...] = ()
    started_agent_message_item_ids: tuple[str, ...] = ()
    leading_whitespace_by_item: tuple[tuple[str, str], ...] = ()
    plan_item_id: str = "plan"
    plan_item_started: bool = False
    plan_item_completed: bool = False
    plan_events: tuple[dict[str, Any], ...] = ()
    turn_item_started_to_emit: Any = None
    assistant_text_deltas: tuple[dict[str, Any], ...] = ()
    raw_content_deltas: tuple[dict[str, Any], ...] = ()
    tool_call_input_delta_events: tuple[dict[str, Any], ...] = ()
    reasoning_delta_events: tuple[dict[str, Any], ...] = ()
    emitted_stream_events: tuple[object, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.applied_event_types, tuple):
            self.applied_event_types = tuple(self.applied_event_types)
        for event_type in self.applied_event_types:
            if not isinstance(event_type, str):
                raise TypeError("applied_event_types must contain strings")
        if self.completed_response_id is not None and not isinstance(self.completed_response_id, str):
            raise TypeError("completed_response_id must be a string or None")
        if not isinstance(self.result_needs_follow_up, bool):
            raise TypeError("result_needs_follow_up must be a bool")
        if self.result_last_agent_message is not None and not isinstance(self.result_last_agent_message, str):
            raise TypeError("result_last_agent_message must be a string or None")
        if not isinstance(self.should_emit_token_count, bool):
            raise TypeError("should_emit_token_count must be a bool")
        if not isinstance(self.should_emit_turn_diff, bool):
            raise TypeError("should_emit_turn_diff must be a bool")
        if not isinstance(self.metadata_events, tuple):
            self.metadata_events = tuple(self.metadata_events)
        for event in self.metadata_events:
            if not isinstance(event, dict):
                raise TypeError("metadata_events must contain dict values")
        if self.server_reasoning_included is not None and not isinstance(self.server_reasoning_included, bool):
            raise TypeError("server_reasoning_included must be a bool or None")
        if self.models_etag_to_refresh is not None and not isinstance(self.models_etag_to_refresh, str):
            raise TypeError("models_etag_to_refresh must be a string or None")
        if not isinstance(self.output_item_done_events, tuple):
            self.output_item_done_events = tuple(self.output_item_done_events)
        for event in self.output_item_done_events:
            if not isinstance(event, dict):
                raise TypeError("output_item_done_events must contain dict values")
        if not isinstance(self.completed_output_items, tuple):
            self.completed_output_items = tuple(self.completed_output_items)
        for item in self.completed_output_items:
            if not isinstance(item, ResponseItem):
                raise TypeError("completed_output_items must contain ResponseItem values")
        if not isinstance(self.should_continue_loop, bool):
            raise TypeError("should_continue_loop must be a bool")
        if not isinstance(self.preempt_for_mailbox_mail, bool):
            raise TypeError("preempt_for_mailbox_mail must be a bool")
        if not isinstance(self.output_item_added_events, tuple):
            self.output_item_added_events = tuple(self.output_item_added_events)
        for event in self.output_item_added_events:
            if not isinstance(event, dict):
                raise TypeError("output_item_added_events must contain dict values")
        if not isinstance(self.output_text_delta_events, tuple):
            self.output_text_delta_events = tuple(self.output_text_delta_events)
        for event in self.output_text_delta_events:
            if not isinstance(event, dict):
                raise TypeError("output_text_delta_events must contain dict values")
        if self.active_tool_argument_diff_consumer is not None:
            if (
                not isinstance(self.active_tool_argument_diff_consumer, tuple)
                or len(self.active_tool_argument_diff_consumer) != 2
                or not isinstance(self.active_tool_argument_diff_consumer[0], str)
            ):
                raise TypeError("active_tool_argument_diff_consumer must be a (call_id, consumer) tuple or None")
        if not isinstance(self.should_reset_tool_argument_diff_consumer, bool):
            raise TypeError("should_reset_tool_argument_diff_consumer must be a bool")
        if not isinstance(self.active_item_is_streaming_to_client, bool):
            raise TypeError("active_item_is_streaming_to_client must be a bool")
        if not isinstance(self.pending_agent_message_items, tuple):
            self.pending_agent_message_items = tuple(self.pending_agent_message_items)
        if not isinstance(self.started_agent_message_item_ids, tuple):
            self.started_agent_message_item_ids = tuple(self.started_agent_message_item_ids)
        for item_id in self.started_agent_message_item_ids:
            if not isinstance(item_id, str):
                raise TypeError("started_agent_message_item_ids must contain strings")
        if not isinstance(self.leading_whitespace_by_item, tuple):
            self.leading_whitespace_by_item = tuple(self.leading_whitespace_by_item)
        for item_id, whitespace in self.leading_whitespace_by_item:
            if not isinstance(item_id, str) or not isinstance(whitespace, str):
                raise TypeError("leading_whitespace_by_item must contain string pairs")
        if not isinstance(self.plan_item_id, str):
            raise TypeError("plan_item_id must be a string")
        if not isinstance(self.plan_item_started, bool):
            raise TypeError("plan_item_started must be a bool")
        if not isinstance(self.plan_item_completed, bool):
            raise TypeError("plan_item_completed must be a bool")
        if not isinstance(self.plan_events, tuple):
            self.plan_events = tuple(self.plan_events)
        for event in self.plan_events:
            if not isinstance(event, dict):
                raise TypeError("plan_events must contain dict values")
        if not isinstance(self.assistant_text_deltas, tuple):
            self.assistant_text_deltas = tuple(self.assistant_text_deltas)
        for delta in self.assistant_text_deltas:
            if not isinstance(delta, dict):
                raise TypeError("assistant_text_deltas must contain dict values")
        if not isinstance(self.raw_content_deltas, tuple):
            self.raw_content_deltas = tuple(self.raw_content_deltas)
        for delta in self.raw_content_deltas:
            if not isinstance(delta, dict):
                raise TypeError("raw_content_deltas must contain dict values")
        if not isinstance(self.tool_call_input_delta_events, tuple):
            self.tool_call_input_delta_events = tuple(self.tool_call_input_delta_events)
        for event in self.tool_call_input_delta_events:
            if not isinstance(event, dict):
                raise TypeError("tool_call_input_delta_events must contain dict values")
        if not isinstance(self.reasoning_delta_events, tuple):
            self.reasoning_delta_events = tuple(self.reasoning_delta_events)
        for event in self.reasoning_delta_events:
            if not isinstance(event, dict):
                raise TypeError("reasoning_delta_events must contain dict values")
        if not isinstance(self.emitted_stream_events, tuple):
            self.emitted_stream_events = tuple(self.emitted_stream_events)

    def snapshot(self) -> dict[str, Any]:
        return {
            "applied_event_types": self.applied_event_types,
            "completed_response_id": self.completed_response_id,
            "result_needs_follow_up": self.result_needs_follow_up,
            "result_last_agent_message": self.result_last_agent_message,
            "should_emit_token_count": self.should_emit_token_count,
            "should_emit_turn_diff": self.should_emit_turn_diff,
            "token_usage_to_record": self.token_usage_to_record,
            "metadata_events": self.metadata_events,
            "server_reasoning_included": self.server_reasoning_included,
            "rate_limits_to_record": self.rate_limits_to_record,
            "models_etag_to_refresh": self.models_etag_to_refresh,
            "output_item_done_events": self.output_item_done_events,
            "completed_output_items": self.completed_output_items,
            "should_continue_loop": self.should_continue_loop,
            "preempt_for_mailbox_mail": self.preempt_for_mailbox_mail,
            "output_result": self.output_result,
            "state_after_output_result": self.state_after_output_result,
            "mailbox_preemption_plan": self.mailbox_preemption_plan,
            "output_item_added_events": self.output_item_added_events,
            "output_text_delta_events": self.output_text_delta_events,
            "active_tool_argument_diff_consumer": self.active_tool_argument_diff_consumer,
            "should_reset_tool_argument_diff_consumer": self.should_reset_tool_argument_diff_consumer,
            "active_item": self.active_item,
            "active_item_is_streaming_to_client": self.active_item_is_streaming_to_client,
            "pending_agent_message_item": self.pending_agent_message_item,
            "pending_agent_message_items": self.pending_agent_message_items,
            "started_agent_message_item_ids": self.started_agent_message_item_ids,
            "leading_whitespace_by_item": self.leading_whitespace_by_item,
            "plan_item_id": self.plan_item_id,
            "plan_item_started": self.plan_item_started,
            "plan_item_completed": self.plan_item_completed,
            "plan_events": self.plan_events,
            "turn_item_started_to_emit": self.turn_item_started_to_emit,
            "assistant_text_deltas": self.assistant_text_deltas,
            "raw_content_deltas": self.raw_content_deltas,
            "tool_call_input_delta_events": self.tool_call_input_delta_events,
            "reasoning_delta_events": self.reasoning_delta_events,
            "emitted_stream_events": self.emitted_stream_events,
        }


@dataclass(slots=True)
class SamplingRequestRuntimeHookAdapter:
    websocket_session: WebsocketSession | None = None
    event_application_state: SamplingRuntimeEventApplicationState | None = None
    event_plan_applier: Callable[[Any], Any] | None = None
    response_processed_sender: Callable[[str], Any] | None = None
    in_flight_drainer: Callable[[], Any] | None = None
    token_count_sender: Callable[[], Any] | None = None
    turn_diff_sender: Callable[[str], Any] | None = None
    unknown_tail_action_handler: Callable[[Mapping[str, Any]], Any] | None = None

    def apply_event_plan(self, step: Mapping[str, Any]) -> Any:
        plan = step.get("plan")
        if plan is None:
            raise TypeError("apply_event_plan step plan is required")
        if self.event_plan_applier is not None:
            return self.event_plan_applier(plan)
        if self.event_application_state is not None:
            return _apply_sampling_event_plan_to_state(plan, self.event_application_state)
        return _sampling_event_apply_plan_summary(plan)

    def send_response_processed(self, step: Mapping[str, Any]) -> Any:
        request = step.get("request")
        if not isinstance(request, Mapping):
            raise TypeError("send_response_processed step request must be a mapping")
        response_id = request.get("response_id")
        if not isinstance(response_id, str):
            raise TypeError("send_response_processed response_id must be a string")
        if self.response_processed_sender is not None:
            try:
                return self.response_processed_sender(response_id)
            except Exception as exc:
                return {"sent": False, "error": str(exc), "request": dict(request)}
        connection = self._connection()
        if connection is None:
            return {"sent": False, "reason": "missing_connection", "request": dict(request)}
        sender = getattr(connection, "send_response_processed", None)
        if callable(sender):
            try:
                return sender(response_id)
            except Exception as exc:
                return {"sent": False, "error": str(exc), "request": dict(request)}
        generic_sender = getattr(connection, "send", None)
        if callable(generic_sender):
            try:
                return generic_sender(dict(request))
            except Exception as exc:
                return {"sent": False, "error": str(exc), "request": dict(request)}
        return {"sent": False, "reason": "missing_sender", "request": dict(request)}

    def drain_in_flight(self, step: Mapping[str, Any]) -> Any:
        if self.in_flight_drainer is not None:
            return self.in_flight_drainer()
        connection = self._connection()
        drainer = getattr(connection, "drain_in_flight", None) if connection is not None else None
        if callable(drainer):
            return drainer()
        return {"drained": False, "reason": "missing_drainer"}

    def send_token_count(self, step: Mapping[str, Any]) -> Any:
        if self.token_count_sender is None:
            return {"sent": False, "reason": "missing_token_count_sender"}
        return self.token_count_sender()

    def send_turn_diff(self, step: Mapping[str, Any]) -> Any:
        unified_diff = step.get("unified_diff")
        if not isinstance(unified_diff, str):
            raise TypeError("send_turn_diff unified_diff must be a string")
        if self.turn_diff_sender is None:
            return {
                "sent": False,
                "reason": "missing_turn_diff_sender",
                "unified_diff": unified_diff,
            }
        return self.turn_diff_sender(unified_diff)

    def return_sampling_result(self, step: Mapping[str, Any]) -> dict[str, Any]:
        if self.event_application_state is not None and (
            self.event_application_state.applied_event_types
            or self.event_application_state.result_needs_follow_up
            or self.event_application_state.result_last_agent_message is not None
        ):
            return _sampling_result_from_event_application_state(self.event_application_state)
        needs_follow_up = step.get("needs_follow_up", False)
        last_agent_message = step.get("last_agent_message")
        if not isinstance(needs_follow_up, bool):
            raise TypeError("return_sampling_result needs_follow_up must be a bool")
        if last_agent_message is not None and not isinstance(last_agent_message, str):
            raise TypeError("return_sampling_result last_agent_message must be a string or None")
        return {
            "needs_follow_up": needs_follow_up,
            "last_agent_message": last_agent_message,
        }

    def return_turn_aborted(self, step: Mapping[str, Any]) -> dict[str, str]:
        return {"error": "turn_aborted"}

    def handle_unknown_tail_action(self, step: Mapping[str, Any]) -> Any:
        action = step.get("action")
        if not isinstance(action, Mapping):
            raise TypeError("unknown_tail_action step action must be a mapping")
        if self.unknown_tail_action_handler is None:
            return {"handled": False, "reason": "missing_unknown_tail_action_handler", "action": dict(action)}
        return self.unknown_tail_action_handler(action)

    def _connection(self) -> Any:
        if self.websocket_session is None:
            return None
        return self.websocket_session.connection


def _sampling_event_apply_plan_summary(plan: Any) -> dict[str, Any]:
    event_type = getattr(plan, "event_type", None)
    if not isinstance(event_type, str):
        raise TypeError("apply event plan must expose string event_type")
    no_op = getattr(plan, "no_op", False)
    if not isinstance(no_op, bool):
        raise TypeError("apply event plan no_op must be a bool")

    child_plan_fields = (
        "output_item_done_apply_plan",
        "output_item_added_apply_plan",
        "output_text_delta_apply_plan",
        "tool_call_input_delta_apply_plan",
        "reasoning_delta_apply_plan",
        "completed_event_apply_plan",
        "metadata_event_apply_plan",
    )
    child_plans = tuple(field for field in child_plan_fields if getattr(plan, field, None) is not None)
    summary: dict[str, Any] = {
        "applied": False,
        "reason": "missing_event_plan_applier",
        "event_type": event_type,
        "no_op": no_op,
        "child_plans": child_plans,
    }

    completed = getattr(plan, "completed_event_apply_plan", None)
    if completed is not None:
        summary["completed_response_id"] = getattr(completed, "completed_response_id_after", None)
        summary["result_needs_follow_up"] = getattr(completed, "result_needs_follow_up", False)
        summary["result_last_agent_message"] = getattr(completed, "result_last_agent_message", None)
        summary["should_emit_token_count"] = getattr(completed, "should_emit_token_count", False)
        summary["should_emit_turn_diff"] = getattr(completed, "should_emit_turn_diff", False)

    metadata = getattr(plan, "metadata_event_apply_plan", None)
    if metadata is not None:
        summary["metadata_event_type"] = getattr(metadata, "event_type", None)
        summary["metadata_should_emit_token_count"] = getattr(metadata, "should_emit_token_count", False)

    output_added = getattr(plan, "output_item_added_apply_plan", None)
    if output_added is not None:
        summary["has_active_tool_argument_diff_consumer"] = (
            getattr(output_added, "active_tool_argument_diff_consumer_after", None) is not None
        )
        summary["should_reset_tool_argument_diff_consumer"] = getattr(
            output_added,
            "should_reset_tool_argument_diff_consumer",
            False,
        )
        summary["has_pending_agent_message_item"] = getattr(output_added, "pending_agent_message_item", None) is not None
        summary["has_turn_item_started_to_emit"] = getattr(output_added, "turn_item_started_to_emit", None) is not None
        summary["has_seeded_streamed_assistant_text_plan"] = (
            getattr(output_added, "seeded_streamed_assistant_text_plan", None) is not None
        )
        summary["has_active_item_after"] = getattr(output_added, "active_item_after", None) is not None
        summary["active_item_is_streaming_to_client_after"] = getattr(
            output_added,
            "active_item_is_streaming_to_client_after",
            False,
        )

    output_text = getattr(plan, "output_text_delta_apply_plan", None)
    if output_text is not None:
        summary["output_text_delta_item_id"] = getattr(output_text, "item_id", None)
        summary["raw_content_delta"] = getattr(output_text, "raw_content_delta", None)
        streamed = getattr(output_text, "streamed_assistant_text_plan", None)
        if streamed is not None:
            summary["streamed_assistant_text_item_id"] = getattr(streamed, "item_id", None)
            summary["visible_text_delta"] = getattr(streamed, "visible_text_delta", None)
            summary["citations"] = getattr(streamed, "citations", ())
            summary["ignored_citations"] = getattr(streamed, "ignored_citations", False)

    tool_delta = getattr(plan, "tool_call_input_delta_apply_plan", None)
    if tool_delta is not None:
        summary["tool_call_input_delta_call_id"] = getattr(tool_delta, "call_id", None)
        summary["tool_call_input_delta"] = getattr(tool_delta, "delta", None)
        summary["tool_call_should_send_event"] = getattr(tool_delta, "should_send_event", False)
        summary["has_tool_call_event_to_emit"] = getattr(tool_delta, "event_to_emit", None) is not None

    reasoning_delta = getattr(plan, "reasoning_delta_apply_plan", None)
    if reasoning_delta is not None:
        summary["reasoning_delta_event_type"] = getattr(reasoning_delta, "event_type", None)
        summary["reasoning_delta_item_id"] = getattr(reasoning_delta, "item_id", None)
        summary["reasoning_event_to_emit"] = getattr(reasoning_delta, "event_to_emit", None)

    output_done = getattr(plan, "output_item_done_apply_plan", None)
    if output_done is not None:
        summary["should_continue_loop"] = getattr(output_done, "should_continue_loop", False)
        summary["preempt_for_mailbox_mail"] = getattr(output_done, "preempt_for_mailbox_mail", False)
        state_after = getattr(output_done, "state_after_output_result", None)
        if state_after is not None:
            summary["output_state_needs_follow_up"] = getattr(state_after, "needs_follow_up", False)
            summary["output_state_last_agent_message"] = getattr(state_after, "last_agent_message", None)
            summary["output_state_in_flight"] = getattr(state_after, "in_flight", ())
        mailbox_preemption = getattr(output_done, "mailbox_preemption_plan", None)
        if mailbox_preemption is not None:
            summary["mailbox_preemption_needs_follow_up"] = getattr(mailbox_preemption, "needs_follow_up", False)
            summary["mailbox_preemption_last_agent_message"] = getattr(mailbox_preemption, "last_agent_message", None)

    return summary


def _apply_sampling_event_plan_to_state(
    plan: Any,
    state: SamplingRuntimeEventApplicationState,
) -> dict[str, Any]:
    if not isinstance(state, SamplingRuntimeEventApplicationState):
        raise TypeError("state must be a SamplingRuntimeEventApplicationState")

    summary = _sampling_event_apply_plan_summary(plan)
    event_type = summary["event_type"]
    state.applied_event_types = state.applied_event_types + (event_type,)

    completed = getattr(plan, "completed_event_apply_plan", None)
    if completed is not None:
        state.completed_response_id = getattr(completed, "completed_response_id_after", None)
        state.result_needs_follow_up = getattr(completed, "result_needs_follow_up", False)
        state.result_last_agent_message = getattr(completed, "result_last_agent_message", None)
        state.should_emit_token_count = (
            state.should_emit_token_count or getattr(completed, "should_emit_token_count", False)
        )
        state.should_emit_turn_diff = state.should_emit_turn_diff or getattr(completed, "should_emit_turn_diff", False)
        if getattr(completed, "should_record_token_usage", False):
            state.token_usage_to_record = getattr(completed, "token_usage_to_record", None)
        flush_all = getattr(completed, "flush_all_plan", None)
        for item_plan in tuple(getattr(flush_all, "item_plans", ()) or ()):
            streamed = _streamed_assistant_text_plan_from_flush_item(
                item_plan,
                thread_id=getattr(completed, "thread_id", ""),
                turn_id=getattr(completed, "turn_id", ""),
            )
            if streamed is None:
                continue
            _apply_streamed_assistant_text_plan_to_state(streamed, state)

    metadata = getattr(plan, "metadata_event_apply_plan", None)
    if metadata is not None:
        metadata_record = {
            "event_type": getattr(metadata, "event_type", None),
            "server_model_to_check": getattr(metadata, "server_model_to_check", None),
            "should_mark_server_model_warning_if_emitted": getattr(
                metadata,
                "should_mark_server_model_warning_if_emitted",
                False,
            ),
            "model_verification_to_emit": getattr(metadata, "model_verification_to_emit", None),
            "should_mark_model_verification_emitted": getattr(
                metadata,
                "should_mark_model_verification_emitted",
                False,
            ),
        }
        state.metadata_events = state.metadata_events + (metadata_record,)
        state.should_emit_token_count = (
            state.should_emit_token_count or getattr(metadata, "should_emit_token_count", False)
        )
        server_reasoning_included = getattr(metadata, "server_reasoning_included", None)
        if server_reasoning_included is not None:
            state.server_reasoning_included = server_reasoning_included
        rate_limits = getattr(metadata, "rate_limits_to_record", None)
        if rate_limits is not None:
            state.rate_limits_to_record = rate_limits
        models_etag = getattr(metadata, "models_etag_to_refresh", None)
        if models_etag is not None:
            state.models_etag_to_refresh = models_etag

    output_added = getattr(plan, "output_item_added_apply_plan", None)
    if output_added is not None:
        output_added_record = {
            "has_active_tool_argument_diff_consumer": (
                getattr(output_added, "active_tool_argument_diff_consumer_after", None) is not None
            ),
            "should_reset_tool_argument_diff_consumer": getattr(
                output_added,
                "should_reset_tool_argument_diff_consumer",
                False,
            ),
            "has_pending_agent_message_item": getattr(output_added, "pending_agent_message_item", None) is not None,
            "has_turn_item_started_to_emit": getattr(output_added, "turn_item_started_to_emit", None) is not None,
            "has_seeded_streamed_assistant_text_plan": (
                getattr(output_added, "seeded_streamed_assistant_text_plan", None) is not None
            ),
            "has_active_item_after": getattr(output_added, "active_item_after", None) is not None,
            "active_item_is_streaming_to_client_after": getattr(
                output_added,
                "active_item_is_streaming_to_client_after",
                False,
            ),
        }
        state.output_item_added_events = state.output_item_added_events + (output_added_record,)
        state.active_tool_argument_diff_consumer = getattr(
            output_added,
            "active_tool_argument_diff_consumer_after",
            state.active_tool_argument_diff_consumer,
        )
        state.should_reset_tool_argument_diff_consumer = (
            state.should_reset_tool_argument_diff_consumer
            or getattr(output_added, "should_reset_tool_argument_diff_consumer", False)
        )
        pending_agent_message_item = getattr(output_added, "pending_agent_message_item", None)
        if pending_agent_message_item is not None:
            state.pending_agent_message_item = pending_agent_message_item
            state.pending_agent_message_items = _replace_pending_turn_item(
                state.pending_agent_message_items,
                pending_agent_message_item,
            )
        turn_item_started_to_emit = getattr(output_added, "turn_item_started_to_emit", None)
        if turn_item_started_to_emit is not None:
            state.turn_item_started_to_emit = turn_item_started_to_emit
        active_item_after = getattr(output_added, "active_item_after", None)
        if active_item_after is not None:
            state.active_item = active_item_after
        state.active_item_is_streaming_to_client = getattr(
            output_added,
            "active_item_is_streaming_to_client_after",
            state.active_item_is_streaming_to_client,
        )
        seeded = getattr(output_added, "seeded_streamed_assistant_text_plan", None)
        if seeded is not None:
            _apply_streamed_assistant_text_plan_to_state(seeded, state)

    output_text = getattr(plan, "output_text_delta_apply_plan", None)
    if output_text is not None:
        output_text_record = {
            "item_id": getattr(output_text, "item_id", None),
            "has_streamed_assistant_text_plan": getattr(output_text, "streamed_assistant_text_plan", None) is not None,
            "has_raw_content_delta": getattr(output_text, "raw_content_delta", None) is not None,
        }
        state.output_text_delta_events = state.output_text_delta_events + (output_text_record,)
        streamed = getattr(output_text, "streamed_assistant_text_plan", None)
        if streamed is not None:
            _apply_streamed_assistant_text_plan_to_state(streamed, state)
        raw_content_delta = getattr(output_text, "raw_content_delta", None)
        if raw_content_delta is not None:
            record = {
                "item_id": getattr(output_text, "item_id", None),
                "raw_content_delta": raw_content_delta,
                "event_to_emit": {
                    "type": "agent_message_content_delta",
                    "thread_id": getattr(output_text, "thread_id", ""),
                    "turn_id": getattr(output_text, "turn_id", ""),
                    "item_id": getattr(output_text, "item_id", None),
                    "delta": raw_content_delta,
                },
            }
            state.raw_content_deltas = state.raw_content_deltas + (record,)
            state.emitted_stream_events = state.emitted_stream_events + (record["event_to_emit"],)

    tool_delta = getattr(plan, "tool_call_input_delta_apply_plan", None)
    if tool_delta is not None:
        tool_delta_record = {
            "call_id": getattr(tool_delta, "call_id", None),
            "delta": getattr(tool_delta, "delta", None),
            "should_send_event": getattr(tool_delta, "should_send_event", False),
            "has_event_to_emit": getattr(tool_delta, "event_to_emit", None) is not None,
        }
        state.tool_call_input_delta_events = state.tool_call_input_delta_events + (tool_delta_record,)
        event_to_emit = getattr(tool_delta, "event_to_emit", None)
        if getattr(tool_delta, "should_send_event", False) and event_to_emit is not None:
            state.emitted_stream_events = state.emitted_stream_events + (event_to_emit,)

    reasoning_delta = getattr(plan, "reasoning_delta_apply_plan", None)
    if reasoning_delta is not None:
        reasoning_record = {
            "event_type": getattr(reasoning_delta, "event_type", None),
            "item_id": getattr(reasoning_delta, "item_id", None),
            "event_to_emit": getattr(reasoning_delta, "event_to_emit", None),
        }
        state.reasoning_delta_events = state.reasoning_delta_events + (reasoning_record,)
        state.emitted_stream_events = state.emitted_stream_events + (
            getattr(reasoning_delta, "event_to_emit", None),
        )

    output_done = getattr(plan, "output_item_done_apply_plan", None)
    if output_done is not None:
        transition = getattr(output_done, "transition_plan", None)
        finished_tool_input_event = getattr(transition, "finished_tool_input_event", None)
        output_done_record = {
            "should_continue_loop": getattr(output_done, "should_continue_loop", False),
            "preempt_for_mailbox_mail": getattr(output_done, "preempt_for_mailbox_mail", False),
            "has_streamed_assistant_text_plan": getattr(output_done, "streamed_assistant_text_plan", None) is not None,
            "has_plan_mode_assistant_done_plan": getattr(output_done, "plan_mode_assistant_done_plan", None) is not None,
            "has_finished_tool_input_event": finished_tool_input_event is not None,
            "has_completed_item": getattr(output_done, "completed_item", None) is not None,
        }
        state.output_item_done_events = state.output_item_done_events + (output_done_record,)
        if finished_tool_input_event is not None:
            state.emitted_stream_events = state.emitted_stream_events + (finished_tool_input_event,)
        state.active_tool_argument_diff_consumer = None
        completed_item = getattr(output_done, "completed_item", None)
        completed_turn_item = getattr(output_done, "completed_turn_item", None)
        if isinstance(completed_item, ResponseItem) and completed_item not in state.completed_output_items:
            state.completed_output_items = state.completed_output_items + (completed_item,)
        state.should_continue_loop = state.should_continue_loop or getattr(output_done, "should_continue_loop", False)
        state.preempt_for_mailbox_mail = (
            state.preempt_for_mailbox_mail or getattr(output_done, "preempt_for_mailbox_mail", False)
        )
        output_result = getattr(output_done, "output_result", None)
        streamed = getattr(output_done, "streamed_assistant_text_plan", None)
        if streamed is not None:
            _apply_streamed_assistant_text_plan_to_state(streamed, state)
        plan_done = getattr(output_done, "plan_mode_assistant_done_plan", None)
        if plan_done is not None:
            _apply_plan_mode_assistant_done_plan_to_state(
                plan_done,
                state,
                thread_id=getattr(transition, "thread_id", ""),
                turn_id=getattr(transition, "turn_id", ""),
                completed_item=completed_item,
                completed_turn_item=completed_turn_item,
            )
        else:
            turn_item = (
                completed_turn_item
                if isinstance(completed_turn_item, TurnItem)
                else _completed_response_item_to_turn_item(completed_item)
            )
            if turn_item is not None:
                _append_stream_event(
                    state,
                    _item_lifecycle_event(
                        "item_completed",
                        getattr(transition, "thread_id", ""),
                        getattr(transition, "turn_id", ""),
                        turn_item,
                    ),
                )
        if output_result is not None:
            state.output_result = output_result
            state.result_needs_follow_up = getattr(output_result, "needs_follow_up", state.result_needs_follow_up)
            state.result_last_agent_message = getattr(
                output_result,
                "last_agent_message",
                state.result_last_agent_message,
            )
        state_after = getattr(output_done, "state_after_output_result", None)
        if state_after is not None:
            state.state_after_output_result = state_after
            state.result_needs_follow_up = getattr(state_after, "needs_follow_up", state.result_needs_follow_up)
            state.result_last_agent_message = getattr(
                state_after,
                "last_agent_message",
                state.result_last_agent_message,
            )
        mailbox_preemption = getattr(output_done, "mailbox_preemption_plan", None)
        if mailbox_preemption is not None:
            state.mailbox_preemption_plan = mailbox_preemption
            state.result_needs_follow_up = getattr(
                mailbox_preemption,
                "needs_follow_up",
                state.result_needs_follow_up,
            )
            state.result_last_agent_message = getattr(
                mailbox_preemption,
                "last_agent_message",
                state.result_last_agent_message,
            )

    summary["applied"] = True
    summary["reason"] = "applied_to_event_application_state"
    summary["state"] = state.snapshot()
    return summary


def _streamed_assistant_text_delta_record(plan: Any) -> dict[str, Any]:
    record = {
        "item_id": getattr(plan, "item_id", None),
        "visible_text_delta": getattr(plan, "visible_text_delta", None),
        "has_plan_segments_plan": getattr(plan, "plan_segments_plan", None) is not None,
        "citations": getattr(plan, "citations", ()),
        "ignored_citations": getattr(plan, "ignored_citations", False),
    }
    visible_text_delta = getattr(plan, "visible_text_delta", None)
    if isinstance(visible_text_delta, str) and visible_text_delta:
        record["event_to_emit"] = {
            "type": "agent_message_content_delta",
            "thread_id": getattr(plan, "thread_id", ""),
            "turn_id": getattr(plan, "turn_id", ""),
            "item_id": getattr(plan, "item_id", None),
            "delta": visible_text_delta,
        }
    return record


def _apply_streamed_assistant_text_plan_to_state(
    plan: Any,
    state: SamplingRuntimeEventApplicationState,
) -> None:
    record = _streamed_assistant_text_delta_record(plan)
    state.assistant_text_deltas = state.assistant_text_deltas + (record,)
    event_to_emit = record.get("event_to_emit")
    if event_to_emit is not None:
        state.emitted_stream_events = state.emitted_stream_events + (event_to_emit,)
    segments_plan = getattr(plan, "plan_segments_plan", None)
    if segments_plan is not None:
        _apply_plan_segments_plan_to_state(
            segments_plan,
            state,
            thread_id=getattr(plan, "thread_id", ""),
            turn_id=getattr(plan, "turn_id", ""),
        )


def _apply_plan_segments_plan_to_state(
    segments_plan: Any,
    state: SamplingRuntimeEventApplicationState,
    *,
    thread_id: str,
    turn_id: str,
) -> None:
    for action in tuple(getattr(segments_plan, "actions", ()) or ()):
        action_type = getattr(action, "action_type", None)
        item_id = getattr(action, "item_id", None)
        delta = getattr(action, "delta", None)
        if action_type == "emit_pending_agent_message_start":
            turn_item = _pop_pending_turn_item(state, item_id)
            if turn_item is not None:
                _append_stream_event(state, _item_lifecycle_event("item_started", thread_id, turn_id, turn_item))
                state.started_agent_message_item_ids = _sorted_str_tuple(
                    (*state.started_agent_message_item_ids, item_id)
                )
        elif action_type == "agent_message_delta":
            if isinstance(item_id, str) and isinstance(delta, str) and delta:
                _append_stream_event(
                    state,
                    {
                        "type": "agent_message_content_delta",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "item_id": item_id,
                        "delta": delta,
                    },
                )
        elif action_type == "start_plan_item":
            if isinstance(item_id, str):
                state.plan_item_id = item_id
                state.plan_item_started = True
                _append_stream_event(
                    state,
                    _item_lifecycle_event(
                        "item_started",
                        thread_id,
                        turn_id,
                        TurnItem.plan(PlanItem(id=item_id, text="")),
                    ),
                )
        elif action_type == "plan_delta":
            if isinstance(item_id, str) and isinstance(delta, str) and delta:
                _append_stream_event(
                    state,
                    {
                        "type": "plan_delta",
                        "thread_id": thread_id,
                        "turn_id": turn_id,
                        "item_id": item_id,
                        "delta": delta,
                    },
                )
    leading = getattr(segments_plan, "leading_whitespace_by_item_after", ())
    state.leading_whitespace_by_item = tuple(leading or ())
    state.plan_item_started = getattr(segments_plan, "plan_item_started_after", state.plan_item_started)
    state.plan_item_completed = getattr(segments_plan, "plan_item_completed_after", state.plan_item_completed)


def _apply_plan_mode_assistant_done_plan_to_state(
    plan: Any,
    state: SamplingRuntimeEventApplicationState,
    *,
    thread_id: str = "",
    turn_id: str = "",
    completed_item: ResponseItem | None = None,
    completed_turn_item: TurnItem | None = None,
) -> None:
    completion = getattr(plan, "proposed_plan_completion_plan", None)
    if not thread_id:
        thread_id = _event_thread_id_from_state(state)
    if not turn_id:
        turn_id = _event_turn_id_from_state(state)
    if completion is not None:
        item_id = getattr(completion, "plan_item_id", state.plan_item_id)
        plan_text = getattr(completion, "plan_text", "")
        if getattr(completion, "should_start_plan_item", False):
            _append_stream_event(
                state,
                _item_lifecycle_event(
                    "item_started",
                    thread_id,
                    turn_id,
                    TurnItem.plan(PlanItem(id=item_id, text="")),
                ),
            )
        if getattr(completion, "should_complete_plan_item", False):
            _append_stream_event(
                state,
                _item_lifecycle_event(
                    "item_completed",
                    thread_id,
                    turn_id,
                    TurnItem.plan(PlanItem(id=item_id, text=plan_text)),
                ),
            )
        state.plan_item_id = item_id
        state.plan_item_started = getattr(completion, "plan_item_started_after", state.plan_item_started)
        state.plan_item_completed = getattr(completion, "plan_item_completed_after", state.plan_item_completed)

    turn_item_emit = getattr(plan, "turn_item_emit_plan", None)
    contributed_turn_item = _plan_mode_contributed_agent_turn_item(
        plan,
        completed_item,
        turn_item_emit,
        completed_turn_item=completed_turn_item,
    )
    if contributed_turn_item is not None and turn_item_emit is not None:
        turn_item_emit = _replace_attr(turn_item_emit, "turn_item", contributed_turn_item)
    if turn_item_emit is not None:
        _apply_plan_mode_turn_item_emit_plan_to_state(turn_item_emit, state, thread_id=thread_id, turn_id=turn_id)
    if getattr(plan, "should_update_last_agent_message", False):
        if contributed_turn_item is not None and contributed_turn_item.type == "AgentMessage":
            from pycodex.core.stream_events_utils import agent_message_text

            state.result_last_agent_message = agent_message_text(contributed_turn_item.item)
        else:
            state.result_last_agent_message = getattr(plan, "last_agent_message", state.result_last_agent_message)


def _plan_mode_contributed_agent_turn_item(
    plan: Any,
    completed_item: ResponseItem | None,
    turn_item_emit: Any,
    *,
    completed_turn_item: TurnItem | None = None,
) -> TurnItem | None:
    turn_item = completed_turn_item
    if not isinstance(turn_item, TurnItem):
        turn_item = getattr(turn_item_emit, "turn_item", None)
    if not isinstance(turn_item, TurnItem):
        turn_item = _assistant_response_item_to_agent_turn_item(completed_item)
    if turn_item is None or turn_item.type != "AgentMessage":
        return None

    sess = getattr(plan, "sess", None)
    if sess is None:
        sess = getattr(plan, "session", None)
    if sess is None:
        return turn_item
    turn_store = getattr(plan, "turn_store", None)

    from pycodex.core.stream_events_utils import apply_turn_item_contributors

    contributed = apply_turn_item_contributors(sess, turn_store, turn_item)
    if isawaitable(contributed):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            contributed = asyncio.run(contributed)
        else:
            raise RuntimeError("plan mode turn item contributors require an async event-plan application path")
    if not isinstance(contributed, TurnItem):
        raise TypeError("turn item contributors must return a TurnItem")
    return contributed


def _completed_response_item_to_turn_item(item: ResponseItem | None) -> TurnItem | None:
    # Rust stream_events_utils::handle_output_item_done finalizes every
    # parseable non-tool item, including reasoning and hosted-tool results.
    if not isinstance(item, ResponseItem):
        return None
    return parse_turn_item(item)


def _assistant_response_item_to_agent_turn_item(item: ResponseItem | None) -> TurnItem | None:
    if not isinstance(item, ResponseItem) or item.type != "message" or item.role != "assistant":
        return None
    content = tuple(
        AgentMessageContent.text_content(content_item.text or "")
        for content_item in item.content
        if isinstance(content_item, ContentItem) and content_item.type == "output_text"
    )
    if not content:
        return None
    return TurnItem.agent_message(AgentMessageItem(item.id or "", content, phase=item.phase))


def _replace_attr(value: Any, name: str, replacement: Any) -> Any:
    try:
        return replace(value, **{name: replacement})
    except TypeError:
        if hasattr(value, "__dict__"):
            clone = type("_PlanAttrReplacement", (), {})()
            clone.__dict__.update(value.__dict__)
            setattr(clone, name, replacement)
            return clone
        return value


def _apply_plan_mode_turn_item_emit_plan_to_state(
    plan: Any,
    state: SamplingRuntimeEventApplicationState,
    *,
    thread_id: str,
    turn_id: str,
) -> None:
    turn_item = getattr(plan, "turn_item", None)
    agent_plan = getattr(plan, "agent_message_plan", None)
    if agent_plan is not None:
        if getattr(agent_plan, "should_drop_empty_agent_message", False):
            _remove_pending_turn_item(state, getattr(agent_plan, "item_id", None))
            state.started_agent_message_item_ids = tuple(
                item_id
                for item_id in state.started_agent_message_item_ids
                if item_id != getattr(agent_plan, "item_id", None)
            )
            return
        pending_start = getattr(agent_plan, "pending_start_plan", None)
        if pending_start is not None:
            start_item = getattr(pending_start, "turn_item_to_start", None)
            if isinstance(start_item, TurnItem):
                _append_stream_event(state, _item_lifecycle_event("item_started", thread_id, turn_id, start_item))
                _remove_pending_turn_item(state, getattr(pending_start, "item_id", None))
        fallback = getattr(agent_plan, "fallback_start_item", None)
        if isinstance(fallback, TurnItem):
            _append_stream_event(state, _item_lifecycle_event("item_started", thread_id, turn_id, fallback))
        if getattr(agent_plan, "should_emit_completed", False) and isinstance(turn_item, TurnItem):
            _append_stream_event(state, _item_lifecycle_event("item_completed", thread_id, turn_id, turn_item))
        state.started_agent_message_item_ids = tuple(getattr(agent_plan, "started_agent_message_item_ids_after", ()))
        remaining = set(getattr(agent_plan, "pending_agent_message_item_ids_after", ()))
        state.pending_agent_message_items = tuple(
            item for item in state.pending_agent_message_items if _turn_item_id(item) in remaining
        )
        return
    if isinstance(turn_item, TurnItem):
        if getattr(plan, "should_emit_started", False):
            _append_stream_event(state, _item_lifecycle_event("item_started", thread_id, turn_id, turn_item))
        if getattr(plan, "should_emit_completed", False):
            _append_stream_event(state, _item_lifecycle_event("item_completed", thread_id, turn_id, turn_item))


def _append_stream_event(state: SamplingRuntimeEventApplicationState, event: dict[str, Any]) -> None:
    state.emitted_stream_events = state.emitted_stream_events + (event,)
    if event.get("type") in {"plan_delta", "item_started", "item_completed"}:
        state.plan_events = state.plan_events + (event,)


def _item_lifecycle_event(event_type: str, thread_id: str, turn_id: str, item: TurnItem) -> dict[str, Any]:
    timestamp_ms = int(time.time() * 1000)
    return {
        "type": event_type,
        "thread_id": thread_id,
        "turn_id": turn_id,
        "item": item.to_mapping(),
        "started_at_ms": timestamp_ms if event_type == "item_started" else 0,
        "completed_at_ms": timestamp_ms if event_type == "item_completed" else 0,
    }


def _replace_pending_turn_item(pending_items: Sequence[Any], item: Any) -> tuple[Any, ...]:
    item_id = _turn_item_id(item)
    if item_id is None:
        return tuple(pending_items)
    kept = tuple(candidate for candidate in pending_items if _turn_item_id(candidate) != item_id)
    return kept + (item,)


def _remove_pending_turn_item(state: SamplingRuntimeEventApplicationState, item_id: Any) -> None:
    if not isinstance(item_id, str):
        return
    state.pending_agent_message_items = tuple(
        item for item in state.pending_agent_message_items if _turn_item_id(item) != item_id
    )
    current = state.pending_agent_message_item
    if _turn_item_id(current) == item_id:
        state.pending_agent_message_item = None


def _pop_pending_turn_item(state: SamplingRuntimeEventApplicationState, item_id: Any) -> TurnItem | None:
    if not isinstance(item_id, str):
        return None
    for item in state.pending_agent_message_items:
        if _turn_item_id(item) == item_id and isinstance(item, TurnItem):
            _remove_pending_turn_item(state, item_id)
            return item
    current = state.pending_agent_message_item
    if _turn_item_id(current) == item_id and isinstance(current, TurnItem):
        _remove_pending_turn_item(state, item_id)
        return current
    return None


def _turn_item_id(item: Any) -> str | None:
    if isinstance(item, TurnItem):
        return item.id()
    item_id = getattr(item, "id", None)
    return item_id if isinstance(item_id, str) else None


def _sorted_str_tuple(values: Sequence[Any]) -> tuple[str, ...]:
    return tuple(sorted({value for value in values if isinstance(value, str)}))


def _event_thread_id_from_state(state: SamplingRuntimeEventApplicationState) -> str:
    for event in reversed(state.emitted_stream_events):
        if isinstance(event, Mapping) and isinstance(event.get("thread_id"), str):
            return event["thread_id"]
    return ""


def _event_turn_id_from_state(state: SamplingRuntimeEventApplicationState) -> str:
    for event in reversed(state.emitted_stream_events):
        if isinstance(event, Mapping) and isinstance(event.get("turn_id"), str):
            return event["turn_id"]
    return ""


def _streamed_assistant_text_plan_from_flush_item(
    item_plan: Any,
    *,
    thread_id: str = "",
    turn_id: str = "",
) -> Any:
    parsed = getattr(item_plan, "parsed", None)
    visible_text = _parsed_field_for_client(parsed, "visible_text", "")
    if visible_text is None:
        visible_text = ""
    citations = _parsed_str_sequence_field_for_client(parsed, "citations")
    if not isinstance(visible_text, str) or (visible_text == "" and not citations):
        return None
    from pycodex.core.stream_events_utils import SamplingStreamedAssistantTextDeltaPlan

    return SamplingStreamedAssistantTextDeltaPlan(
        item_id=getattr(item_plan, "item_id", ""),
        visible_text_delta=visible_text if visible_text else None,
        citations=citations,
        ignored_citations=bool(citations),
        thread_id=thread_id,
        turn_id=turn_id,
    )


def _parsed_field_for_client(parsed: Any, name: str, default: Any) -> Any:
    if isinstance(parsed, Mapping):
        return parsed.get(name, default)
    return getattr(parsed, name, default)


def _parsed_str_sequence_field_for_client(parsed: Any, name: str) -> tuple[str, ...]:
    value = _parsed_field_for_client(parsed, name, ())
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return tuple(str(item) for item in value)
    return ()


def _sampling_result_from_event_application_state(
    state: SamplingRuntimeEventApplicationState,
) -> dict[str, Any]:
    if not isinstance(state, SamplingRuntimeEventApplicationState):
        raise TypeError("state must be a SamplingRuntimeEventApplicationState")
    return {
        "needs_follow_up": state.result_needs_follow_up,
        "last_agent_message": state.result_last_agent_message,
    }


def sampling_post_drain_tail_plan(
    *,
    should_emit_token_count: bool,
    cancellation_requested: bool,
    should_emit_turn_diff: bool,
    unified_diff: str | None,
) -> SamplingPostDrainTailPlan:
    actions = tuple(
        sampling_turn_tail_actions(
            should_emit_token_count=should_emit_token_count,
            cancellation_requested=cancellation_requested,
            should_emit_turn_diff=should_emit_turn_diff,
            unified_diff=unified_diff,
        )
    )
    return SamplingPostDrainTailPlan(
        actions=actions,
        should_send_token_count_before_cancellation=should_emit_token_count,
        should_return_turn_aborted=cancellation_requested,
        should_read_turn_diff=not cancellation_requested and should_emit_turn_diff,
        should_emit_turn_diff=not cancellation_requested and should_emit_turn_diff and unified_diff is not None,
    )


def sampling_loop_tail_plan(
    features: Any,
    *,
    outcome_ok: bool,
    completed_response_id: str | None,
    should_emit_token_count: bool,
    cancellation_requested: bool,
    should_emit_turn_diff: bool,
    unified_diff: str | None,
) -> SamplingLoopTailPlan:
    response_processed = response_processed_request_for_sampling_turn(
        features,
        outcome_ok=outcome_ok,
        completed_response_id=completed_response_id,
    )
    post_drain = sampling_post_drain_tail_plan(
        should_emit_token_count=should_emit_token_count,
        cancellation_requested=cancellation_requested,
        should_emit_turn_diff=should_emit_turn_diff,
        unified_diff=unified_diff,
    )
    return SamplingLoopTailPlan(
        response_processed_request=response_processed,
        should_drain_in_flight=True,
        post_drain_tail_plan=post_drain,
    )


def sampling_loop_tail_plan_from_runtime_state(
    features: Any,
    state: SamplingRuntimeEventApplicationState,
    *,
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
) -> SamplingLoopTailPlan:
    if not isinstance(state, SamplingRuntimeEventApplicationState):
        raise TypeError("state must be a SamplingRuntimeEventApplicationState")
    return sampling_loop_tail_plan(
        features,
        outcome_ok=outcome_ok,
        completed_response_id=state.completed_response_id,
        should_emit_token_count=state.should_emit_token_count,
        cancellation_requested=cancellation_requested,
        should_emit_turn_diff=state.should_emit_turn_diff,
        unified_diff=unified_diff,
    )


def sampling_request_runtime_tail_plan_from_state(
    features: Any,
    state: SamplingRuntimeEventApplicationState,
    *,
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
) -> SamplingRequestRuntimePlan:
    if not isinstance(state, SamplingRuntimeEventApplicationState):
        raise TypeError("state must be a SamplingRuntimeEventApplicationState")

    loop_tail = sampling_loop_tail_plan_from_runtime_state(
        features,
        state,
        outcome_ok=outcome_ok,
        cancellation_requested=cancellation_requested,
        unified_diff=unified_diff,
    )

    steps: list[dict[str, Any]] = []
    hooks: list[str] = []

    def add_hook(name: str) -> None:
        if name not in hooks:
            hooks.append(name)

    if loop_tail.response_processed_request is not None:
        steps.append(
            {
                "type": "send_response_processed",
                "request": loop_tail.response_processed_request,
            }
        )
        add_hook("send_response_processed")

    if loop_tail.should_drain_in_flight:
        steps.append({"type": "drain_in_flight"})
        add_hook("drain_in_flight")

    post_drain = loop_tail.post_drain_tail_plan
    should_return_turn_aborted = False
    if post_drain is not None:
        should_return_turn_aborted = post_drain.should_return_turn_aborted
        for action in post_drain.actions:
            action_type = action.get("type")
            if action_type == "send_token_count":
                steps.append({"type": "send_token_count"})
                add_hook("send_token_count")
            elif action_type == "turn_diff":
                steps.append(
                    {
                        "type": "send_turn_diff",
                        "unified_diff": action.get("unified_diff"),
                    }
                )
                add_hook("send_turn_diff")
            elif action_type == "turn_aborted":
                steps.append({"type": "return_turn_aborted"})
                add_hook("return_turn_aborted")
            else:
                steps.append({"type": "unknown_tail_action", "action": action})
                add_hook("handle_unknown_tail_action")

    if not should_return_turn_aborted:
        steps.append(
            {
                "type": "return_sampling_result",
                "needs_follow_up": state.result_needs_follow_up,
                "last_agent_message": state.result_last_agent_message,
            }
        )
        add_hook("return_sampling_result")

    return SamplingRequestRuntimePlan(
        steps=tuple(steps),
        required_hooks=tuple(hooks),
    )


def sampling_request_plan(
    *,
    event_apply_plans: Sequence[Any],
    loop_tail_plan: SamplingLoopTailPlan,
    outcome_ok: bool,
    result_needs_follow_up: bool,
    result_last_agent_message: str | None = None,
    completed_response_id: str | None = None,
) -> SamplingRequestPlan:
    if not isinstance(loop_tail_plan, SamplingLoopTailPlan):
        raise TypeError("loop_tail_plan must be a SamplingLoopTailPlan")
    if not isinstance(outcome_ok, bool):
        raise TypeError("outcome_ok must be a bool")
    if not isinstance(result_needs_follow_up, bool):
        raise TypeError("result_needs_follow_up must be a bool")
    if result_last_agent_message is not None and not isinstance(result_last_agent_message, str):
        raise TypeError("result_last_agent_message must be a string or None")
    if completed_response_id is not None and not isinstance(completed_response_id, str):
        raise TypeError("completed_response_id must be a string or None")
    post_drain = loop_tail_plan.post_drain_tail_plan
    should_return_turn_aborted = post_drain.should_return_turn_aborted if post_drain is not None else False
    return SamplingRequestPlan(
        event_apply_plans=tuple(event_apply_plans),
        loop_tail_plan=loop_tail_plan,
        outcome_ok=outcome_ok,
        result_needs_follow_up=result_needs_follow_up,
        result_last_agent_message=result_last_agent_message,
        completed_response_id=completed_response_id,
        should_return_turn_aborted=should_return_turn_aborted,
    )


def sampling_request_runtime_plan(
    request_plan: SamplingRequestPlan,
) -> SamplingRequestRuntimePlan:
    if not isinstance(request_plan, SamplingRequestPlan):
        raise TypeError("request_plan must be a SamplingRequestPlan")

    steps: list[dict[str, Any]] = []
    hooks: list[str] = []

    def add_hook(name: str) -> None:
        if name not in hooks:
            hooks.append(name)

    for event_plan in request_plan.event_apply_plans:
        steps.append(
            {
                "type": "apply_event_plan",
                "event_type": getattr(event_plan, "event_type", None),
                "plan": event_plan,
            }
        )
        add_hook("apply_event_plan")

    loop_tail = request_plan.loop_tail_plan
    if loop_tail.response_processed_request is not None:
        steps.append(
            {
                "type": "send_response_processed",
                "request": loop_tail.response_processed_request,
            }
        )
        add_hook("send_response_processed")

    if loop_tail.should_drain_in_flight:
        steps.append({"type": "drain_in_flight"})
        add_hook("drain_in_flight")

    post_drain = loop_tail.post_drain_tail_plan
    if post_drain is not None:
        for action in post_drain.actions:
            action_type = action.get("type")
            if action_type == "send_token_count":
                steps.append({"type": "send_token_count"})
                add_hook("send_token_count")
            elif action_type == "turn_diff":
                steps.append(
                    {
                        "type": "send_turn_diff",
                        "unified_diff": action.get("unified_diff"),
                    }
                )
                add_hook("send_turn_diff")
            elif action_type == "turn_aborted":
                steps.append({"type": "return_turn_aborted"})
                add_hook("return_turn_aborted")
            else:
                steps.append({"type": "unknown_tail_action", "action": action})
                add_hook("handle_unknown_tail_action")

    if not request_plan.should_return_turn_aborted:
        steps.append(
            {
                "type": "return_sampling_result",
                "needs_follow_up": request_plan.result_needs_follow_up,
                "last_agent_message": request_plan.result_last_agent_message,
            }
        )
        add_hook("return_sampling_result")

    return SamplingRequestRuntimePlan(
        steps=tuple(steps),
        required_hooks=tuple(hooks),
    )


def execute_sampling_request_runtime_plan(
    runtime_plan: SamplingRequestRuntimePlan,
    hooks: Any,
) -> SamplingRequestRuntimeExecutionResult:
    if not isinstance(runtime_plan, SamplingRequestRuntimePlan):
        raise TypeError("runtime_plan must be a SamplingRequestRuntimePlan")

    step_results: list[dict[str, Any]] = []
    final_result: Any = None
    returned_turn_aborted = False

    for step in runtime_plan.steps:
        step_type = step.get("type")
        if not isinstance(step_type, str):
            raise TypeError("runtime step type must be a string")
        hook = getattr(hooks, step_type, None)
        if not callable(hook):
            raise TypeError(f"hooks must provide callable {step_type}")
        result = hook(step)
        step_results.append(
            {
                "type": step_type,
                "result": result,
            }
        )
        if step_type == "return_sampling_result":
            final_result = result
        elif step_type == "return_turn_aborted":
            final_result = result
            returned_turn_aborted = True

    return SamplingRequestRuntimeExecutionResult(
        step_results=tuple(step_results),
        final_result=final_result,
        returned_turn_aborted=returned_turn_aborted,
    )


def execute_sampling_request_runtime_tail_plan_from_state(
    features: Any,
    state: SamplingRuntimeEventApplicationState,
    hooks: Any | None = None,
    *,
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
) -> SamplingRequestRuntimeExecutionResult:
    if hooks is None:
        hooks = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    runtime_plan = sampling_request_runtime_tail_plan_from_state(
        features,
        state,
        outcome_ok=outcome_ok,
        cancellation_requested=cancellation_requested,
        unified_diff=unified_diff,
    )
    return execute_sampling_request_runtime_plan(runtime_plan, hooks)


def _sampling_runtime_state_phase_summary(state: SamplingRuntimeEventApplicationState) -> dict[str, Any]:
    return {
        "applied_event_types": state.applied_event_types,
        "completed_response_id": state.completed_response_id,
        "result_needs_follow_up": state.result_needs_follow_up,
        "result_last_agent_message": state.result_last_agent_message,
        "should_emit_token_count": state.should_emit_token_count,
        "should_emit_turn_diff": state.should_emit_turn_diff,
        "should_continue_loop": state.should_continue_loop,
        "preempt_for_mailbox_mail": state.preempt_for_mailbox_mail,
        "metadata_state": {
            "has_token_usage_to_record": state.token_usage_to_record is not None,
            "server_reasoning_included": state.server_reasoning_included,
            "has_rate_limits_to_record": state.rate_limits_to_record is not None,
            "models_etag_to_refresh": state.models_etag_to_refresh,
        },
        "follow_up_state": {
            "needs_follow_up": state.result_needs_follow_up,
            "last_agent_message": state.result_last_agent_message,
            "has_output_result": state.output_result is not None,
            "has_state_after_output_result": state.state_after_output_result is not None,
            "has_mailbox_preemption_plan": state.mailbox_preemption_plan is not None,
        },
        "stream_event_counts": {
            "metadata": len(state.metadata_events),
            "output_item_done": len(state.output_item_done_events),
            "completed_output_items": len(state.completed_output_items),
            "output_item_added": len(state.output_item_added_events),
            "output_text_delta": len(state.output_text_delta_events),
            "assistant_text_delta": len(state.assistant_text_deltas),
            "raw_content_delta": len(state.raw_content_deltas),
            "tool_call_input_delta": len(state.tool_call_input_delta_events),
            "reasoning_delta": len(state.reasoning_delta_events),
            "emitted_stream": len(state.emitted_stream_events),
        },
    }


def _sampling_runtime_step_types(result: SamplingRequestRuntimeExecutionResult) -> tuple[str | None, ...]:
    return tuple(step.get("type") for step in result.step_results)


def _sampling_runtime_last_response_items_added(state: SamplingRuntimeEventApplicationState) -> tuple[ResponseItem, ...]:
    items: list[ResponseItem] = []
    for item in state.completed_output_items:
        if item not in items:
            items.append(item)
    for candidate in (
        state.pending_agent_message_item,
        state.turn_item_started_to_emit,
        state.active_item,
    ):
        if isinstance(candidate, ResponseItem) and candidate not in items:
            items.append(candidate)
    return tuple(items)


def _field_or_key(value: Any, field: str, default: Any = 0) -> Any:
    if isinstance(value, Mapping):
        return value.get(field, default)
    return getattr(value, field, default)


def _record_websocket_completed_telemetry(session_telemetry: Any, token_usage: Any) -> dict[str, Any] | None:
    if token_usage is None:
        return None
    input_tokens = _field_or_key(token_usage, "input_tokens", 0)
    output_tokens = _field_or_key(token_usage, "output_tokens", 0)
    cached_input_tokens = _field_or_key(token_usage, "cached_input_tokens", 0)
    reasoning_output_tokens = _field_or_key(token_usage, "reasoning_output_tokens", 0)
    total_tokens = _field_or_key(token_usage, "total_tokens", _field_or_key(token_usage, "total", 0))
    recorder = getattr(session_telemetry, "sse_event_completed", None)
    if callable(recorder):
        recorder(
            input_tokens,
            output_tokens,
            cached_input_tokens,
            reasoning_output_tokens,
            total_tokens,
        )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cached_input_tokens": cached_input_tokens,
        "reasoning_output_tokens": reasoning_output_tokens,
        "total_tokens": total_tokens,
        "recorded": callable(recorder),
    }


def _record_websocket_failed_telemetry(session_telemetry: Any, error_message: str) -> dict[str, Any]:
    recorder = getattr(session_telemetry, "see_event_completed_failed", None)
    if callable(recorder):
        recorder(error_message)
    return {
        "error": error_message,
        "recorded": callable(recorder),
    }


def execute_sampling_request_runtime_state_driven_plan(
    features: Any,
    *,
    event_apply_plans: Sequence[Any],
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
    state: SamplingRuntimeEventApplicationState | None = None,
    hooks: Any | None = None,
) -> SamplingRequestRuntimeExecutionResult:
    if state is None:
        state = SamplingRuntimeEventApplicationState()
    if not isinstance(state, SamplingRuntimeEventApplicationState):
        raise TypeError("state must be a SamplingRuntimeEventApplicationState or None")
    if hooks is None:
        hooks = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    elif isinstance(hooks, SamplingRequestRuntimeHookAdapter):
        if hooks.event_application_state is None:
            hooks.event_application_state = state
        elif hooks.event_application_state is not state:
            raise TypeError("hooks event_application_state must match state")

    event_step_results: list[dict[str, Any]] = []
    event_summaries: list[dict[str, Any]] = []
    event_returned_turn_aborted = False
    for event_plan in event_apply_plans:
        event_type = getattr(event_plan, "event_type", None)
        event_result = execute_sampling_request_runtime_plan(
            SamplingRequestRuntimePlan(
                steps=(
                    {
                        "type": "apply_event_plan",
                        "event_type": event_type,
                        "plan": event_plan,
                    },
                ),
                required_hooks=("apply_event_plan",),
            ),
            hooks,
        )
        event_step_results.extend(event_result.step_results)
        event_summaries.append(
            {
                "event_type": event_type,
                "state_after": _sampling_runtime_state_phase_summary(state),
            }
        )
        event_returned_turn_aborted = event_returned_turn_aborted or event_result.returned_turn_aborted
    tail_result = execute_sampling_request_runtime_tail_plan_from_state(
        features,
        state,
        hooks,
        outcome_ok=outcome_ok,
        cancellation_requested=cancellation_requested,
        unified_diff=unified_diff,
    )
    return SamplingRequestRuntimeExecutionResult(
        step_results=tuple(event_step_results) + tail_result.step_results,
        final_result=tail_result.final_result,
        returned_turn_aborted=tail_result.returned_turn_aborted,
        phase_results=(
            {
                "phase": "event_apply",
                "step_count": len(event_step_results),
                "step_types": tuple(step.get("type") for step in event_step_results),
                "event_summaries": tuple(event_summaries),
                "state_after": _sampling_runtime_state_phase_summary(state),
                "returned_turn_aborted": event_returned_turn_aborted,
            },
            {
                "phase": "tail",
                "step_count": len(tail_result.step_results),
                "step_types": _sampling_runtime_step_types(tail_result),
                "state_after": _sampling_runtime_state_phase_summary(state),
                "returned_turn_aborted": tail_result.returned_turn_aborted,
            },
        ),
    )


def execute_sampling_request_runtime_state_driven_session_plan(
    session: ModelClientSession,
    features: Any,
    *,
    event_apply_plans: Sequence[Any],
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
    state: SamplingRuntimeEventApplicationState | None = None,
    request: Mapping[str, Any] | None = None,
    completed_response_from_untraced_warmup: bool = False,
    **hook_overrides: Any,
) -> SamplingRequestRuntimeExecutionResult:
    if not isinstance(session, ModelClientSession):
        raise TypeError("session must be a ModelClientSession")
    if request is not None and not isinstance(request, Mapping):
        raise TypeError("request must be a mapping or None")
    if not isinstance(completed_response_from_untraced_warmup, bool):
        raise TypeError("completed_response_from_untraced_warmup must be a bool")
    if state is None:
        state = SamplingRuntimeEventApplicationState()
    adapter = session.sampling_request_runtime_hook_adapter(state=state, **hook_overrides)
    result = execute_sampling_request_runtime_state_driven_plan(
        features,
        event_apply_plans=event_apply_plans,
        outcome_ok=outcome_ok,
        cancellation_requested=cancellation_requested,
        unified_diff=unified_diff,
        state=state,
        hooks=adapter,
    )
    if not result.returned_turn_aborted and state.completed_response_id is not None:
        session.websocket_session.last_response = LastResponse(
            state.completed_response_id,
            _sampling_runtime_last_response_items_added(state),
        )
        session.websocket_session.last_response_from_untraced_warmup = completed_response_from_untraced_warmup
        if request is not None:
            session.websocket_session.last_request = dict(request)
    return result


def prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
    session: ModelClientSession,
    features: Any,
    *,
    payload: Mapping[str, Any],
    request: Mapping[str, Any],
    event_apply_plans: Sequence[Any],
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
    state: SamplingRuntimeEventApplicationState | None = None,
    websocket_outcome: WebsocketStreamOutcome = WebsocketStreamOutcome.STREAM,
    session_telemetry: Any = None,
    model_info: Any = None,
    warmup: bool = False,
    websocket_connection_needs_new: bool | None = None,
    websocket_connection: Any = None,
    websocket_connection_error: Any = None,
    websocket_connection_timeout: bool = False,
    trace: Any | None = None,
    turn_metadata_header: str | None = None,
    stamp_websocket_request_start_ms: bool = True,
    websocket_stream_error: Any = None,
    websocket_mapped_stream_error: Any = None,
    websocket_stream_closed_before_completed: bool = False,
    websocket_consumer_dropped: bool = False,
    websocket_upstream_request_id: str | None = None,
    websocket_error_request_id: str | None = None,
    **hook_overrides: Any,
) -> SamplingRequestRuntimeSessionLifecycleResult:
    if not isinstance(session, ModelClientSession):
        raise TypeError("session must be a ModelClientSession")
    if not isinstance(websocket_outcome, WebsocketStreamOutcome):
        raise TypeError("websocket_outcome must be WebsocketStreamOutcome")
    if not isinstance(warmup, bool):
        raise TypeError("warmup must be a bool")
    if websocket_connection_needs_new is not None and not isinstance(websocket_connection_needs_new, bool):
        raise TypeError("websocket_connection_needs_new must be a bool or None")
    if not isinstance(websocket_connection_timeout, bool):
        raise TypeError("websocket_connection_timeout must be a bool")
    if not isinstance(stamp_websocket_request_start_ms, bool):
        raise TypeError("stamp_websocket_request_start_ms must be a bool")
    if not isinstance(websocket_stream_closed_before_completed, bool):
        raise TypeError("websocket_stream_closed_before_completed must be a bool")
    if not isinstance(websocket_consumer_dropped, bool):
        raise TypeError("websocket_consumer_dropped must be a bool")
    if websocket_upstream_request_id is not None and not isinstance(websocket_upstream_request_id, str):
        raise TypeError("websocket_upstream_request_id must be a string or None")
    if websocket_error_request_id is not None and not isinstance(websocket_error_request_id, str):
        raise TypeError("websocket_error_request_id must be a string or None")
    if state is None:
        state = SamplingRuntimeEventApplicationState()
    effective_websocket_connection_needs_new = (
        websocket_connection_needs_new
        if websocket_connection_needs_new is not None
        else session.websocket_connection_needs_new()
    )
    websocket_connection_lifecycle = (
        session.apply_websocket_connection_lifecycle(
            effective_websocket_connection_needs_new,
            connection=websocket_connection,
        )
    )
    websocket_connection_failure = None
    if websocket_connection_error is not None:
        websocket_connection_failure = {
            "error": str(websocket_connection_error),
            "timeout": websocket_connection_timeout,
        }
        if websocket_connection_timeout:
            session.reset_websocket_session()
            if websocket_connection_lifecycle is None:
                websocket_connection_lifecycle = {
                    "needs_new": True,
                    "connection_reused": False,
                    "incremental_state_reset": True,
                }
            websocket_connection_lifecycle = {
                **websocket_connection_lifecycle,
                "connection_failure_reset": True,
            }
    websocket_connection_reused = session.websocket_session.connection_reused()
    websocket_payload = session.client.build_websocket_payload(
        payload,
        trace=trace,
        turn_metadata_header=turn_metadata_header,
    )
    websocket_request, from_untraced_warmup = session.prepare_websocket_request(websocket_payload, request)
    websocket_request_start_ms_stamped = False
    if stamp_websocket_request_start_ms:
        stamp_ws_stream_request_start_ms(websocket_request)
        websocket_request_start_ms_stamped = (
            websocket_request.get("type") == "response.create"
            and X_CODEX_WS_STREAM_REQUEST_START_MS_CLIENT_METADATA_KEY
            in websocket_request.get("client_metadata", {})
        )
    inference_trace_started_request = dict(request) if from_untraced_warmup else dict(websocket_request)
    inference_trace_started_request_source = "logical_request" if from_untraced_warmup else "websocket_request"
    session.websocket_session.last_request = dict(request)
    session.websocket_session.last_response_from_untraced_warmup = warmup
    websocket_last_request_recorded = True
    websocket_stream_request_attempt = {
        "request": websocket_request,
        "connection_available": session.websocket_session.connection is not None,
        "connection_reused": websocket_connection_reused,
    }
    if websocket_connection_failure is not None:
        websocket_stream_request_attempt["connection_failure"] = websocket_connection_failure
    websocket_stream_request_attempt_outcome = (
        {"status": "ready", "error": None}
        if websocket_stream_request_attempt["connection_available"]
        else {
            "status": "blocked",
            "error": "websocket connection is unavailable",
        }
    )
    inference_trace_failed = None
    if websocket_stream_request_attempt_outcome["status"] == "ready" and websocket_stream_error is not None:
        error_message = str(websocket_stream_error)
        websocket_stream_request_attempt_outcome = {
            "status": "failed",
            "error": error_message,
        }
        inference_trace_failed = {
            "error": error_message,
            "request_id": None,
            "output_items": (),
        }
    websocket_last_response_receiver_registered = (
        websocket_stream_request_attempt_outcome["status"] == "ready"
    )
    if websocket_last_response_receiver_registered:
        session.websocket_session.last_response_pending = True
    websocket_feedback_tags: dict[str, str] = {}
    if websocket_upstream_request_id is not None:
        websocket_feedback_tags["last_model_request_id"] = websocket_upstream_request_id
    websocket_stream_result = (
        {
            "status": "stream",
            "stream_mapped": True,
            "last_response_receiver_registered": True,
        }
        if websocket_last_response_receiver_registered
        else {
            "status": websocket_stream_request_attempt_outcome["status"],
            "stream_mapped": False,
            "last_response_receiver_registered": False,
        }
    )
    http_fallback_activated = False
    if websocket_outcome == WebsocketStreamOutcome.FALLBACK_TO_HTTP:
        http_fallback_activated = session.client.force_http_fallback(
            session_telemetry=session_telemetry,
            model_info=model_info,
        )
        session.reset_websocket_session()
    http_request = (
        session.prepare_http_request(request)
        if websocket_outcome == WebsocketStreamOutcome.FALLBACK_TO_HTTP
        else None
    )
    runtime_event_apply_plans = (
        ()
        if (
            websocket_outcome != WebsocketStreamOutcome.FALLBACK_TO_HTTP
            and websocket_stream_request_attempt_outcome["status"] != "ready"
        )
        else event_apply_plans
    )
    runtime_result = execute_sampling_request_runtime_state_driven_session_plan(
        session,
        features,
        event_apply_plans=runtime_event_apply_plans,
        outcome_ok=outcome_ok,
        cancellation_requested=cancellation_requested,
        unified_diff=unified_diff,
        state=state,
        request=request,
        completed_response_from_untraced_warmup=warmup,
        **hook_overrides,
    )
    if websocket_stream_request_attempt_outcome["status"] != "ready":
        session.websocket_session.last_response = None
        session.websocket_session.last_response_pending = False
    if websocket_outcome == WebsocketStreamOutcome.FALLBACK_TO_HTTP:
        session.reset_websocket_session()
    websocket_response_processed_request = response_processed_request_for_sampling_turn(
        features,
        outcome_ok=outcome_ok,
        completed_response_id=state.completed_response_id,
    )
    websocket_response_processed_result = None
    for step_result in runtime_result.step_results:
        if step_result.get("type") == "send_response_processed":
            websocket_response_processed_result = step_result.get("result")
            break
    inference_trace_cancelled = None
    websocket_failed_telemetry = None
    if (
        websocket_consumer_dropped
        and websocket_stream_result["status"] == "stream"
        and state.completed_response_id is None
    ):
        session.websocket_session.last_response_pending = False
        inference_trace_cancelled = {
            "reason": "response stream dropped before provider terminal event",
            "request_id": websocket_upstream_request_id,
            "output_items": state.completed_output_items,
        }
        websocket_stream_result = {
            "status": "cancelled",
            "stream_mapped": True,
            "last_response_receiver_registered": websocket_last_response_receiver_registered,
            "terminal_event": "consumer_dropped",
        }
    if (
        websocket_mapped_stream_error is not None
        and websocket_stream_result["status"] == "stream"
        and state.completed_response_id is None
    ):
        error_message = str(websocket_mapped_stream_error)
        error_request_id = websocket_upstream_request_id or websocket_error_request_id
        if error_request_id is not None:
            websocket_feedback_tags["last_model_request_id"] = error_request_id
        session.websocket_session.last_response_pending = False
        websocket_failed_telemetry = _record_websocket_failed_telemetry(
            session_telemetry,
            error_message,
        )
        inference_trace_failed = {
            "error": error_message,
            "request_id": error_request_id,
            "output_items": state.completed_output_items,
        }
        websocket_stream_result = {
            "status": "failed",
            "stream_mapped": True,
            "last_response_receiver_registered": websocket_last_response_receiver_registered,
            "terminal_event": "api_error",
        }
    if (
        websocket_stream_closed_before_completed
        and websocket_stream_result["status"] == "stream"
        and state.completed_response_id is None
    ):
        session.websocket_session.last_response_pending = False
        inference_trace_failed = {
            "error": "stream closed before response.completed",
            "request_id": websocket_upstream_request_id,
            "output_items": state.completed_output_items,
        }
        websocket_stream_result = {
            "status": "failed",
            "stream_mapped": True,
            "last_response_receiver_registered": websocket_last_response_receiver_registered,
            "terminal_event": "missing_response_completed",
        }
    inference_trace_completed = None
    websocket_completed_telemetry = None
    if websocket_stream_result["status"] == "stream" and state.completed_response_id is not None:
        websocket_feedback_tags["last_model_response_id"] = state.completed_response_id
        inference_trace_completed = {
            "response_id": state.completed_response_id,
            "request_id": websocket_upstream_request_id,
            "token_usage": state.token_usage_to_record,
            "output_items": _sampling_runtime_last_response_items_added(state),
        }
        websocket_completed_telemetry = _record_websocket_completed_telemetry(
            session_telemetry,
            state.token_usage_to_record,
        )
    websocket_last_response_delivery = None
    if (
        websocket_stream_result["status"] == "stream"
        and session.websocket_session.last_response is not None
    ):
        websocket_last_response_delivery = {
            "response_id": session.websocket_session.last_response.response_id,
            "items_added": session.websocket_session.last_response.items_added,
            "receiver_pending": session.websocket_session.last_response_pending,
        }
    return SamplingRequestRuntimeSessionLifecycleResult(
        websocket_request=websocket_request,
        from_untraced_warmup=from_untraced_warmup,
        runtime_result=runtime_result,
        websocket_outcome=websocket_outcome,
        http_request=http_request,
        http_fallback_activated=http_fallback_activated,
        runtime_state_summary=_sampling_runtime_state_phase_summary(state),
        completed_response_from_untraced_warmup=warmup,
        websocket_connection_reused=websocket_connection_reused,
        websocket_connection_lifecycle=websocket_connection_lifecycle,
        websocket_request_start_ms_stamped=websocket_request_start_ms_stamped,
        inference_trace_started_request=inference_trace_started_request,
        inference_trace_started_request_source=inference_trace_started_request_source,
        websocket_last_request_recorded=websocket_last_request_recorded,
        websocket_stream_request_attempt=websocket_stream_request_attempt,
        websocket_stream_request_attempt_outcome=websocket_stream_request_attempt_outcome,
        websocket_last_response_receiver_registered=websocket_last_response_receiver_registered,
        inference_trace_completed=inference_trace_completed,
        inference_trace_failed=inference_trace_failed,
        inference_trace_cancelled=inference_trace_cancelled,
        websocket_stream_result=websocket_stream_result,
        websocket_last_response_delivery=websocket_last_response_delivery,
        websocket_completed_telemetry=websocket_completed_telemetry,
        websocket_failed_telemetry=websocket_failed_telemetry,
        websocket_feedback_tags=websocket_feedback_tags or None,
        websocket_response_processed_request=websocket_response_processed_request,
        websocket_response_processed_result=websocket_response_processed_result,
    )


def sampling_request_state_machine_plan(
    features: Any,
    *,
    event_apply_plans: Sequence[Any],
    outcome_ok: bool,
    cancellation_requested: bool,
    unified_diff: str | None,
) -> SamplingRequestPlan:
    if not isinstance(outcome_ok, bool):
        raise TypeError("outcome_ok must be a bool")
    if not isinstance(cancellation_requested, bool):
        raise TypeError("cancellation_requested must be a bool")
    if unified_diff is not None and not isinstance(unified_diff, str):
        raise TypeError("unified_diff must be a string or None")

    completed_response_id: str | None = None
    result_needs_follow_up = False
    result_last_agent_message: str | None = None
    should_emit_token_count = False
    should_emit_turn_diff = False

    plans = tuple(event_apply_plans)
    for plan in plans:
        completed = getattr(plan, "completed_event_apply_plan", None)
        if completed is not None:
            completed_response_id = getattr(completed, "completed_response_id_after", None)
            result_needs_follow_up = getattr(completed, "result_needs_follow_up", False)
            result_last_agent_message = getattr(completed, "result_last_agent_message", None)
            should_emit_token_count = should_emit_token_count or getattr(completed, "should_emit_token_count", False)
            should_emit_turn_diff = should_emit_turn_diff or getattr(completed, "should_emit_turn_diff", False)

        metadata = getattr(plan, "metadata_event_apply_plan", None)
        if metadata is not None:
            should_emit_token_count = should_emit_token_count or getattr(metadata, "should_emit_token_count", False)

        done = getattr(plan, "output_item_done_apply_plan", None)
        if done is not None:
            mailbox_preemption = getattr(done, "mailbox_preemption_plan", None)
            if mailbox_preemption is not None:
                result_needs_follow_up = getattr(mailbox_preemption, "needs_follow_up", result_needs_follow_up)
                result_last_agent_message = getattr(mailbox_preemption, "last_agent_message", result_last_agent_message)
            else:
                state_after = getattr(done, "state_after_output_result", None)
                if state_after is not None:
                    result_needs_follow_up = getattr(state_after, "needs_follow_up", result_needs_follow_up)
                    result_last_agent_message = getattr(state_after, "last_agent_message", result_last_agent_message)

    loop_tail = sampling_loop_tail_plan(
        features,
        outcome_ok=outcome_ok,
        completed_response_id=completed_response_id,
        should_emit_token_count=should_emit_token_count,
        cancellation_requested=cancellation_requested,
        should_emit_turn_diff=should_emit_turn_diff,
        unified_diff=unified_diff,
    )
    return sampling_request_plan(
        event_apply_plans=plans,
        loop_tail_plan=loop_tail,
        outcome_ok=outcome_ok,
        result_needs_follow_up=result_needs_follow_up,
        result_last_agent_message=result_last_agent_message,
        completed_response_id=completed_response_id,
    )


def stamp_ws_stream_request_start_ms(request: MutableMapping[str, Any]) -> None:
    if request.get("type") not in (None, "response.create"):
        return
    metadata = request.setdefault("client_metadata", {})
    metadata[X_CODEX_WS_STREAM_REQUEST_START_MS_CLIENT_METADATA_KEY] = str(int(time.time() * 1000))


def _service_tier_for_request(model_info: Any, service_tier: Any | None) -> str | None:
    service_tier = _service_tier_request_value(service_tier)
    method = getattr(model_info, "service_tier_for_request", None)
    if callable(method):
        return method(service_tier)
    return service_tier


def _service_tier_request_value(service_tier: Any | None) -> str | None:
    if service_tier is None:
        return None
    request_value = getattr(service_tier, "request_value", None)
    if callable(request_value):
        return str(request_value())
    if isinstance(service_tier, str):
        parsed = ServiceTier.from_request_value(service_tier)
        return parsed.request_value() if parsed is not None else service_tier
    if isinstance(service_tier, Enum):
        return str(service_tier.value)
    return str(service_tier)


def _starts_with(items: Sequence[Any], prefix: Sequence[Any]) -> bool:
    return len(items) >= len(prefix) and list(items[: len(prefix)]) == list(prefix)


def _trace_field(trace: Any | None, name: str) -> str | None:
    if trace is None:
        return None
    if isinstance(trace, Mapping):
        value = trace.get(name)
    else:
        value = getattr(trace, name, None)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    return value


def _feature_responses_websocket_response_processed() -> Any:
    from pycodex.features import Feature

    return Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED


async def _call_provider_hook(provider: Any, name: str) -> Any:
    hook = getattr(provider, name, None)
    if not callable(hook):
        return None
    value = hook()
    return await value if isawaitable(value) else value


def _provider_info(provider: Any) -> Any:
    if isinstance(provider, Mapping):
        info = provider.get("info")
        if callable(info):
            return info()
        return info if info is not None else provider
    info = getattr(provider, "info", None)
    if callable(info):
        return info()
    return info if info is not None else provider


def _provider_supports_websockets(provider_info: Any) -> bool:
    supports = getattr(provider_info, "supports_websockets", False)
    return bool(supports() if callable(supports) else supports)



# HTTP and websocket sampling implementation owned by Rust core::client.
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
    for header_event in _response_header_stream_events(
        header_server_model=_non_empty_header(response_headers, OPENAI_MODEL_HEADER),
        rate_limits=_parse_all_rate_limits(response_headers),
        models_etag=_non_empty_header(response_headers, X_MODELS_ETAG_HEADER),
        server_reasoning_included=_server_reasoning_included(response_headers),
    ):
        live_stream_events_emitted = (
            await _notify_stream_event_observer(
                getattr(prepared.sampling_request, "stream_event_observer", None),
                header_event,
            )
            or live_stream_events_emitted
        )
    with response:
        try:
            readline = getattr(response, "readline", None)
            if callable(readline):
                payload, body_stream_events_emitted = await _read_http_response_payload_live(
                    prepared,
                    response,
                    readline,
                )
                live_stream_events_emitted = body_stream_events_emitted or live_stream_events_emitted
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
        raise CodexErr.stream(str(exc)) from exc
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
        raise CodexErr.stream("stream closed before response.completed")

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
            raise CodexErr.stream(_sse_error_message(event))

    if completed_response is None:
        if pending_stream_error is not None:
            raise pending_stream_error
        raise CodexErr.stream("stream closed before response.completed")

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
                if max_retries is None:
                    # The Rust user-turn loop owns stream retry notifications,
                    # backoff, and transport fallback. Keep this transport
                    # sampler single-attempt when it is composed into that
                    # loop so failures reach responses_retry instead of being
                    # consumed by a second retry state machine.
                    sampled = await sample_with_model_client_session(
                        sampling_request,
                        model_session,
                        websocket_transport,
                    )
                else:
                    sampled = await sample_with_model_client_session_retries(
                        sampling_request,
                        model_session,
                        websocket_transport,
                        max_retries=max_retries,
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
            connection = websocket_client.connect(
                extra_headers=headers,
                turn_state=model_session.turn_state,
                timeout=_websocket_connect_timeout_seconds(model_session.client.state.provider),
            )
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
def _websocket_connect_timeout_seconds(provider: Any) -> float | None:
    """Return Rust-shaped provider websocket connect timeout in seconds."""

    info = _provider_info(provider)
    for source in (info, provider):
        method = getattr(source, "websocket_connect_timeout", None)
        if callable(method):
            value = method()
            if value is None:
                continue
            return _timeout_millis_to_seconds(value)
        value = getattr(source, "websocket_connect_timeout_ms", None)
        if value is not None:
            return _timeout_millis_to_seconds(value)
    return None
def _timeout_millis_to_seconds(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError("websocket connect timeout must be a number of milliseconds")
    if value < 0:
        raise ValueError("websocket connect timeout must be non-negative")
    return float(value) / 1000.0
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
__all__ = [
    "COMPACT_REQUEST_TIMEOUT_IDLE_MULTIPLIER",
    "MEMORIES_SUMMARIZE_ENDPOINT",
    "OPENAI_BETA_HEADER",
    "RESPONSE_STREAM_CHANNEL_CAPACITY",
    "RESPONSES_COMPACT_ENDPOINT",
    "RESPONSES_ENDPOINT",
    "RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE",
    "STREAM_DROPPED_REASON",
    "X_CODEX_INSTALLATION_ID_HEADER",
    "X_CODEX_PARENT_THREAD_ID_HEADER",
    "X_CODEX_TURN_METADATA_HEADER",
    "X_CODEX_TURN_STATE_HEADER",
    "X_CODEX_WINDOW_ID_HEADER",
    "X_CODEX_WS_STREAM_REQUEST_START_MS_CLIENT_METADATA_KEY",
    "X_OPENAI_MEMGEN_REQUEST_HEADER",
    "X_OPENAI_SUBAGENT_HEADER",
    "auth_headers_from_value",
    "sideband_websocket_auth_headers",
    "X_RESPONSESAPI_INCLUDE_TIMING_METRICS_HEADER",
    "WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY",
    "WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY",
    "CompactConversationRequestSettings",
    "CurrentClientSetup",
    "LastResponse",
    "ModelClient",
    "ModelClientSession",
    "ModelClientState",
    "SamplingLoopTailPlan",
    "SamplingRequestPlan",
    "SamplingRequestRuntimeExecutionResult",
    "SamplingRequestRuntimeHookAdapter",
    "SamplingRequestRuntimePlan",
    "SamplingRequestRuntimeSessionLifecycleResult",
    "SamplingRuntimeEventApplicationState",
    "RealtimeWebrtcCallStart",
    "RequestRouteTelemetry",
    "SamplingPostDrainTailPlan",
    "TurnState",
    "WebsocketSession",
    "WebsocketStreamOutcome",
    "build_reasoning",
    "build_responses_headers",
    "build_session_headers",
    "insert_header_if_valid",
    "create_text_param_for_request",
    "create_tools_json_for_responses_api",
    "parent_thread_id_header_value",
    "parse_turn_metadata_header",
    "response_create_client_metadata",
    "response_create_ws_request",
    "response_processed_request_for_sampling_turn",
    "response_processed_ws_request",
    "sampling_loop_tail_plan",
    "sampling_loop_tail_plan_from_runtime_state",
    "execute_sampling_request_runtime_plan",
    "execute_sampling_request_runtime_state_driven_plan",
    "execute_sampling_request_runtime_state_driven_session_plan",
    "execute_sampling_request_runtime_tail_plan_from_state",
    "prepare_and_execute_sampling_request_runtime_state_driven_session_plan",
    "sampling_request_plan",
    "sampling_request_runtime_plan",
    "sampling_request_runtime_tail_plan_from_state",
    "sampling_request_state_machine_plan",
    "sampling_turn_tail_actions",
    "sampling_post_drain_tail_plan",
    "serialize_responses_request",
    "sideband_websocket_auth_headers",
    "stamp_ws_stream_request_start_ms",
    "subagent_header_value",
]

__all__ += [
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
    "send_prepared_http_sampling_request",
]
