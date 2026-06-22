"""Rust-derived tests for ``codex-api/src/lib.rs``."""

from __future__ import annotations

import pycodex.codex_api as codex_api


def test_crate_root_reexports_rust_public_facade() -> None:
    # Rust crate/module: codex-api/src/lib.rs
    # Contract: crate root publicly re-exports codex-api module APIs plus the
    # codex-client/protocol facade names used by core runtime callers.
    rust_public_exports = {
        "AllowedCaller",
        "ApiError",
        "ApproximateLocation",
        "AuthError",
        "AuthHeaderTelemetry",
        "AuthProvider",
        "ClickOperation",
        "CompactClient",
        "CompactionInput",
        "Compression",
        "FinanceAssetType",
        "FinanceOperation",
        "FindOperation",
        "ImageBackground",
        "ImageData",
        "ImageEditRequest",
        "ImageGenerationRequest",
        "ImageQuality",
        "ImageResponse",
        "ImageUrl",
        "ImagesClient",
        "LocationType",
        "MemoriesClient",
        "MemorySummarizeInput",
        "MemorySummarizeOutput",
        "ModelsClient",
        "OpenAiVerbosity",
        "OpenOperation",
        "Provider",
        "RawMemory",
        "RawMemoryMetadata",
        "Reasoning",
        "RealtimeAudioFrame",
        "RealtimeCallClient",
        "RealtimeCallResponse",
        "RealtimeEvent",
        "RealtimeEventParser",
        "RealtimeOutputModality",
        "RealtimeSessionConfig",
        "RealtimeSessionMode",
        "RealtimeWebsocketClient",
        "RealtimeWebsocketConnection",
        "RealtimeWebsocketEvents",
        "RealtimeWebsocketWriter",
        "ReqwestTransport",
        "RequestTelemetry",
        "ResponseCreateWsRequest",
        "ResponseEvent",
        "ResponseProcessedWsRequest",
        "ResponseStream",
        "ResponsesApiRequest",
        "ResponsesClient",
        "ResponsesOptions",
        "ResponsesWebsocketClient",
        "ResponsesWebsocketClose",
        "ResponsesWebsocketConnection",
        "ResponsesWebsocketProbe",
        "ResponsesWsRequest",
        "RetryConfig",
        "ScreenshotOperation",
        "SearchClient",
        "SearchCommands",
        "SearchContextSize",
        "SearchFilters",
        "SearchImageSettings",
        "SearchInput",
        "SearchQuery",
        "SearchRequest",
        "SearchResponse",
        "SearchResponseLength",
        "SearchSettings",
        "SharedAuthProvider",
        "SportsFunction",
        "SportsLeague",
        "SportsOperation",
        "SportsToolName",
        "SseTelemetry",
        "TextControls",
        "TimeOperation",
        "TransportError",
        "WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY",
        "WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY",
        "WeatherOperation",
        "WebsocketTelemetry",
        "auth_header_telemetry",
        "build_session_headers",
        "create_text_param_for_request",
        "is_azure_responses_provider",
        "map_api_error",
        "response_create_client_metadata",
        "session_update_session_json",
        "upload_local_file",
    }

    assert rust_public_exports <= set(codex_api.__all__)
    for name in rust_public_exports:
        assert hasattr(codex_api, name), name


def test_crate_root_reexport_identity_for_cross_crate_anchors() -> None:
    # Rust crate/module: codex-api/src/lib.rs
    # Contract: re-exported public facade names point at the canonical Python
    # modules that carry the corresponding Rust module contracts.
    from pycodex import codex_client
    from pycodex import protocol
    from pycodex.codex_api import common
    from pycodex.codex_api import endpoint
    from pycodex.codex_api import requests
    from pycodex.codex_api.endpoint import realtime_websocket
    from pycodex.codex_api.endpoint import responses_websocket

    assert codex_api.RequestTelemetry is codex_client.RequestTelemetry
    assert codex_api.ReqwestTransport is codex_client.ReqwestTransport
    assert codex_api.TransportError is codex_client.TransportError
    assert codex_api.RealtimeAudioFrame is protocol.RealtimeAudioFrame
    assert codex_api.RealtimeOutputModality is protocol.RealtimeOutputModality
    assert codex_api.CompactionInput is common.CompactionInput
    assert codex_api.ResponsesApiRequest is common.ResponsesApiRequest
    assert codex_api.Compression is requests.Compression
    assert codex_api.RealtimeWebsocketClient is realtime_websocket.RealtimeWebsocketClient
    assert codex_api.RealtimeWebsocketConnection is realtime_websocket.RealtimeWebsocketConnection
    assert codex_api.RealtimeWebsocketEvents is realtime_websocket.RealtimeWebsocketEvents
    assert codex_api.RealtimeWebsocketWriter is realtime_websocket.RealtimeWebsocketWriter
    assert codex_api.RealtimeEvent is realtime_websocket.RealtimeEvent
    assert codex_api.ResponsesClient is endpoint.ResponsesClient
    assert codex_api.ResponsesWebsocketClient is responses_websocket.ResponsesWebsocketClient
    assert codex_api.ResponsesWebsocketClose is responses_websocket.ResponsesWebsocketClose
    assert codex_api.ResponsesWebsocketProbe is responses_websocket.ResponsesWebsocketProbe
