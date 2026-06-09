from types import SimpleNamespace

import pytest

from pycodex.core import (
    OPENAI_BETA_HEADER,
    RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE,
    X_CODEX_INSTALLATION_ID_HEADER,
    X_CODEX_TURN_METADATA_HEADER,
    X_CODEX_WINDOW_ID_HEADER,
    X_RESPONSESAPI_INCLUDE_TIMING_METRICS_HEADER,
    WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY,
    WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY,
    LastResponse,
    ModelClient,
    SamplingRuntimeEventApplicationState,
    WebsocketSession,
    WebsocketStreamOutcome,
    prepare_and_execute_sampling_request_runtime_state_driven_session_plan,
    response_create_client_metadata,
    response_create_ws_request,
    response_processed_request_for_sampling_turn,
    response_processed_ws_request,
    stamp_ws_stream_request_start_ms,
)
from pycodex.core.stream_events_utils import (
    SamplingCompletedEventApplyPlan,
    SamplingMetadataEventApplyPlan,
    SamplingStreamEventApplyPlan,
)
from pycodex.features import Feature
from pycodex.protocol import ContentItem, ResponseItem


class FeatureSet:
    def __init__(self, *features: Feature) -> None:
        self.features = set(features)

    def enabled(self, feature: Feature) -> bool:
        return feature in self.features


def _provider(supports: bool = True):
    return SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=supports))


def _client(*, supports: bool = True, timing: bool = False) -> ModelClient:
    return ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=_provider(supports),
        include_timing_metrics=timing,
    )


def _item(role: str, text: str) -> ResponseItem:
    if role == "assistant":
        return ResponseItem.message("assistant", (ContentItem.output_text(text),))
    return ResponseItem.message("user", (ContentItem.input_text(text),))


def _completed(response_id: str = "resp-1") -> SamplingStreamEventApplyPlan:
    return SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id=response_id,
            completed_response_id_after=response_id,
        ),
    )


def _metadata(**kwargs) -> SamplingStreamEventApplyPlan:
    return SamplingStreamEventApplyPlan(
        event_type="metadata",
        metadata_event_apply_plan=SamplingMetadataEventApplyPlan(event_type="metadata", **kwargs),
    )


def _run_session_plan(session, request, *, features=None, plans=None, outcome=WebsocketStreamOutcome.STREAM, **kwargs):
    return prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        features or FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=tuple(plans or (_completed(),)),
        outcome_ok=kwargs.pop("outcome_ok", True),
        cancellation_requested=False,
        unified_diff=None,
        websocket_outcome=outcome,
        **kwargs,
    )


def test_responses_websocket_streams_request():
    # Rust source: codex/codex-rs/core/tests/suite/client_websockets.rs
    # Rust test: responses_websocket_streams_request.
    client = _client(timing=True)
    request = response_create_ws_request({"model": "gpt-5.3-codex", "stream": True, "input": [_item("user", "hello")]})
    payload = client.build_websocket_payload(request)
    headers = client.build_websocket_headers()
    stamp_ws_stream_request_start_ms(payload)
    assert payload["type"] == "response.create"
    assert payload["model"] == "gpt-5.3-codex"
    assert payload["stream"] is True
    assert headers["x-client-request-id"] == "thread"
    assert headers["session-id"] == "session"
    assert headers["thread-id"] == "thread"
    assert payload["client_metadata"][X_CODEX_INSTALLATION_ID_HEADER] == "install"
    assert payload["client_metadata"]["x-codex-ws-stream-request-start-ms"].isdigit()


def test_responses_websocket_streams_without_feature_flag_when_provider_supports_websockets():
    # Rust test: responses_websocket_streams_without_feature_flag_when_provider_supports_websockets.
    assert _client(supports=True).responses_websocket_enabled() is True


def test_responses_websocket_sends_response_processed_when_feature_enabled():
    # Rust test: responses_websocket_sends_response_processed_when_feature_enabled.
    assert response_processed_request_for_sampling_turn(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        outcome_ok=True,
        completed_response_id="resp-1",
    ) == response_processed_ws_request("resp-1")


def test_responses_websocket_sends_response_processed_after_remote_compaction_v2():
    # Rust test: responses_websocket_sends_response_processed_after_remote_compaction_v2.
    assert response_processed_ws_request("resp-compact") == {
        "type": "response.processed",
        "response_id": "resp-compact",
    }


