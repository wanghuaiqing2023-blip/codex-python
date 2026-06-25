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
        self.connection = None
        self.last_request = None
        self.last_response = None
        self.last_response_pending = False
        self.last_response_from_untraced_warmup = False
        self.set_connection_reused(False)


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
        self.store_cached_websocket_session(WebsocketSession())

    def advance_window_generation(self) -> None:
        self.state.window_generation += 1
        self.store_cached_websocket_session(WebsocketSession())

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
            self.store_cached_websocket_session(WebsocketSession())
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
        prepared["input"] = incremental_items
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


def _serialize_request_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, ResponseItem):
        return _serialize_request_value(value.to_mapping())
    if isinstance(value, Mapping):
        return {
            str(key): _serialize_request_value(item)
            for key, item in value.items()
            if item is not None
        }
    if isinstance(value, (list, tuple)):
        return [_serialize_request_value(item) for item in value]
    return value


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
    contributed_turn_item = _plan_mode_contributed_agent_turn_item(plan, completed_item, turn_item_emit)
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
) -> TurnItem | None:
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
    return TurnItem.agent_message(AgentMessageItem(item.id or "", content))


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
    info = getattr(provider, "info", None)
    if callable(info):
        return info()
    return info if info is not None else provider


def _provider_supports_websockets(provider_info: Any) -> bool:
    supports = getattr(provider_info, "supports_websockets", False)
    return bool(supports() if callable(supports) else supports)


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