def test_responses_websocket_omits_response_processed_without_feature():
    # Rust test: responses_websocket_omits_response_processed_without_feature.
    assert response_processed_request_for_sampling_turn(
        FeatureSet(),
        outcome_ok=True,
        completed_response_id="resp-1",
    ) is None


def test_responses_websocket_reuses_connection_with_per_turn_trace_payloads():
    # Rust test: responses_websocket_reuses_connection_with_per_turn_trace_payloads.
    client = _client()
    first = client.build_websocket_payload({"model": "m"}, {"traceparent": "00-first"})
    second = client.build_websocket_payload({"model": "m"}, {"traceparent": "00-second"})
    assert first["client_metadata"][WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] == "00-first"
    assert second["client_metadata"][WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] == "00-second"


def test_responses_websocket_preconnect_does_not_replace_turn_trace_payload():
    # Rust test: responses_websocket_preconnect_does_not_replace_turn_trace_payload.
    session = _client().new_session()
    session.preconnect_websocket(object())
    payload = session.client.build_websocket_payload({"model": "m"}, {"traceparent": "00-turn"})
    assert payload["client_metadata"][WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] == "00-turn"


def test_responses_websocket_preconnect_reuses_connection():
    # Rust test: responses_websocket_preconnect_reuses_connection.
    session = _client().new_session()
    connection = object()
    assert session.preconnect_websocket(connection) == {"preconnected": True, "connection_reused": False}
    second = session.preconnect_websocket(object())
    assert second["reason"] == "connection_already_present"


def test_responses_websocket_request_prewarm_reuses_connection():
    # Rust test: responses_websocket_request_prewarm_reuses_connection.
    session = _client().new_session()
    request = {"model": "m", "input": [_item("user", "hello")]}
    result = session.prewarm_websocket(FeatureSet(), payload=request, request=request, event_apply_plans=(_completed("warm-1"),), connection=object())
    assert result["prewarmed"] is True
    assert session.websocket_session.connection is not None
    assert session.websocket_session.last_response == LastResponse("warm-1")


def test_responses_websocket_request_prewarm_traces_logical_request():
    # Rust test: responses_websocket_request_prewarm_traces_logical_request.
    session = _client().new_session()
    request = {"model": "m", "input": [_item("user", "hello")]}
    result = session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(_completed("warm-1"),),
        trace={"traceparent": "00-prewarm"},
    )
    lifecycle = result["result"]
    assert lifecycle.inference_trace_started_request_source == "websocket_request"
    assert lifecycle.websocket_request["client_metadata"][WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY] == "00-prewarm"


def test_responses_websocket_reuses_connection_after_session_drop():
    # Rust test: responses_websocket_reuses_connection_after_session_drop.
    client = _client()
    session = client.new_session()
    session.preconnect_websocket(object())
    session.close()
    next_session = client.new_session()
    assert next_session.websocket_session.connection is not None


def test_responses_websocket_preconnect_is_reused_even_with_header_changes():
    # Rust test: responses_websocket_preconnect_is_reused_even_with_header_changes.
    session = _client().new_session()
    session.preconnect_websocket(object())
    one = session.client.build_websocket_headers(turn_metadata_header="one")
    two = session.client.build_websocket_headers(turn_metadata_header="two")
    assert session.websocket_session.connection is not None
    assert one[X_CODEX_TURN_METADATA_HEADER] == "one"
    assert two[X_CODEX_TURN_METADATA_HEADER] == "two"


def test_responses_websocket_request_prewarm_is_reused_even_with_header_changes():
    # Rust test: responses_websocket_request_prewarm_is_reused_even_with_header_changes.
    session = _client().new_session()
    request = {"model": "m", "input": [_item("user", "hello")]}
    session.prewarm_websocket(FeatureSet(), payload=request, request=request, event_apply_plans=(_completed("warm-1"),), connection=object())
    assert session.prewarm_websocket(FeatureSet(), payload=request, request=request, event_apply_plans=(_completed("warm-2"),))["reason"] == "last_request_present"


def test_responses_websocket_prewarm_uses_v2_when_provider_supports_websockets():
    # Rust test: responses_websocket_prewarm_uses_v2_when_provider_supports_websockets.
    assert _client().build_websocket_headers()[OPENAI_BETA_HEADER] == RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE


def test_responses_websocket_preconnect_runs_when_only_v2_feature_enabled():
    # Rust test: responses_websocket_preconnect_runs_when_only_v2_feature_enabled.
    assert _client().new_session().preconnect_websocket(object())["preconnected"] is True


def test_responses_websocket_v2_requests_use_v2_when_provider_supports_websockets():
    # Rust test: responses_websocket_v2_requests_use_v2_when_provider_supports_websockets.
    assert _client().responses_websocket_enabled() is True
    assert _client().build_websocket_headers()[OPENAI_BETA_HEADER] == RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE


def test_responses_websocket_v2_incremental_requests_are_reused_across_turns():
    # Rust test: responses_websocket_v2_incremental_requests_are_reused_across_turns.
    session = _client().new_session()
    first, assistant, second = _item("user", "one"), _item("assistant", "two"), _item("user", "three")
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-1", (assistant,))
    prepared, _ = session.prepare_websocket_request({"model": "m", "input": [first, assistant, second]}, {"model": "m", "input": [first, assistant, second]})
    assert prepared["previous_response_id"] == "resp-1"
    assert prepared["input"] == [second]


def test_responses_websocket_v2_wins_when_both_features_enabled():
    # Rust test: responses_websocket_v2_wins_when_both_features_enabled.
    assert _client().build_websocket_headers()[OPENAI_BETA_HEADER] == RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE


def test_responses_websocket_emits_websocket_telemetry_events():
    # Rust test: responses_websocket_emits_websocket_telemetry_events.
    session = _client().new_session()
    result = _run_session_plan(session, {"model": "m", "input": []})
    assert result.websocket_stream_request_attempt["connection_available"] is False
    assert result.websocket_stream_result["status"] == "blocked"
    assert result.websocket_stream_request_attempt_outcome["status"] == "blocked"


def test_responses_websocket_includes_timing_metrics_header_when_runtime_metrics_enabled():
    # Rust test: responses_websocket_includes_timing_metrics_header_when_runtime_metrics_enabled.
    headers = _client(timing=True).build_websocket_headers()
    assert headers[X_RESPONSESAPI_INCLUDE_TIMING_METRICS_HEADER] == "true"


def test_responses_websocket_omits_timing_metrics_header_when_runtime_metrics_disabled():
    # Rust test: responses_websocket_omits_timing_metrics_header_when_runtime_metrics_disabled.
    assert X_RESPONSESAPI_INCLUDE_TIMING_METRICS_HEADER not in _client(timing=False).build_websocket_headers()


def test_responses_websocket_emits_reasoning_included_event():
    # Rust test: responses_websocket_emits_reasoning_included_event.
    state = SamplingRuntimeEventApplicationState(server_reasoning_included=True)
    assert state.server_reasoning_included is True


def test_responses_websocket_emits_rate_limit_events():
    # Rust test: responses_websocket_emits_rate_limit_events.
    rate_limits = {"limit_name": "test-limit"}
    state = SamplingRuntimeEventApplicationState(rate_limits_to_record=rate_limits)
    assert state.rate_limits_to_record == rate_limits


def test_responses_websocket_usage_limit_error_emits_rate_limit_event():
    # Rust test: responses_websocket_usage_limit_error_emits_rate_limit_event.
    plan = _metadata(rate_limits_to_record={"remaining": 0})
    assert plan.metadata_event_apply_plan.rate_limits_to_record == {"remaining": 0}


def test_responses_websocket_invalid_request_error_with_status_is_forwarded():
    # Rust test: responses_websocket_invalid_request_error_with_status_is_forwarded.
    session = _client().new_session()
    result = _run_session_plan(session, {"model": "m", "input": []}, outcome_ok=False)
    assert result.runtime_result.final_result["needs_follow_up"] is False


def test_responses_websocket_connection_limit_error_reconnects_and_completes():
    # Rust test: responses_websocket_connection_limit_error_reconnects_and_completes.
    client = _client()
    session = client.new_session()
    assert session.force_http_fallback() is True
    assert client.responses_websocket_enabled() is False


def test_responses_websocket_uses_incremental_create_on_prefix():
    # Rust test: responses_websocket_uses_incremental_create_on_prefix.
    test_responses_websocket_v2_incremental_requests_are_reused_across_turns()


def test_responses_websocket_forwards_turn_metadata_on_initial_and_incremental_create():
    # Rust test: responses_websocket_forwards_turn_metadata_on_initial_and_incremental_create.
    client = _client()
    initial = client.build_websocket_payload({"model": "m"}, turn_metadata_header="turn-meta")
    incremental = client.build_websocket_payload({"model": "m", "previous_response_id": "resp-1"}, turn_metadata_header="turn-meta")
    assert initial["client_metadata"][X_CODEX_TURN_METADATA_HEADER] == "turn-meta"
    assert incremental["client_metadata"][X_CODEX_TURN_METADATA_HEADER] == "turn-meta"


def test_responses_websocket_preserves_custom_turn_metadata_fields():
    # Rust test: responses_websocket_preserves_custom_turn_metadata_fields.
    metadata = response_create_client_metadata({X_CODEX_TURN_METADATA_HEADER: '{"custom":true}'}, None)
    assert metadata[X_CODEX_TURN_METADATA_HEADER] == '{"custom":true}'


def test_responses_websocket_uses_previous_response_id_when_prefix_after_completed():
    # Rust test: responses_websocket_uses_previous_response_id_when_prefix_after_completed.
    test_responses_websocket_v2_incremental_requests_are_reused_across_turns()


def test_responses_websocket_creates_on_non_prefix():
    # Rust test: responses_websocket_creates_on_non_prefix.
    session = _client().new_session()
    session.websocket_session.last_request = {"model": "m", "input": [_item("user", "hello")]}
    session.websocket_session.last_response = LastResponse("resp-1")
    prepared, _ = session.prepare_websocket_request({"model": "m", "input": [_item("user", "different")]}, {"model": "m", "input": [_item("user", "different")]})
    assert "previous_response_id" not in prepared


def test_responses_websocket_creates_when_non_input_request_fields_change():
    # Rust test: responses_websocket_creates_when_non_input_request_fields_change.
    session = _client().new_session()
    first = _item("user", "hello")
    session.websocket_session.last_request = {"model": "m", "instructions": "one", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-1")
    prepared, _ = session.prepare_websocket_request({"model": "m", "instructions": "two", "input": [first]}, {"model": "m", "instructions": "two", "input": [first]})
    assert "previous_response_id" not in prepared


def test_responses_websocket_v2_creates_with_previous_response_id_on_prefix():
    # Rust test: responses_websocket_v2_creates_with_previous_response_id_on_prefix.
    test_responses_websocket_v2_incremental_requests_are_reused_across_turns()


def test_responses_websocket_v2_creates_without_previous_response_id_when_non_input_fields_change():
    # Rust test: responses_websocket_v2_creates_without_previous_response_id_when_non_input_fields_change.
    test_responses_websocket_creates_when_non_input_request_fields_change()


def test_responses_websocket_v2_after_error_uses_full_create_without_previous_response_id():
    # Rust test: responses_websocket_v2_after_error_uses_full_create_without_previous_response_id.
    session = _client().new_session()
    session.websocket_session.last_request = {"model": "m", "input": [_item("user", "hello")]}
    session.websocket_session.last_response = None
    prepared, _ = session.prepare_websocket_request({"model": "m", "input": [_item("user", "hello"), _item("user", "third")]}, {"model": "m", "input": [_item("user", "hello"), _item("user", "third")]})
    assert "previous_response_id" not in prepared


def test_responses_websocket_v2_surfaces_terminal_error_without_close_handshake():
    # Rust test: responses_websocket_v2_surfaces_terminal_error_without_close_handshake.
    session = _client().new_session()
    result = _run_session_plan(session, {"model": "m", "input": []}, outcome_ok=False)
    assert result.websocket_response_processed_request is None
    assert result.runtime_result.final_result["needs_follow_up"] is False


def test_responses_websocket_v2_sets_openai_beta_header():
    # Rust test: responses_websocket_v2_sets_openai_beta_header.
    header = _client().build_websocket_headers()[OPENAI_BETA_HEADER]
    assert RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE in [part.strip() for part in header.split(",")]


def test_client_websockets_rejects_non_mapping_payloads():
    with pytest.raises(TypeError):
        response_create_ws_request(None)  # type: ignore[arg-type]

