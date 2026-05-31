from types import SimpleNamespace

import pytest

from pycodex.core import (
    OPENAI_BETA_HEADER,
    RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE,
    X_CODEX_PARENT_THREAD_ID_HEADER,
    X_CODEX_TURN_METADATA_HEADER,
    X_CODEX_TURN_STATE_HEADER,
    X_CODEX_WINDOW_ID_HEADER,
    X_OPENAI_SUBAGENT_HEADER,
    WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY,
    WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY,
    LastResponse,
    ModelClient,
    SamplingLoopTailPlan,
    SamplingPostDrainTailPlan,
    SamplingRequestPlan,
    SamplingRequestRuntimeExecutionResult,
    SamplingRequestRuntimeHookAdapter,
    SamplingRequestRuntimePlan,
    SamplingRequestRuntimeSessionLifecycleResult,
    SamplingRuntimeEventApplicationState,
    TurnState,
    WebsocketSession,
    WebsocketStreamOutcome,
    build_responses_headers,
    build_session_headers,
    create_tools_json_for_responses_api,
    create_text_param_for_request,
    execute_sampling_request_runtime_plan,
    execute_sampling_request_runtime_state_driven_plan,
    execute_sampling_request_runtime_state_driven_session_plan,
    execute_sampling_request_runtime_tail_plan_from_state,
    prepare_and_execute_sampling_request_runtime_state_driven_session_plan,
    parent_thread_id_header_value,
    parse_turn_metadata_header,
    response_create_client_metadata,
    response_create_ws_request,
    response_processed_request_for_sampling_turn,
    response_processed_ws_request,
    sampling_loop_tail_plan,
    sampling_loop_tail_plan_from_runtime_state,
    sampling_request_plan,
    sampling_request_runtime_plan,
    sampling_request_runtime_tail_plan_from_state,
    sampling_request_state_machine_plan,
    sampling_post_drain_tail_plan,
    sampling_turn_tail_actions,
    serialize_responses_request,
    stamp_ws_stream_request_start_ms,
    subagent_header_value,
)
from pycodex.core.client_common import Prompt
from pycodex.core.features import Feature
from pycodex.core.hosted_spec import FreeformToolFormat, ToolSpec
from pycodex.core.stream_events_utils import (
    OutputItemResult,
    SamplingMailboxPreemptionPlan,
    SamplingCompletedEventApplyPlan,
    SamplingMetadataEventApplyPlan,
    SamplingOutputItemAddedApplyPlan,
    SamplingOutputItemDoneApplyPlan,
    SamplingOutputItemDoneTransitionPlan,
    SamplingOutputTextDeltaApplyPlan,
    SamplingOutputState,
    SamplingReasoningDeltaApplyPlan,
    SamplingStreamedAssistantTextDeltaPlan,
    SamplingStreamEventApplyPlan,
    SamplingToolCallInputDeltaApplyPlan,
)
from pycodex.protocol import ReasoningEffort, ReasoningSummary, ResponseItem, ServiceTier, SessionSource, SubAgentSource, ThreadId


class FeatureSet:
    def __init__(self, *features: Feature) -> None:
        self.features = set(features)

    def enabled(self, feature: Feature) -> bool:
        return feature in self.features


def test_build_responses_headers_includes_beta_turn_state_and_metadata():
    turn_state = TurnState()
    turn_state.set("sticky")

    headers = build_responses_headers("beta-a", turn_state, "turn-meta")

    assert headers["x-codex-beta-features"] == "beta-a"
    assert headers[X_CODEX_TURN_STATE_HEADER] == "sticky"
    assert headers[X_CODEX_TURN_METADATA_HEADER] == "turn-meta"


def test_build_responses_headers_skips_invalid_header_values():
    turn_state = TurnState()
    turn_state.set("bad\nstate")

    headers = build_responses_headers("bad\rfeatures", turn_state, "bad\nmetadata")

    assert "x-codex-beta-features" not in headers
    assert X_CODEX_TURN_STATE_HEADER not in headers
    assert X_CODEX_TURN_METADATA_HEADER not in headers

def test_build_session_headers_matches_rust_optional_session_thread_headers():
    assert build_session_headers("sess_123", "thread_123") == {
        "session-id": "sess_123",
        "thread-id": "thread_123",
    }
    assert build_session_headers(None, "thread_123") == {"thread-id": "thread_123"}
    assert build_session_headers("sess_123", None) == {"session-id": "sess_123"}
    assert build_session_headers(None, None) == {}
    assert build_session_headers("bad\r\nsession", "thread_123") == {"thread-id": "thread_123"}
    assert build_session_headers("sess_123", "bad\nthread") == {"session-id": "sess_123"}


def test_parse_turn_metadata_header_rejects_newlines():
    assert parse_turn_metadata_header("ok") == "ok"
    assert parse_turn_metadata_header("bad\nheader") is None


def test_subagent_and_parent_thread_headers_match_thread_spawn_source():
    parent_thread_id = ThreadId.new()
    source = SessionSource.subagent(SubAgentSource.thread_spawn(parent_thread_id, depth=1))

    assert subagent_header_value(source) == "collab_spawn"
    assert parent_thread_id_header_value(source) == str(parent_thread_id)






def test_build_ws_client_metadata_keeps_subagent_metadata_unfiltered():
    source = SessionSource.subagent(SubAgentSource.other_source("bad\nlabel"))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", session_source=source)

    metadata = client.build_ws_client_metadata()

    assert metadata[X_OPENAI_SUBAGENT_HEADER] == "bad\nlabel"
def test_build_subagent_headers_skip_invalid_other_label():
    source = SessionSource.subagent(SubAgentSource.other_source("bad\nlabel"))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", session_source=source)

    headers = client.build_subagent_headers()

    assert "x-openai-subagent" not in headers

def test_model_client_window_generation_resets_cached_websocket_session():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    cached = WebsocketSession(connection=object())
    client.store_cached_websocket_session(cached)

    assert client.current_window_id() == "thread:0"
    assert client.responses_websocket_enabled() is True

    client.advance_window_generation()

    assert client.current_window_id() == "thread:1"
    assert client.state.cached_websocket_session.connection is None


def test_force_http_fallback_disables_websockets_once():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)

    assert client.force_http_fallback() is True
    assert client.responses_websocket_enabled() is False
    assert client.force_http_fallback() is False


def test_build_websocket_headers_include_identity_and_beta():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", include_timing_metrics=True)

    headers = client.build_websocket_headers(turn_metadata_header="turn")

    assert headers["x-client-request-id"] == "thread"
    assert headers[X_CODEX_WINDOW_ID_HEADER] == "thread:0"
    assert headers[X_CODEX_TURN_METADATA_HEADER] == "turn"
    assert headers[OPENAI_BETA_HEADER] == RESPONSES_WEBSOCKETS_V2_BETA_HEADER_VALUE




def test_build_websocket_headers_skip_invalid_identity_values():
    client = ModelClient(session_id="session", thread_id="bad\nthread", installation_id="install")

    headers = client.build_websocket_headers(turn_metadata_header="ok")

    assert "x-client-request-id" not in headers
    assert "thread-id" not in headers
    assert headers["session-id"] == "session"
    assert headers[X_CODEX_TURN_METADATA_HEADER] == "ok"

def test_model_client_session_incremental_items_use_last_response_baseline():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = ResponseItem.message("one")
    second = ResponseItem.message("two")
    third = ResponseItem.message("three")
    request_base = {"model": "m", "input": [first]}
    session.websocket_session.last_request = request_base

    delta = session.get_incremental_items(
        {"model": "m", "input": [first, second, third]},
        LastResponse("resp-1", (second,)),
        allow_empty_delta=False,
    )

    assert delta == [third]


def test_prompt_get_formatted_input_matches_rust_clone_behavior():
    item = ResponseItem.message("hello")
    prompt = Prompt(input=[item])

    formatted = prompt.get_formatted_input()
    formatted.append(ResponseItem.message("extra"))

    assert formatted[:1] == [item]
    assert prompt.input == [item]


def test_stamp_ws_stream_request_start_ms_adds_client_metadata():
    request = {}

    stamp_ws_stream_request_start_ms(request)

    assert "client_metadata" in request
    assert request["client_metadata"]["x-codex-ws-stream-request-start-ms"].isdigit()


def test_stamp_ws_stream_request_start_ms_ignores_processed_requests():
    request = response_processed_ws_request("resp-1")

    stamp_ws_stream_request_start_ms(request)

    assert request == {"type": "response.processed", "response_id": "resp-1"}


def test_response_create_ws_request_matches_tagged_enum_shape():
    assert response_create_ws_request({"model": "m", "input": []}) == {
        "type": "response.create",
        "model": "m",
        "input": [],
    }


def test_response_processed_ws_request_matches_tagged_enum_shape():
    assert response_processed_ws_request("resp-1") == {
        "type": "response.processed",
        "response_id": "resp-1",
    }


def test_response_processed_request_for_sampling_turn_requires_feature_success_and_response_id():
    assert (
        response_processed_request_for_sampling_turn(
            FeatureSet(),
            outcome_ok=True,
            completed_response_id="resp-1",
        )
        is None
    )
    assert (
        response_processed_request_for_sampling_turn(
            FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
            outcome_ok=False,
            completed_response_id="resp-1",
        )
        is None
    )
    assert (
        response_processed_request_for_sampling_turn(
            FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
            outcome_ok=True,
            completed_response_id=None,
        )
        is None
    )
    assert response_processed_request_for_sampling_turn(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        outcome_ok=True,
        completed_response_id="resp-1",
    ) == {"type": "response.processed", "response_id": "resp-1"}


def test_sampling_turn_tail_actions_emit_token_count_before_cancellation():
    assert sampling_turn_tail_actions(
        should_emit_token_count=True,
        cancellation_requested=True,
        should_emit_turn_diff=True,
        unified_diff="diff",
    ) == [{"type": "send_token_count"}, {"type": "turn_aborted"}]


def test_sampling_turn_tail_actions_emit_turn_diff_after_non_cancelled_turn():
    assert sampling_turn_tail_actions(
        should_emit_token_count=False,
        cancellation_requested=False,
        should_emit_turn_diff=True,
        unified_diff="diff --git a/file b/file",
    ) == [{"type": "turn_diff", "unified_diff": "diff --git a/file b/file"}]


def test_sampling_turn_tail_actions_skip_missing_or_disabled_diff():
    assert (
        sampling_turn_tail_actions(
            should_emit_token_count=False,
            cancellation_requested=False,
            should_emit_turn_diff=True,
            unified_diff=None,
        )
        == []
    )
    assert (
        sampling_turn_tail_actions(
            should_emit_token_count=False,
            cancellation_requested=False,
            should_emit_turn_diff=False,
            unified_diff="diff",
        )
        == []
    )


def test_sampling_post_drain_tail_plan_preserves_rust_order_and_flags():
    assert sampling_post_drain_tail_plan(
        should_emit_token_count=True,
        cancellation_requested=True,
        should_emit_turn_diff=True,
        unified_diff="diff",
    ) == SamplingPostDrainTailPlan(
        actions=({"type": "send_token_count"}, {"type": "turn_aborted"}),
        should_send_token_count_before_cancellation=True,
        should_return_turn_aborted=True,
        should_read_turn_diff=False,
        should_emit_turn_diff=False,
    )

    assert sampling_post_drain_tail_plan(
        should_emit_token_count=False,
        cancellation_requested=False,
        should_emit_turn_diff=True,
        unified_diff="diff --git a/file b/file",
    ) == SamplingPostDrainTailPlan(
        actions=({"type": "turn_diff", "unified_diff": "diff --git a/file b/file"},),
        should_send_token_count_before_cancellation=False,
        should_return_turn_aborted=False,
        should_read_turn_diff=True,
        should_emit_turn_diff=True,
    )

    assert sampling_post_drain_tail_plan(
        should_emit_token_count=False,
        cancellation_requested=False,
        should_emit_turn_diff=True,
        unified_diff=None,
    ) == SamplingPostDrainTailPlan(
        actions=(),
        should_send_token_count_before_cancellation=False,
        should_return_turn_aborted=False,
        should_read_turn_diff=True,
        should_emit_turn_diff=False,
    )


def test_sampling_loop_tail_plan_combines_response_processed_drain_and_post_drain_tail():
    assert sampling_loop_tail_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        outcome_ok=True,
        completed_response_id="resp-1",
        should_emit_token_count=True,
        cancellation_requested=False,
        should_emit_turn_diff=True,
        unified_diff="diff --git a/file b/file",
    ) == SamplingLoopTailPlan(
        response_processed_request={"type": "response.processed", "response_id": "resp-1"},
        should_drain_in_flight=True,
        post_drain_tail_plan=SamplingPostDrainTailPlan(
            actions=(
                {"type": "send_token_count"},
                {"type": "turn_diff", "unified_diff": "diff --git a/file b/file"},
            ),
            should_send_token_count_before_cancellation=True,
            should_return_turn_aborted=False,
            should_read_turn_diff=True,
            should_emit_turn_diff=True,
        ),
    )


def test_sampling_loop_tail_plan_skips_response_processed_when_outcome_failed():
    assert sampling_loop_tail_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        outcome_ok=False,
        completed_response_id="resp-1",
        should_emit_token_count=False,
        cancellation_requested=True,
        should_emit_turn_diff=True,
        unified_diff="diff",
    ) == SamplingLoopTailPlan(
        response_processed_request=None,
        should_drain_in_flight=True,
        post_drain_tail_plan=SamplingPostDrainTailPlan(
            actions=({"type": "turn_aborted"},),
            should_send_token_count_before_cancellation=False,
            should_return_turn_aborted=True,
            should_read_turn_diff=False,
            should_emit_turn_diff=False,
        ),
    )


def test_sampling_loop_tail_plan_from_runtime_state_uses_executed_event_flags():
    state = SamplingRuntimeEventApplicationState(
        completed_response_id="resp-1",
        should_emit_token_count=True,
        should_emit_turn_diff=True,
    )

    assert sampling_loop_tail_plan_from_runtime_state(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        state,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff="diff --git a/file b/file",
    ) == SamplingLoopTailPlan(
        response_processed_request={"type": "response.processed", "response_id": "resp-1"},
        should_drain_in_flight=True,
        post_drain_tail_plan=SamplingPostDrainTailPlan(
            actions=(
                {"type": "send_token_count"},
                {"type": "turn_diff", "unified_diff": "diff --git a/file b/file"},
            ),
            should_send_token_count_before_cancellation=True,
            should_return_turn_aborted=False,
            should_read_turn_diff=True,
            should_emit_turn_diff=True,
        ),
    )


def test_sampling_loop_tail_plan_from_runtime_state_keeps_rust_cancellation_order():
    state = SamplingRuntimeEventApplicationState(
        completed_response_id="resp-1",
        should_emit_token_count=True,
        should_emit_turn_diff=True,
    )

    assert sampling_loop_tail_plan_from_runtime_state(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        state,
        outcome_ok=False,
        cancellation_requested=True,
        unified_diff="diff",
    ) == SamplingLoopTailPlan(
        response_processed_request=None,
        should_drain_in_flight=True,
        post_drain_tail_plan=SamplingPostDrainTailPlan(
            actions=({"type": "send_token_count"}, {"type": "turn_aborted"}),
            should_send_token_count_before_cancellation=True,
            should_return_turn_aborted=True,
            should_read_turn_diff=False,
            should_emit_turn_diff=False,
        ),
    )


def test_sampling_request_runtime_tail_plan_from_state_builds_executable_steps():
    state = SamplingRuntimeEventApplicationState(
        completed_response_id="resp-1",
        should_emit_token_count=True,
        should_emit_turn_diff=True,
        result_needs_follow_up=True,
        result_last_agent_message="tail",
    )

    assert sampling_request_runtime_tail_plan_from_state(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        state,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff="diff",
    ) == SamplingRequestRuntimePlan(
        steps=(
            {"type": "send_response_processed", "request": {"type": "response.processed", "response_id": "resp-1"}},
            {"type": "drain_in_flight"},
            {"type": "send_token_count"},
            {"type": "send_turn_diff", "unified_diff": "diff"},
            {
                "type": "return_sampling_result",
                "needs_follow_up": True,
                "last_agent_message": "tail",
            },
        ),
        required_hooks=(
            "send_response_processed",
            "drain_in_flight",
            "send_token_count",
            "send_turn_diff",
            "return_sampling_result",
        ),
    )


def test_sampling_request_runtime_tail_plan_from_state_handles_aborted_tail():
    state = SamplingRuntimeEventApplicationState(
        completed_response_id="resp-1",
        should_emit_token_count=True,
        result_needs_follow_up=True,
        result_last_agent_message="tail",
    )

    assert sampling_request_runtime_tail_plan_from_state(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        state,
        outcome_ok=False,
        cancellation_requested=True,
        unified_diff=None,
    ) == SamplingRequestRuntimePlan(
        steps=(
            {"type": "drain_in_flight"},
            {"type": "send_token_count"},
            {"type": "return_turn_aborted"},
        ),
        required_hooks=(
            "drain_in_flight",
            "send_token_count",
            "return_turn_aborted",
        ),
    )


def test_sampling_request_plan_collects_event_plans_and_tail_result():
    tail = sampling_loop_tail_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        outcome_ok=True,
        completed_response_id="resp-1",
        should_emit_token_count=True,
        cancellation_requested=False,
        should_emit_turn_diff=False,
        unified_diff=None,
    )

    assert sampling_request_plan(
        event_apply_plans=({"type": "created"}, {"type": "completed"}),
        loop_tail_plan=tail,
        outcome_ok=True,
        result_needs_follow_up=True,
        result_last_agent_message="assistant tail",
        completed_response_id="resp-1",
    ) == SamplingRequestPlan(
        event_apply_plans=({"type": "created"}, {"type": "completed"}),
        loop_tail_plan=tail,
        outcome_ok=True,
        result_needs_follow_up=True,
        result_last_agent_message="assistant tail",
        completed_response_id="resp-1",
        should_return_turn_aborted=False,
    )


def test_sampling_request_plan_marks_turn_aborted_from_tail():
    tail = sampling_loop_tail_plan(
        FeatureSet(),
        outcome_ok=False,
        completed_response_id=None,
        should_emit_token_count=True,
        cancellation_requested=True,
        should_emit_turn_diff=True,
        unified_diff="diff",
    )

    assert sampling_request_plan(
        event_apply_plans=(),
        loop_tail_plan=tail,
        outcome_ok=False,
        result_needs_follow_up=False,
    ) == SamplingRequestPlan(
        event_apply_plans=(),
        loop_tail_plan=tail,
        outcome_ok=False,
        result_needs_follow_up=False,
        should_return_turn_aborted=True,
    )


def test_sampling_request_state_machine_plan_folds_completed_and_metadata_tail_flags():
    completed_apply = SimpleNamespace(
        completed_response_id_after="resp-1",
        result_needs_follow_up=True,
        result_last_agent_message="assistant tail",
        should_emit_token_count=True,
        should_emit_turn_diff=True,
    )
    metadata_apply = SimpleNamespace(should_emit_token_count=True)
    event_plans = (
        SimpleNamespace(completed_event_apply_plan=completed_apply),
        SimpleNamespace(metadata_event_apply_plan=metadata_apply),
    )

    plan = sampling_request_state_machine_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=event_plans,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff="diff --git a/file b/file",
    )

    assert plan == SamplingRequestPlan(
        event_apply_plans=event_plans,
        loop_tail_plan=SamplingLoopTailPlan(
            response_processed_request={"type": "response.processed", "response_id": "resp-1"},
            should_drain_in_flight=True,
            post_drain_tail_plan=SamplingPostDrainTailPlan(
                actions=(
                    {"type": "send_token_count"},
                    {"type": "turn_diff", "unified_diff": "diff --git a/file b/file"},
                ),
                should_send_token_count_before_cancellation=True,
                should_return_turn_aborted=False,
                should_read_turn_diff=True,
                should_emit_turn_diff=True,
            ),
        ),
        outcome_ok=True,
        result_needs_follow_up=True,
        result_last_agent_message="assistant tail",
        completed_response_id="resp-1",
        should_return_turn_aborted=False,
    )


def test_sampling_request_state_machine_plan_folds_output_done_mailbox_preemption():
    mailbox = SimpleNamespace(needs_follow_up=True, last_agent_message="mailbox tail")
    done_apply = SimpleNamespace(mailbox_preemption_plan=mailbox)
    event_plans = (SimpleNamespace(output_item_done_apply_plan=done_apply),)

    plan = sampling_request_state_machine_plan(
        FeatureSet(),
        event_apply_plans=event_plans,
        outcome_ok=True,
        cancellation_requested=True,
        unified_diff="ignored",
    )

    assert plan.result_needs_follow_up is True
    assert plan.result_last_agent_message == "mailbox tail"
    assert plan.completed_response_id is None
    assert plan.should_return_turn_aborted is True
    assert plan.loop_tail_plan.post_drain_tail_plan.actions == ({"type": "turn_aborted"},)


def test_sampling_request_runtime_plan_lists_ordered_hooks_for_successful_request():
    event_plan = SimpleNamespace(event_type="completed")
    tail = SamplingLoopTailPlan(
        response_processed_request={"type": "response.processed", "response_id": "resp-1"},
        should_drain_in_flight=True,
        post_drain_tail_plan=SamplingPostDrainTailPlan(
            actions=(
                {"type": "send_token_count"},
                {"type": "turn_diff", "unified_diff": "diff"},
            ),
            should_send_token_count_before_cancellation=True,
            should_return_turn_aborted=False,
            should_read_turn_diff=True,
            should_emit_turn_diff=True,
        ),
    )
    request = SamplingRequestPlan(
        event_apply_plans=(event_plan,),
        loop_tail_plan=tail,
        outcome_ok=True,
        result_needs_follow_up=True,
        result_last_agent_message="assistant tail",
        completed_response_id="resp-1",
    )

    assert sampling_request_runtime_plan(request) == SamplingRequestRuntimePlan(
        steps=(
            {"type": "apply_event_plan", "event_type": "completed", "plan": event_plan},
            {"type": "send_response_processed", "request": {"type": "response.processed", "response_id": "resp-1"}},
            {"type": "drain_in_flight"},
            {"type": "send_token_count"},
            {"type": "send_turn_diff", "unified_diff": "diff"},
            {
                "type": "return_sampling_result",
                "needs_follow_up": True,
                "last_agent_message": "assistant tail",
            },
        ),
        required_hooks=(
            "apply_event_plan",
            "send_response_processed",
            "drain_in_flight",
            "send_token_count",
            "send_turn_diff",
            "return_sampling_result",
        ),
    )


def test_sampling_request_runtime_plan_returns_turn_aborted_without_sampling_result():
    request = SamplingRequestPlan(
        event_apply_plans=(),
        loop_tail_plan=SamplingLoopTailPlan(
            response_processed_request=None,
            should_drain_in_flight=True,
            post_drain_tail_plan=SamplingPostDrainTailPlan(
                actions=({"type": "turn_aborted"},),
                should_return_turn_aborted=True,
            ),
        ),
        outcome_ok=False,
        result_needs_follow_up=False,
        should_return_turn_aborted=True,
    )

    assert sampling_request_runtime_plan(request) == SamplingRequestRuntimePlan(
        steps=(
            {"type": "drain_in_flight"},
            {"type": "return_turn_aborted"},
        ),
        required_hooks=("drain_in_flight", "return_turn_aborted"),
    )


def test_execute_sampling_request_runtime_plan_calls_hooks_in_step_order():
    runtime_plan = SamplingRequestRuntimePlan(
        steps=(
            {"type": "apply_event_plan", "event_type": "created"},
            {
                "type": "send_response_processed",
                "request": {"type": "response.processed", "response_id": "resp-1"},
            },
            {
                "type": "return_sampling_result",
                "needs_follow_up": True,
                "last_agent_message": "tail",
            },
        ),
        required_hooks=(
            "apply_event_plan",
            "send_response_processed",
            "return_sampling_result",
        ),
    )

    class Hooks:
        def __init__(self):
            self.calls = []

        def apply_event_plan(self, step):
            self.calls.append(("apply_event_plan", step.get("event_type")))
            return "applied"

        def send_response_processed(self, step):
            self.calls.append(("send_response_processed", step["request"]["response_id"]))
            return "sent"

        def return_sampling_result(self, step):
            self.calls.append(
                (
                    "return_sampling_result",
                    step["needs_follow_up"],
                    step["last_agent_message"],
                )
            )
            return {
                "needs_follow_up": step["needs_follow_up"],
                "last_agent_message": step["last_agent_message"],
            }

    hooks = Hooks()

    assert execute_sampling_request_runtime_plan(
        runtime_plan,
        hooks,
    ) == SamplingRequestRuntimeExecutionResult(
        step_results=(
            {"type": "apply_event_plan", "result": "applied"},
            {"type": "send_response_processed", "result": "sent"},
            {
                "type": "return_sampling_result",
                "result": {"needs_follow_up": True, "last_agent_message": "tail"},
            },
        ),
        final_result={"needs_follow_up": True, "last_agent_message": "tail"},
        returned_turn_aborted=False,
    )
    assert hooks.calls == [
        ("apply_event_plan", "created"),
        ("send_response_processed", "resp-1"),
        ("return_sampling_result", True, "tail"),
    ]


def test_execute_sampling_request_runtime_plan_marks_turn_aborted_and_requires_hooks():
    runtime_plan = SamplingRequestRuntimePlan(
        steps=({"type": "return_turn_aborted"},),
        required_hooks=("return_turn_aborted",),
    )

    class Hooks:
        def return_turn_aborted(self, step):
            return {"error": "turn_aborted"}

    assert execute_sampling_request_runtime_plan(
        runtime_plan,
        Hooks(),
    ) == SamplingRequestRuntimeExecutionResult(
        step_results=(
            {"type": "return_turn_aborted", "result": {"error": "turn_aborted"}},
        ),
        final_result={"error": "turn_aborted"},
        returned_turn_aborted=True,
    )

    with pytest.raises(TypeError, match="hooks must provide callable drain_in_flight"):
        execute_sampling_request_runtime_plan(
            SamplingRequestRuntimePlan(steps=({"type": "drain_in_flight"},)),
            object(),
        )


def test_sampling_request_runtime_hook_adapter_sends_response_processed_with_connection():
    sent = []

    class Connection:
        def send_response_processed(self, response_id):
            sent.append(response_id)
            return {"sent": True, "response_id": response_id}

    adapter = SamplingRequestRuntimeHookAdapter(
        websocket_session=WebsocketSession(connection=Connection()),
    )

    assert adapter.send_response_processed(
        {"type": "send_response_processed", "request": {"response_id": "resp-1"}}
    ) == {"sent": True, "response_id": "resp-1"}
    assert sent == ["resp-1"]


def test_sampling_request_runtime_hook_adapter_swallows_response_processed_send_errors():
    class Connection:
        def send_response_processed(self, response_id):
            raise RuntimeError(f"cannot ack {response_id}")

    adapter = SamplingRequestRuntimeHookAdapter(
        websocket_session=WebsocketSession(connection=Connection()),
    )

    assert adapter.send_response_processed(
        {"type": "send_response_processed", "request": {"response_id": "resp-1"}}
    ) == {
        "sent": False,
        "error": "cannot ack resp-1",
        "request": {"response_id": "resp-1"},
    }


def test_model_client_session_builds_sampling_runtime_adapter_bound_to_websocket_session():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    state = SamplingRuntimeEventApplicationState()

    adapter = session.sampling_request_runtime_hook_adapter(state=state)

    assert adapter.websocket_session is session.websocket_session
    assert adapter.event_application_state is state


def test_sampling_request_runtime_hook_adapter_summarizes_apply_event_plan_without_callback():
    plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            result_needs_follow_up=True,
            result_last_agent_message="tail",
        ),
    )

    assert SamplingRequestRuntimeHookAdapter().apply_event_plan(
        {"type": "apply_event_plan", "plan": plan}
    ) == {
        "applied": False,
        "reason": "missing_event_plan_applier",
        "event_type": "completed",
        "no_op": False,
        "child_plans": ("completed_event_apply_plan",),
        "completed_response_id": "resp-1",
        "result_needs_follow_up": True,
        "result_last_agent_message": "tail",
        "should_emit_token_count": True,
        "should_emit_turn_diff": True,
    }


def test_sampling_request_runtime_hook_adapter_applies_completed_and_metadata_to_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)

    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            token_usage_to_record={"total_tokens": 42},
            completed_response_id_after="resp-1",
            result_needs_follow_up=True,
            result_last_agent_message="tail",
        ),
    )
    metadata_plan = SamplingStreamEventApplyPlan(
        event_type="rate_limits",
        metadata_event_apply_plan=SamplingMetadataEventApplyPlan(
            event_type="rate_limits",
            rate_limits_to_record={"remaining": 9},
            should_emit_token_count=True,
        ),
    )

    completed_result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": completed_plan})
    metadata_result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": metadata_plan})

    assert completed_result["applied"] is True
    assert completed_result["reason"] == "applied_to_event_application_state"
    state_snapshot = metadata_result["state"]
    assert state_snapshot["applied_event_types"] == ("completed", "rate_limits")
    assert state_snapshot["completed_response_id"] == "resp-1"
    assert state_snapshot["result_needs_follow_up"] is True
    assert state_snapshot["result_last_agent_message"] == "tail"
    assert state_snapshot["should_emit_token_count"] is True
    assert state_snapshot["should_emit_turn_diff"] is True
    assert state_snapshot["token_usage_to_record"] == {"total_tokens": 42}
    assert state_snapshot["metadata_events"] == (
        {
            "event_type": "rate_limits",
            "server_model_to_check": None,
            "should_mark_server_model_warning_if_emitted": False,
            "model_verification_to_emit": None,
            "should_mark_model_verification_emitted": False,
        },
    )
    assert state_snapshot["rate_limits_to_record"] == {"remaining": 9}


def test_sampling_request_runtime_hook_adapter_applies_output_item_done_to_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    output_result = OutputItemResult(
        last_agent_message="tool result tail",
        needs_follow_up=True,
        tool_future="future",
    )
    state_after = SamplingOutputState(
        needs_follow_up=True,
        last_agent_message="state tail",
        in_flight=("future",),
    )
    mailbox_preemption = SamplingMailboxPreemptionPlan(
        needs_follow_up=True,
        last_agent_message="mailbox tail",
    )
    plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            should_continue_loop=True,
            preempt_for_mailbox_mail=True,
            output_result=output_result,
            state_after_output_result=state_after,
            mailbox_preemption_plan=mailbox_preemption,
        ),
    )

    result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": plan})

    assert result["should_continue_loop"] is True
    assert result["preempt_for_mailbox_mail"] is True
    assert result["output_state_needs_follow_up"] is True
    assert result["mailbox_preemption_last_agent_message"] == "mailbox tail"
    state_snapshot = result["state"]
    assert state_snapshot["applied_event_types"] == ("response.output_item.done",)
    assert state_snapshot["result_needs_follow_up"] is True
    assert state_snapshot["result_last_agent_message"] == "mailbox tail"
    assert state_snapshot["output_item_done_events"] == (
        {
            "should_continue_loop": True,
            "preempt_for_mailbox_mail": True,
            "has_streamed_assistant_text_plan": False,
            "has_plan_mode_assistant_done_plan": False,
        },
    )
    assert state_snapshot["should_continue_loop"] is True
    assert state_snapshot["preempt_for_mailbox_mail"] is True
    assert state_snapshot["output_result"] is output_result
    assert state_snapshot["state_after_output_result"] is state_after
    assert state_snapshot["mailbox_preemption_plan"] is mailbox_preemption


def test_sampling_request_runtime_hook_adapter_applies_added_and_text_delta_to_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    seeded = SamplingStreamedAssistantTextDeltaPlan(
        item_id="msg-1",
        visible_text_delta="Hello",
        citations=("cite-1",),
    )
    streamed = SamplingStreamedAssistantTextDeltaPlan(
        item_id="msg-1",
        visible_text_delta=", world",
        ignored_citations=True,
    )
    added_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.added",
        output_item_added_apply_plan=SamplingOutputItemAddedApplyPlan(
            active_tool_argument_diff_consumer_after=("call-1", "consumer"),
            should_reset_tool_argument_diff_consumer=True,
            seeded_streamed_assistant_text_plan=seeded,
            active_item_is_streaming_to_client_after=True,
        ),
    )
    text_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_text.delta",
        output_text_delta_apply_plan=SamplingOutputTextDeltaApplyPlan(
            item_id="msg-1",
            streamed_assistant_text_plan=streamed,
            raw_content_delta="{raw}",
        ),
    )

    added_result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": added_plan})
    text_result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": text_plan})

    assert added_result["has_seeded_streamed_assistant_text_plan"] is True
    assert text_result["visible_text_delta"] == ", world"
    assert text_result["state"]["applied_event_types"] == (
        "response.output_item.added",
        "response.output_text.delta",
    )
    assert text_result["state"]["output_item_added_events"] == (
        {
            "has_active_tool_argument_diff_consumer": True,
            "should_reset_tool_argument_diff_consumer": True,
            "has_pending_agent_message_item": False,
            "has_turn_item_started_to_emit": False,
            "has_seeded_streamed_assistant_text_plan": True,
            "has_active_item_after": False,
            "active_item_is_streaming_to_client_after": True,
        },
    )
    assert text_result["state"]["output_text_delta_events"] == (
        {
            "item_id": "msg-1",
            "has_streamed_assistant_text_plan": True,
            "has_raw_content_delta": True,
        },
    )
    assert text_result["state"]["active_tool_argument_diff_consumer"] == ("call-1", "consumer")
    assert text_result["state"]["should_reset_tool_argument_diff_consumer"] is True
    assert text_result["state"]["active_item_is_streaming_to_client"] is True
    assert text_result["state"]["assistant_text_deltas"] == (
        {
            "item_id": "msg-1",
            "visible_text_delta": "Hello",
            "has_plan_segments_plan": False,
            "citations": ("cite-1",),
            "ignored_citations": False,
        },
        {
            "item_id": "msg-1",
            "visible_text_delta": ", world",
            "has_plan_segments_plan": False,
            "citations": (),
            "ignored_citations": True,
        },
    )
    assert text_result["state"]["raw_content_deltas"] == (
        {"item_id": "msg-1", "raw_content_delta": "{raw}"},
    )


def test_sampling_request_runtime_hook_adapter_applies_tool_and_reasoning_delta_to_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    tool_event = {"type": "tool.input.delta", "call_id": "call-1"}
    reasoning_event = {"type": "reasoning.delta", "item_id": "rs-1"}
    tool_plan = SamplingStreamEventApplyPlan(
        event_type="response.function_call_arguments.delta",
        tool_call_input_delta_apply_plan=SamplingToolCallInputDeltaApplyPlan(
            call_id="call-1",
            delta='{"a"',
            event_to_emit=tool_event,
            should_send_event=True,
        ),
    )
    reasoning_plan = SamplingStreamEventApplyPlan(
        event_type="response.reasoning_summary_text.delta",
        reasoning_delta_apply_plan=SamplingReasoningDeltaApplyPlan(
            event_type="response.reasoning_summary_text.delta",
            item_id="rs-1",
            event_to_emit=reasoning_event,
        ),
    )

    tool_result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": tool_plan})
    reasoning_result = adapter.apply_event_plan({"type": "apply_event_plan", "plan": reasoning_plan})

    assert tool_result["tool_call_input_delta_call_id"] == "call-1"
    assert tool_result["tool_call_input_delta"] == '{"a"'
    assert tool_result["tool_call_should_send_event"] is True
    assert reasoning_result["reasoning_delta_item_id"] == "rs-1"
    assert reasoning_result["state"]["tool_call_input_delta_events"] == (
        {
            "call_id": "call-1",
            "delta": '{"a"',
            "should_send_event": True,
            "has_event_to_emit": True,
        },
    )
    assert reasoning_result["state"]["reasoning_delta_events"] == (
        {
            "event_type": "response.reasoning_summary_text.delta",
            "item_id": "rs-1",
            "event_to_emit": reasoning_event,
        },
    )
    assert reasoning_result["state"]["emitted_stream_events"] == (
        tool_event,
        reasoning_event,
    )


def test_sampling_request_runtime_hook_adapter_returns_sampling_result_from_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    state_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            state_after_output_result=SamplingOutputState(
                needs_follow_up=True,
                last_agent_message="state-derived tail",
            ),
        ),
    )

    adapter.apply_event_plan({"type": "apply_event_plan", "plan": state_plan})

    assert adapter.return_sampling_result(
        {
            "type": "return_sampling_result",
            "needs_follow_up": False,
            "last_agent_message": "static tail",
        }
    ) == {
        "needs_follow_up": True,
        "last_agent_message": "state-derived tail",
    }


def test_execute_sampling_request_runtime_plan_final_result_can_come_from_adapter_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    state_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            result_needs_follow_up=True,
            result_last_agent_message="completed tail",
        ),
    )
    runtime_plan = SamplingRequestRuntimePlan(
        steps=(
            {"type": "apply_event_plan", "plan": state_plan},
            {
                "type": "return_sampling_result",
                "needs_follow_up": False,
                "last_agent_message": "static tail",
            },
        )
    )

    result = execute_sampling_request_runtime_plan(runtime_plan, adapter)

    assert result.final_result == {
        "needs_follow_up": True,
        "last_agent_message": "completed tail",
    }
    assert result.step_results[-1] == {
        "type": "return_sampling_result",
        "result": {
            "needs_follow_up": True,
            "last_agent_message": "completed tail",
        },
    }


def test_execute_sampling_request_runtime_tail_plan_from_state_runs_state_derived_tail():
    calls = []
    state = SamplingRuntimeEventApplicationState(
        completed_response_id="resp-1",
        should_emit_token_count=True,
        should_emit_turn_diff=True,
        result_needs_follow_up=True,
        result_last_agent_message="state tail",
    )
    adapter = SamplingRequestRuntimeHookAdapter(
        event_application_state=state,
        response_processed_sender=lambda response_id: calls.append(("response_processed", response_id)) or "processed",
        in_flight_drainer=lambda: calls.append(("drain", None)) or "drained",
        token_count_sender=lambda: calls.append(("token_count", None)) or "token_count_sent",
        turn_diff_sender=lambda unified_diff: calls.append(("turn_diff", unified_diff)) or "turn_diff_sent",
    )

    result = execute_sampling_request_runtime_tail_plan_from_state(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        state,
        adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff="diff",
    )

    assert calls == [
        ("response_processed", "resp-1"),
        ("drain", None),
        ("token_count", None),
        ("turn_diff", "diff"),
    ]
    assert result.final_result == {
        "needs_follow_up": True,
        "last_agent_message": "state tail",
    }
    assert result.returned_turn_aborted is False


def test_execute_sampling_request_runtime_state_driven_plan_applies_events_before_tail():
    calls = []
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(
        event_application_state=state,
        response_processed_sender=lambda response_id: calls.append(("response_processed", response_id)) or "processed",
        in_flight_drainer=lambda: calls.append(("drain", None)) or "drained",
        token_count_sender=lambda: calls.append(("token_count", None)) or "token_count_sent",
        turn_diff_sender=lambda unified_diff: calls.append(("turn_diff", unified_diff)) or "turn_diff_sent",
    )
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            result_needs_follow_up=True,
            result_last_agent_message="state applied tail",
            should_emit_token_count=True,
            should_emit_turn_diff=True,
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=(completed_plan,),
        state=state,
        hooks=adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff="diff",
    )

    assert tuple(step["type"] for step in result.step_results) == (
        "apply_event_plan",
        "send_response_processed",
        "drain_in_flight",
        "send_token_count",
        "send_turn_diff",
        "return_sampling_result",
    )
    assert state.completed_response_id == "resp-1"
    assert calls == [
        ("response_processed", "resp-1"),
        ("drain", None),
        ("token_count", None),
        ("turn_diff", "diff"),
    ]
    assert result.phase_results == (
        {
            "phase": "event_apply",
            "step_count": 1,
            "step_types": ("apply_event_plan",),
            "event_summaries": (
                {
                    "event_type": "completed",
                    "state_after": {
                        "applied_event_types": ("completed",),
                        "completed_response_id": "resp-1",
                        "result_needs_follow_up": True,
                        "result_last_agent_message": "state applied tail",
                        "should_emit_token_count": True,
                        "should_emit_turn_diff": True,
                        "should_continue_loop": False,
                        "preempt_for_mailbox_mail": False,
                        "stream_event_counts": {
                            "metadata": 0,
                            "output_item_done": 0,
                            "output_item_added": 0,
                            "output_text_delta": 0,
                            "assistant_text_delta": 0,
                            "raw_content_delta": 0,
                            "tool_call_input_delta": 0,
                            "reasoning_delta": 0,
                            "emitted_stream": 0,
                        },
                    },
                },
            ),
            "state_after": {
                "applied_event_types": ("completed",),
                "completed_response_id": "resp-1",
                "result_needs_follow_up": True,
                "result_last_agent_message": "state applied tail",
                "should_emit_token_count": True,
                "should_emit_turn_diff": True,
                "should_continue_loop": False,
                "preempt_for_mailbox_mail": False,
                "metadata_state": {
                    "has_token_usage_to_record": False,
                    "server_reasoning_included": None,
                    "has_rate_limits_to_record": False,
                    "models_etag_to_refresh": None,
                },
                "follow_up_state": {
                    "needs_follow_up": True,
                    "last_agent_message": "state applied tail",
                    "has_output_result": False,
                    "has_state_after_output_result": False,
                    "has_mailbox_preemption_plan": False,
                },
                "stream_event_counts": {
                    "metadata": 0,
                    "output_item_done": 0,
                    "output_item_added": 0,
                    "output_text_delta": 0,
                    "assistant_text_delta": 0,
                    "raw_content_delta": 0,
                    "tool_call_input_delta": 0,
                    "reasoning_delta": 0,
                    "emitted_stream": 0,
                },
            },
            "returned_turn_aborted": False,
        },
        {
            "phase": "tail",
            "step_count": 5,
            "step_types": (
                "send_response_processed",
                "drain_in_flight",
                "send_token_count",
                "send_turn_diff",
                "return_sampling_result",
            ),
            "state_after": {
                "applied_event_types": ("completed",),
                "completed_response_id": "resp-1",
                "result_needs_follow_up": True,
                "result_last_agent_message": "state applied tail",
                "should_emit_token_count": True,
                "should_emit_turn_diff": True,
                "should_continue_loop": False,
                "preempt_for_mailbox_mail": False,
                "metadata_state": {
                    "has_token_usage_to_record": False,
                    "server_reasoning_included": None,
                    "has_rate_limits_to_record": False,
                    "models_etag_to_refresh": None,
                },
                "follow_up_state": {
                    "needs_follow_up": True,
                    "last_agent_message": "state applied tail",
                    "has_output_result": False,
                    "has_state_after_output_result": False,
                    "has_mailbox_preemption_plan": False,
                },
                "stream_event_counts": {
                    "metadata": 0,
                    "output_item_done": 0,
                    "output_item_added": 0,
                    "output_text_delta": 0,
                    "assistant_text_delta": 0,
                    "raw_content_delta": 0,
                    "tool_call_input_delta": 0,
                    "reasoning_delta": 0,
                    "emitted_stream": 0,
                },
            },
            "returned_turn_aborted": False,
        },
    )
    assert result.final_result == {
        "needs_follow_up": True,
        "last_agent_message": "state applied tail",
    }


def test_execute_sampling_request_runtime_state_driven_session_plan_uses_session_connection():
    sent = []

    class Connection:
        def send_response_processed(self, response_id):
            sent.append(response_id)
            return {"sent": True, "response_id": response_id}

        def drain_in_flight(self):
            sent.append("drain")
            return "drained"

    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = Connection()
    state = SamplingRuntimeEventApplicationState()
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            result_needs_follow_up=False,
            result_last_agent_message="session tail",
        ),
    )

    result = execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=(completed_plan,),
        state=state,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert sent == ["resp-1", "drain"]
    assert result.final_result == {
        "needs_follow_up": False,
        "last_agent_message": "session tail",
    }
    assert session.websocket_session.last_response == LastResponse("resp-1")


def test_execute_sampling_request_runtime_state_driven_session_plan_caches_response_items_added():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    item = ResponseItem.message("assistant", ())
    state = SamplingRuntimeEventApplicationState()
    added_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.added",
        output_item_added_apply_plan=SamplingOutputItemAddedApplyPlan(
            active_item_after=item,
            active_item_is_streaming_to_client_after=True,
        ),
    )
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        event_apply_plans=(added_plan, completed_plan),
        state=state,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert session.websocket_session.last_response == LastResponse("resp-1", (item,))


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_delivers_completed_items_added():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = object()
    user_item = ResponseItem.message("user", ())
    assistant_item = ResponseItem.message("assistant", ())
    request = {"model": "m", "input": [user_item, assistant_item]}
    done_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            completed_item=assistant_item,
        ),
    )
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(done_plan, completed_plan),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert session.websocket_session.last_response == LastResponse("resp-1", (assistant_item,))
    assert result.websocket_last_response_delivery == {
        "response_id": "resp-1",
        "items_added": (assistant_item,),
        "receiver_pending": True,
    }
    assert result.runtime_state_summary["stream_event_counts"]["completed_output_items"] == 1


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_records_completed_telemetry():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = object()
    telemetry_calls = []

    class Telemetry:
        def sse_event_completed(
            self,
            input_tokens,
            output_tokens,
            cached_input_tokens,
            reasoning_output_tokens,
            total_tokens,
        ):
            telemetry_calls.append(
                (
                    input_tokens,
                    output_tokens,
                    cached_input_tokens,
                    reasoning_output_tokens,
                    total_tokens,
                )
            )

    request = {"model": "m", "input": [ResponseItem.message("user", ())], "client_metadata": {"http": "only"}}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            token_usage_to_record={
                "input_tokens": 3,
                "output_tokens": 5,
                "cached_input_tokens": 2,
                "reasoning_output_tokens": 1,
                "total_tokens": 8,
            },
            should_record_token_usage=True,
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        session_telemetry=Telemetry(),
        websocket_upstream_request_id="req-1",
    )

    assert telemetry_calls == [(3, 5, 2, 1, 8)]
    assert result.websocket_completed_telemetry == {
        "input_tokens": 3,
        "output_tokens": 5,
        "cached_input_tokens": 2,
        "reasoning_output_tokens": 1,
        "total_tokens": 8,
        "recorded": True,
    }
    assert result.inference_trace_completed == {
        "response_id": "resp-1",
        "request_id": "req-1",
        "token_usage": {
            "input_tokens": 3,
            "output_tokens": 5,
            "cached_input_tokens": 2,
            "reasoning_output_tokens": 1,
            "total_tokens": 8,
        },
        "output_items": (),
    }
    assert result.websocket_feedback_tags == {
        "last_model_request_id": "req-1",
        "last_model_response_id": "resp-1",
    }


def test_execute_sampling_request_runtime_state_driven_session_plan_caches_last_request():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    request = {"model": "m", "input": [first]}
    state = SamplingRuntimeEventApplicationState()
    added_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.added",
        output_item_added_apply_plan=SamplingOutputItemAddedApplyPlan(
            active_item_after=second,
            active_item_is_streaming_to_client_after=True,
        ),
    )
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        event_apply_plans=(added_plan, completed_plan),
        state=state,
        request=request,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert session.websocket_session.last_request == request
    assert session.get_incremental_items(
        {"model": "m", "input": [first, second, ResponseItem.message("user", ())]},
        session.websocket_session.last_response,
        allow_empty_delta=False,
    ) == [ResponseItem.message("user", ())]


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_prepares_incremental_request():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev", (second,))
    request = {"model": "m", "input": [first, second, third]}
    state = SamplingRuntimeEventApplicationState()
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-2",
            completed_response_id_after="resp-2",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        state=state,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert isinstance(result, SamplingRequestRuntimeSessionLifecycleResult)
    assert result.websocket_request["type"] == "response.create"
    assert result.websocket_request["request"]["previous_response_id"] == "resp-prev"
    assert result.websocket_request["request"]["input"] == [third]
    assert result.websocket_request["request"]["client_metadata"] == {
        X_CODEX_INSTALLATION_ID_HEADER: "install",
        X_CODEX_WINDOW_ID_HEADER: "thread:0",
    }
    assert result.websocket_request["client_metadata"]["x-codex-ws-stream-request-start-ms"].isdigit()
    assert result.websocket_request_start_ms_stamped is True
    assert result.inference_trace_started_request_source == "websocket_request"
    assert result.inference_trace_started_request == result.websocket_request
    assert result.websocket_last_request_recorded is True
    assert result.websocket_stream_request_attempt == {
        "request": result.websocket_request,
        "connection_available": False,
        "connection_reused": False,
    }
    assert result.websocket_stream_request_attempt_outcome == {
        "status": "blocked",
        "error": "websocket connection is unavailable",
    }
    assert result.websocket_last_response_receiver_registered is False
    assert result.websocket_stream_result == {
        "status": "blocked",
        "stream_mapped": False,
        "last_response_receiver_registered": False,
    }
    assert result.from_untraced_warmup is False
    assert result.websocket_outcome == WebsocketStreamOutcome.STREAM
    assert result.http_request is None
    assert result.http_fallback_activated is False
    assert result.runtime_result.final_result == {
        "needs_follow_up": False,
        "last_agent_message": None,
    }
    assert result.runtime_state_summary["completed_response_id"] is None
    assert result.runtime_state_summary["applied_event_types"] == ()
    assert session.websocket_session.last_request == request
    assert session.websocket_session.last_response is None
    assert result.inference_trace_completed is None


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_builds_ws_payload_metadata():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    request = {
        "model": "m",
        "input": [ResponseItem.message("user", ())],
        "client_metadata": {"http": "only"},
    }
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        trace={"traceparent": "00-turn", "tracestate": "turn=state"},
        turn_metadata_header="turn-meta",
    )

    assert result.websocket_request["request"]["client_metadata"] == {
        X_CODEX_INSTALLATION_ID_HEADER: "install",
        X_CODEX_WINDOW_ID_HEADER: "thread:0",
        X_CODEX_TURN_METADATA_HEADER: "turn-meta",
        WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "00-turn",
        WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY: "turn=state",
    }
    assert result.websocket_request["client_metadata"]["x-codex-ws-stream-request-start-ms"].isdigit()
    assert session.websocket_session.last_request == request
    assert request["client_metadata"] == {"http": "only"}


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_metadata_does_not_break_incremental_delta():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev", (second,))
    request = {"model": "m", "input": [first, second, third]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-2",
            completed_response_id_after="resp-2",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        trace={"traceparent": "00-inc"},
        turn_metadata_header="turn-meta",
    )

    assert result.websocket_request["request"]["previous_response_id"] == "resp-prev"
    assert result.websocket_request["request"]["input"] == [third]
    assert result.websocket_request["request"]["client_metadata"][
        WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY
    ] == "00-inc"
    assert result.websocket_request["request"]["client_metadata"][X_CODEX_TURN_METADATA_HEADER] == "turn-meta"


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_records_http_fallback():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    sent = []

    class Connection:
        def send_response_processed(self, response_id):
            sent.append(response_id)
            return {"sent": True, "response_id": response_id}

    session.websocket_session.connection = Connection()
    session.websocket_session.last_request = {"model": "m", "input": []}
    session.websocket_session.last_response_from_untraced_warmup = True
    session.websocket_session.set_connection_reused(True)
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_outcome=WebsocketStreamOutcome.FALLBACK_TO_HTTP,
    )

    assert result.websocket_outcome == WebsocketStreamOutcome.FALLBACK_TO_HTTP
    assert result.websocket_request["type"] == "response.create"
    assert result.http_request == request
    assert result.http_fallback_activated is True
    assert client.responses_websocket_enabled() is False
    assert result.runtime_result.final_result == {
        "needs_follow_up": False,
        "last_agent_message": None,
    }
    assert result.runtime_state_summary["completed_response_id"] == "resp-1"
    assert result.runtime_state_summary["applied_event_types"] == ("completed",)
    assert session.websocket_session.connection is None
    assert session.websocket_session.last_request is None
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_pending is False
    assert session.websocket_session.last_response_from_untraced_warmup is False
    assert session.websocket_session.connection_reused() is False
    assert result.websocket_last_response_delivery is None
    assert result.websocket_response_processed_request == {
        "type": "response.processed",
        "response_id": "resp-1",
    }
    assert result.websocket_response_processed_result == {
        "sent": False,
        "reason": "missing_connection",
        "request": {"type": "response.processed", "response_id": "resp-1"},
    }
    assert sent == []


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_records_fallback_telemetry():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    counters = []
    telemetry = SimpleNamespace(
        counter=lambda name, value, tags: counters.append((name, value, tags))
    )
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_outcome=WebsocketStreamOutcome.FALLBACK_TO_HTTP,
        session_telemetry=telemetry,
        model_info=SimpleNamespace(slug="m"),
    )

    assert result.http_fallback_activated is True
    assert counters == [
        (
            "codex.transport.fallback_to_http",
            1,
            (("from_wire_api", "responses_websocket"),),
        )
    ]


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_preserves_warmup_response_marker():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("warm-1", (second,))
    session.websocket_session.last_response_from_untraced_warmup = True
    request = {"model": "m", "input": [first, second, third]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-warm-2",
            completed_response_id_after="resp-warm-2",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        warmup=True,
    )

    assert result.from_untraced_warmup is True
    assert result.completed_response_from_untraced_warmup is True
    assert result.inference_trace_started_request_source == "logical_request"
    assert result.inference_trace_started_request == request
    assert result.websocket_last_request_recorded is True
    assert result.websocket_request["request"]["previous_response_id"] == "warm-1"
    assert result.websocket_request["request"]["input"] == [third]
    assert session.websocket_session.last_response == LastResponse("resp-warm-2")
    assert session.websocket_session.last_response_from_untraced_warmup is True


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_reports_connection_reuse():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.set_connection_reused(True)
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert result.websocket_connection_reused is True
    assert result.websocket_stream_request_attempt["connection_reused"] is True


def test_apply_websocket_connection_lifecycle_resets_incremental_state_for_new_connection():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    session.websocket_session.last_request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    session.websocket_session.last_response = LastResponse("resp-1")
    session.websocket_session.last_response_from_untraced_warmup = True
    session.websocket_session.set_connection_reused(True)
    connection = object()

    result = session.apply_websocket_connection_lifecycle(needs_new=True, connection=connection)

    assert result == {
        "needs_new": True,
        "connection_reused": False,
        "incremental_state_reset": True,
    }
    assert session.websocket_session.connection is connection
    assert session.websocket_session.last_request is None
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_from_untraced_warmup is False
    assert session.websocket_session.connection_reused() is False


def test_apply_websocket_connection_lifecycle_clears_old_connection_when_new_connection_missing():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    old_connection = object()
    session.websocket_session.connection = old_connection
    session.websocket_session.last_response_pending = True
    session.websocket_session.set_connection_reused(True)

    result = session.apply_websocket_connection_lifecycle(needs_new=True)

    assert result == {
        "needs_new": True,
        "connection_reused": False,
        "incremental_state_reset": True,
    }
    assert session.websocket_session.connection is None
    assert session.websocket_session.last_response_pending is False
    assert session.websocket_session.connection_reused() is False


def test_apply_websocket_connection_lifecycle_marks_existing_connection_reused():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    response = LastResponse("resp-1")
    session.websocket_session.connection = object()
    session.websocket_session.last_request = request
    session.websocket_session.last_response = response
    session.websocket_session.last_response_from_untraced_warmup = True

    result = session.apply_websocket_connection_lifecycle(needs_new=False)

    assert result == {
        "needs_new": False,
        "connection_reused": True,
        "incremental_state_reset": False,
    }
    assert session.websocket_session.last_request is request
    assert session.websocket_session.last_response is response
    assert session.websocket_session.last_response_from_untraced_warmup is True
    assert session.websocket_session.connection_reused() is True


def test_websocket_connection_needs_new_matches_missing_closed_and_open_connections():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()

    assert session.websocket_connection_needs_new() is True

    class ClosedMethodConnection:
        def is_closed(self):
            return True

    session.websocket_session.connection = ClosedMethodConnection()
    assert session.websocket_connection_needs_new() is True

    session.websocket_session.connection = SimpleNamespace(is_closed=False)
    assert session.websocket_connection_needs_new() is False

    session.websocket_session.connection = object()
    assert session.websocket_connection_needs_new() is False


def test_preconnect_websocket_sets_connection_without_prompt_payload():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    connection = object()

    result = session.preconnect_websocket(connection)

    assert result == {"preconnected": True, "connection_reused": False}
    assert session.websocket_session.connection is connection
    assert session.websocket_session.connection_reused() is False
    assert session.websocket_session.last_request is None
    assert session.websocket_session.last_response is None


def test_preconnect_websocket_skips_when_disabled_or_already_connected():
    disabled_provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=False))
    disabled_client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=disabled_provider,
    )
    disabled_session = disabled_client.new_session()
    assert disabled_session.preconnect_websocket(object()) == {
        "preconnected": False,
        "reason": "websocket_disabled",
    }
    assert disabled_session.websocket_session.connection is None

    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    existing = object()
    session.websocket_session.connection = existing
    session.websocket_session.set_connection_reused(True)

    assert session.preconnect_websocket(object()) == {
        "preconnected": False,
        "reason": "connection_already_present",
        "connection_reused": True,
    }
    assert session.websocket_session.connection is existing


def test_prewarm_websocket_runs_warmup_when_enabled_without_last_request():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    connection = SimpleNamespace(is_closed=False)
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="warm-1",
            completed_response_id_after="warm-1",
        ),
    )

    prewarm = session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        connection=connection,
        trace={"traceparent": "00-warm", "tracestate": "warm=state"},
        turn_metadata_header="turn-meta",
        unified_diff=None,
    )

    result = prewarm["result"]
    assert prewarm["prewarmed"] is True
    assert prewarm["reason"] == "completed"
    assert prewarm["preconnect"] == {"preconnected": True, "connection_reused": False}
    assert result.websocket_outcome == WebsocketStreamOutcome.STREAM
    assert result.websocket_request["request"]["generate"] is False
    assert result.websocket_request["request"]["client_metadata"] == {
        X_CODEX_INSTALLATION_ID_HEADER: "install",
        X_CODEX_WINDOW_ID_HEADER: "thread:0",
        X_CODEX_TURN_METADATA_HEADER: "turn-meta",
        WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "00-warm",
        WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY: "warm=state",
    }
    assert result.completed_response_from_untraced_warmup is True
    assert session.websocket_session.connection is connection
    assert session.websocket_session.last_request == {**request, "generate": False}
    assert request["client_metadata"] == {"http": "only"}
    assert session.websocket_session.last_response == LastResponse("warm-1")
    assert session.websocket_session.last_response_from_untraced_warmup is True


def test_prewarm_websocket_skips_when_disabled_or_last_request_present():
    disabled_provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=False))
    disabled_client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=disabled_provider,
    )
    disabled_session = disabled_client.new_session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())], "generate": False}

    assert disabled_session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        unified_diff=None,
    ) == {"prewarmed": False, "reason": "websocket_disabled"}

    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.last_request = request

    assert session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        connection=object(),
        unified_diff=None,
    ) == {"prewarmed": False, "reason": "last_request_present"}


def test_prewarm_websocket_reports_fallback_and_missing_completed():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    request = {"model": "m", "input": [ResponseItem.message("user", ())], "generate": False}

    fallback_client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=provider,
    )
    fallback_session = fallback_client.new_session()
    fallback = fallback_session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        connection=object(),
        unified_diff=None,
        websocket_outcome=WebsocketStreamOutcome.FALLBACK_TO_HTTP,
    )
    assert fallback["prewarmed"] is False
    assert fallback["reason"] == "fallback_to_http"
    assert fallback["result"].websocket_outcome == WebsocketStreamOutcome.FALLBACK_TO_HTTP
    assert fallback_client.responses_websocket_enabled() is False

    missing_client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=provider,
    )
    missing_session = missing_client.new_session()
    missing = missing_session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        connection=SimpleNamespace(is_closed=False),
        unified_diff=None,
    )
    assert missing["prewarmed"] is False
    assert missing["reason"] == "missing_completed"
    assert missing["result"].runtime_state_summary["completed_response_id"] is None


def test_prewarm_websocket_reports_stream_error_separately_from_missing_completed():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())], "generate": False}

    prewarm = session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        connection=SimpleNamespace(is_closed=False),
        unified_diff=None,
        websocket_mapped_stream_error="warmup stream failed",
    )

    assert prewarm["prewarmed"] is False
    assert prewarm["reason"] == "stream_failed"
    assert prewarm["result"].websocket_stream_result["status"] == "failed"
    assert prewarm["result"].inference_trace_failed["error"] == "warmup stream failed"


def test_prewarm_websocket_reports_stream_cancellation_separately_from_missing_completed():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())], "generate": False}

    prewarm = session.prewarm_websocket(
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        connection=SimpleNamespace(is_closed=False),
        unified_diff=None,
        websocket_consumer_dropped=True,
    )

    assert prewarm["prewarmed"] is False
    assert prewarm["reason"] == "stream_cancelled"
    assert prewarm["result"].websocket_stream_result["status"] == "cancelled"
    assert prewarm["result"].inference_trace_cancelled["reason"] == (
        "response stream dropped before provider terminal event"
    )


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_resets_on_websocket_connect_timeout():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    session.websocket_session.connection = object()
    session.websocket_session.last_request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    session.websocket_session.last_response = LastResponse("resp-1")
    session.websocket_session.last_response_pending = True
    session.websocket_session.last_response_from_untraced_warmup = True
    session.websocket_session.set_connection_reused(True)
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-timeout",
            completed_response_id_after="resp-timeout",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_connection_needs_new=True,
        websocket_connection_error="websocket connect timed out",
        websocket_connection_timeout=True,
    )

    assert result.websocket_connection_lifecycle == {
        "needs_new": True,
        "connection_reused": False,
        "incremental_state_reset": True,
        "connection_failure_reset": True,
    }
    assert result.websocket_stream_request_attempt["connection_available"] is False
    assert result.websocket_stream_request_attempt["connection_failure"] == {
        "error": "websocket connect timed out",
        "timeout": True,
    }
    assert result.runtime_state_summary["completed_response_id"] is None
    assert session.websocket_session.connection is None
    assert session.websocket_session.last_request == request
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_pending is False
    assert session.websocket_session.last_response_from_untraced_warmup is False
    assert session.websocket_session.connection_reused() is False


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_infers_reused_open_connection():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    connection = SimpleNamespace(is_closed=False)
    session.websocket_session.connection = connection
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-1", (second,))
    request = {"model": "m", "input": [first, second, third]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-2",
            completed_response_id_after="resp-2",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert result.websocket_connection_lifecycle == {
        "needs_new": False,
        "connection_reused": True,
        "incremental_state_reset": False,
    }
    assert result.websocket_connection_reused is True
    assert result.websocket_request["request"]["previous_response_id"] == "resp-1"
    assert result.websocket_stream_request_attempt["connection_available"] is True
    assert result.websocket_stream_request_attempt["connection_reused"] is True
    assert session.websocket_session.connection is connection


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_applies_new_connection_lifecycle():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev", (second,))
    session.websocket_session.last_response_from_untraced_warmup = True
    session.websocket_session.set_connection_reused(True)
    connection = object()
    request = {"model": "m", "input": [first, second, third]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-2",
            completed_response_id_after="resp-2",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_connection_needs_new=True,
        websocket_connection=connection,
    )

    assert result.websocket_connection_lifecycle == {
        "needs_new": True,
        "connection_reused": False,
        "incremental_state_reset": True,
    }
    assert result.websocket_connection_reused is False
    assert result.websocket_stream_request_attempt["connection_available"] is True
    assert result.websocket_stream_request_attempt["connection_reused"] is False
    assert result.websocket_stream_request_attempt_outcome == {"status": "ready", "error": None}
    assert result.websocket_last_response_receiver_registered is True
    assert session.websocket_session.last_response_pending is True
    assert result.websocket_stream_result == {
        "status": "stream",
        "stream_mapped": True,
        "last_response_receiver_registered": True,
    }
    assert result.websocket_last_response_delivery == {
        "response_id": "resp-2",
        "items_added": (),
        "receiver_pending": True,
    }
    assert result.websocket_request["request"]["input"] == request["input"]
    assert "previous_response_id" not in result.websocket_request["request"]
    assert session.websocket_session.connection is connection
    assert session.websocket_session.last_response == LastResponse("resp-2")
    assert session.websocket_session.last_response_from_untraced_warmup is False


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_exposes_response_processed_tail():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    sent = []

    class Connection:
        def send_response_processed(self, response_id):
            sent.append(response_id)
            return {"sent": True, "response_id": response_id}

    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-processed",
            completed_response_id_after="resp-processed",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_connection_needs_new=True,
        websocket_connection=Connection(),
    )

    assert result.websocket_response_processed_request == {
        "type": "response.processed",
        "response_id": "resp-processed",
    }
    assert result.websocket_response_processed_result == {
        "sent": True,
        "response_id": "resp-processed",
    }
    assert sent == ["resp-processed"]


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_applies_reused_connection_lifecycle():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    session.websocket_session.connection = object()
    session.websocket_session.last_request = {"model": "m", "input": [first]}
    session.websocket_session.last_response = LastResponse("resp-prev", (second,))
    request = {"model": "m", "input": [first, second, third]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-2",
            completed_response_id_after="resp-2",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_connection_needs_new=False,
    )

    assert result.websocket_connection_lifecycle == {
        "needs_new": False,
        "connection_reused": True,
        "incremental_state_reset": False,
    }
    assert result.websocket_connection_reused is True
    assert result.websocket_stream_request_attempt["connection_available"] is True
    assert result.websocket_stream_request_attempt["connection_reused"] is True
    assert result.websocket_stream_request_attempt_outcome == {"status": "ready", "error": None}
    assert result.websocket_last_response_receiver_registered is True
    assert session.websocket_session.last_response_pending is True
    assert result.websocket_stream_result == {
        "status": "stream",
        "stream_mapped": True,
        "last_response_receiver_registered": True,
    }
    assert result.websocket_last_response_delivery == {
        "response_id": "resp-2",
        "items_added": (),
        "receiver_pending": True,
    }
    assert result.websocket_request["request"]["previous_response_id"] == "resp-prev"
    assert result.websocket_request["request"]["input"] == [third]


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_models_stream_request_error():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = object()
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_stream_error="stream failed",
    )

    assert result.websocket_stream_request_attempt_outcome == {
        "status": "failed",
        "error": "stream failed",
    }
    assert result.inference_trace_failed == {
        "error": "stream failed",
        "request_id": None,
        "output_items": (),
    }
    assert result.websocket_last_response_receiver_registered is False
    assert result.websocket_stream_result == {
        "status": "failed",
        "stream_mapped": False,
        "last_response_receiver_registered": False,
    }
    assert result.websocket_last_response_delivery is None
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_pending is False
    assert result.inference_trace_completed is None
    assert result.runtime_state_summary["completed_response_id"] is None
    assert result.runtime_state_summary["applied_event_types"] == ()


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_models_stream_closed_before_completed():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = object()
    user_item = ResponseItem.message("user", ())
    assistant_item = ResponseItem.message("assistant", ())
    request = {"model": "m", "input": [user_item, assistant_item]}
    done_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            completed_item=assistant_item,
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(done_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_stream_closed_before_completed=True,
        websocket_upstream_request_id="req-closed",
    )

    assert result.websocket_stream_request_attempt_outcome == {"status": "ready", "error": None}
    assert result.websocket_last_response_receiver_registered is True
    assert result.websocket_stream_result == {
        "status": "failed",
        "stream_mapped": True,
        "last_response_receiver_registered": True,
        "terminal_event": "missing_response_completed",
    }
    assert result.inference_trace_failed == {
        "error": "stream closed before response.completed",
        "request_id": "req-closed",
        "output_items": (assistant_item,),
    }
    assert result.websocket_feedback_tags == {"last_model_request_id": "req-closed"}
    assert result.websocket_last_response_delivery is None
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_pending is False


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_models_consumer_dropped():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = object()
    user_item = ResponseItem.message("user", ())
    assistant_item = ResponseItem.message("assistant", ())
    request = {"model": "m", "input": [user_item, assistant_item]}
    done_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            completed_item=assistant_item,
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(done_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_consumer_dropped=True,
        websocket_upstream_request_id="req-cancelled",
    )

    assert result.websocket_stream_request_attempt_outcome == {"status": "ready", "error": None}
    assert result.websocket_last_response_receiver_registered is True
    assert result.websocket_stream_result == {
        "status": "cancelled",
        "stream_mapped": True,
        "last_response_receiver_registered": True,
        "terminal_event": "consumer_dropped",
    }
    assert result.inference_trace_cancelled == {
        "reason": "response stream dropped before provider terminal event",
        "request_id": "req-cancelled",
        "output_items": (assistant_item,),
    }
    assert result.websocket_feedback_tags == {"last_model_request_id": "req-cancelled"}
    assert result.inference_trace_failed is None
    assert result.websocket_last_response_delivery is None
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_pending is False


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_models_mapped_stream_error():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    session.websocket_session.connection = object()
    telemetry_calls = []

    class Telemetry:
        def see_event_completed_failed(self, error):
            telemetry_calls.append(error)

    user_item = ResponseItem.message("user", ())
    assistant_item = ResponseItem.message("assistant", ())
    request = {"model": "m", "input": [user_item, assistant_item]}
    done_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            completed_item=assistant_item,
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(done_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        websocket_mapped_stream_error="mapped api error",
        websocket_error_request_id="req-from-error",
        session_telemetry=Telemetry(),
    )

    assert result.websocket_stream_request_attempt_outcome == {"status": "ready", "error": None}
    assert result.websocket_last_response_receiver_registered is True
    assert result.websocket_stream_result == {
        "status": "failed",
        "stream_mapped": True,
        "last_response_receiver_registered": True,
        "terminal_event": "api_error",
    }
    assert result.inference_trace_failed == {
        "error": "mapped api error",
        "request_id": "req-from-error",
        "output_items": (assistant_item,),
    }
    assert result.websocket_feedback_tags == {"last_model_request_id": "req-from-error"}
    assert telemetry_calls == ["mapped api error"]
    assert result.websocket_failed_telemetry == {
        "error": "mapped api error",
        "recorded": True,
    }
    assert result.inference_trace_cancelled is None
    assert result.websocket_last_response_delivery is None
    assert session.websocket_session.last_response is None
    assert session.websocket_session.last_response_pending is False


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_can_skip_start_timestamp():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
        ),
    )

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(completed_plan,),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
        stamp_websocket_request_start_ms=False,
    )

    assert result.websocket_request_start_ms_stamped is False
    assert "client_metadata" not in result.websocket_request


def test_prepare_and_execute_sampling_request_runtime_state_driven_session_plan_records_last_request_before_abort():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", provider=provider)
    session = client.new_session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}

    result = prepare_and_execute_sampling_request_runtime_state_driven_session_plan(
        session,
        FeatureSet(),
        payload=request,
        request=request,
        event_apply_plans=(),
        outcome_ok=False,
        cancellation_requested=True,
        unified_diff=None,
    )

    assert result.runtime_result.returned_turn_aborted is True
    assert result.websocket_last_request_recorded is True
    assert session.websocket_session.last_request == request
    assert session.websocket_session.last_response is None


def test_prepare_websocket_request_clears_pending_last_response_marker():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = ResponseItem.message("user", ())
    second = ResponseItem.message("assistant", ())
    third = ResponseItem.message("user", ())
    previous = {"model": "m", "input": [first]}
    request = {"model": "m", "input": [first, second, third]}
    session.websocket_session.last_request = previous
    session.websocket_session.last_response = LastResponse("resp-1", (second,))
    session.websocket_session.last_response_pending = True

    prepared, from_warmup = session.prepare_websocket_request(request, request)

    assert from_warmup is False
    assert prepared["previous_response_id"] == "resp-1"
    assert prepared["input"] == [third]
    assert session.websocket_session.last_response_pending is False


def test_execute_sampling_request_runtime_state_driven_plan_binds_adapter_state():
    calls = []
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(
        response_processed_sender=lambda response_id: calls.append(("response_processed", response_id)) or "processed",
        in_flight_drainer=lambda: calls.append(("drain", None)) or "drained",
    )
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            result_needs_follow_up=False,
            result_last_agent_message="bound state tail",
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=(completed_plan,),
        state=state,
        hooks=adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert adapter.event_application_state is state
    assert state.completed_response_id == "resp-1"
    assert calls == [
        ("response_processed", "resp-1"),
        ("drain", None),
    ]
    assert result.final_result == {
        "needs_follow_up": False,
        "last_agent_message": "bound state tail",
    }


def test_execute_sampling_request_runtime_state_driven_plan_traces_aborted_tail():
    calls = []
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(
        event_application_state=state,
        in_flight_drainer=lambda: calls.append(("drain", None)) or "drained",
        token_count_sender=lambda: calls.append(("token_count", None)) or "token_count_sent",
    )
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            completed_response_id_after="resp-1",
            result_needs_follow_up=True,
            result_last_agent_message="cancelled tail",
            should_emit_token_count=True,
            should_emit_turn_diff=True,
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=(completed_plan,),
        state=state,
        hooks=adapter,
        outcome_ok=False,
        cancellation_requested=True,
        unified_diff="ignored diff",
    )

    assert tuple(step["type"] for step in result.step_results) == (
        "apply_event_plan",
        "drain_in_flight",
        "send_token_count",
        "return_turn_aborted",
    )
    assert calls == [
        ("drain", None),
        ("token_count", None),
    ]
    assert result.phase_results == (
        {
            "phase": "event_apply",
            "step_count": 1,
            "step_types": ("apply_event_plan",),
            "event_summaries": (
                {
                    "event_type": "completed",
                    "state_after": {
                        "applied_event_types": ("completed",),
                        "completed_response_id": "resp-1",
                        "result_needs_follow_up": True,
                        "result_last_agent_message": "cancelled tail",
                        "should_emit_token_count": True,
                        "should_emit_turn_diff": True,
                        "should_continue_loop": False,
                        "preempt_for_mailbox_mail": False,
                        "stream_event_counts": {
                            "metadata": 0,
                            "output_item_done": 0,
                            "output_item_added": 0,
                            "output_text_delta": 0,
                            "assistant_text_delta": 0,
                            "raw_content_delta": 0,
                            "tool_call_input_delta": 0,
                            "reasoning_delta": 0,
                            "emitted_stream": 0,
                        },
                    },
                },
            ),
            "state_after": {
                "applied_event_types": ("completed",),
                "completed_response_id": "resp-1",
                "result_needs_follow_up": True,
                "result_last_agent_message": "cancelled tail",
                "should_emit_token_count": True,
                "should_emit_turn_diff": True,
                "should_continue_loop": False,
                "preempt_for_mailbox_mail": False,
                "metadata_state": {
                    "has_token_usage_to_record": False,
                    "server_reasoning_included": None,
                    "has_rate_limits_to_record": False,
                    "models_etag_to_refresh": None,
                },
                "follow_up_state": {
                    "needs_follow_up": True,
                    "last_agent_message": "cancelled tail",
                    "has_output_result": False,
                    "has_state_after_output_result": False,
                    "has_mailbox_preemption_plan": False,
                },
                "stream_event_counts": {
                    "metadata": 0,
                    "output_item_done": 0,
                    "output_item_added": 0,
                    "output_text_delta": 0,
                    "assistant_text_delta": 0,
                    "raw_content_delta": 0,
                    "tool_call_input_delta": 0,
                    "reasoning_delta": 0,
                    "emitted_stream": 0,
                },
            },
            "returned_turn_aborted": False,
        },
        {
            "phase": "tail",
            "step_count": 3,
            "step_types": (
                "drain_in_flight",
                "send_token_count",
                "return_turn_aborted",
            ),
            "state_after": {
                "applied_event_types": ("completed",),
                "completed_response_id": "resp-1",
                "result_needs_follow_up": True,
                "result_last_agent_message": "cancelled tail",
                "should_emit_token_count": True,
                "should_emit_turn_diff": True,
                "should_continue_loop": False,
                "preempt_for_mailbox_mail": False,
                "metadata_state": {
                    "has_token_usage_to_record": False,
                    "server_reasoning_included": None,
                    "has_rate_limits_to_record": False,
                    "models_etag_to_refresh": None,
                },
                "follow_up_state": {
                    "needs_follow_up": True,
                    "last_agent_message": "cancelled tail",
                    "has_output_result": False,
                    "has_state_after_output_result": False,
                    "has_mailbox_preemption_plan": False,
                },
                "stream_event_counts": {
                    "metadata": 0,
                    "output_item_done": 0,
                    "output_item_added": 0,
                    "output_text_delta": 0,
                    "assistant_text_delta": 0,
                    "raw_content_delta": 0,
                    "tool_call_input_delta": 0,
                    "reasoning_delta": 0,
                    "emitted_stream": 0,
                },
            },
            "returned_turn_aborted": True,
        },
    )
    assert result.final_result == {"error": "turn_aborted"}
    assert result.returned_turn_aborted is True


def test_execute_sampling_request_runtime_state_driven_plan_traces_stream_surface_counts():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    tool_event = {"type": "tool.input.delta", "call_id": "call-1"}
    reasoning_event = {"type": "reasoning.delta", "item_id": "rs-1"}
    tool_plan = SamplingStreamEventApplyPlan(
        event_type="response.function_call_arguments.delta",
        tool_call_input_delta_apply_plan=SamplingToolCallInputDeltaApplyPlan(
            call_id="call-1",
            delta='{"a"',
            event_to_emit=tool_event,
            should_send_event=True,
        ),
    )
    reasoning_plan = SamplingStreamEventApplyPlan(
        event_type="response.reasoning_summary_text.delta",
        reasoning_delta_apply_plan=SamplingReasoningDeltaApplyPlan(
            event_type="response.reasoning_summary_text.delta",
            item_id="rs-1",
            event_to_emit=reasoning_event,
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(),
        event_apply_plans=(tool_plan, reasoning_plan),
        state=state,
        hooks=adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert result.phase_results[0]["step_types"] == (
        "apply_event_plan",
        "apply_event_plan",
    )
    assert tuple(summary["event_type"] for summary in result.phase_results[0]["event_summaries"]) == (
        "response.function_call_arguments.delta",
        "response.reasoning_summary_text.delta",
    )
    assert result.phase_results[0]["event_summaries"][0]["state_after"]["stream_event_counts"] == {
        "metadata": 0,
        "output_item_done": 0,
        "output_item_added": 0,
        "output_text_delta": 0,
        "assistant_text_delta": 0,
        "raw_content_delta": 0,
        "tool_call_input_delta": 1,
        "reasoning_delta": 0,
        "emitted_stream": 1,
    }
    assert result.phase_results[0]["state_after"]["stream_event_counts"] == {
        "metadata": 0,
        "output_item_done": 0,
        "output_item_added": 0,
        "output_text_delta": 0,
        "assistant_text_delta": 0,
        "raw_content_delta": 0,
        "tool_call_input_delta": 1,
        "reasoning_delta": 1,
        "emitted_stream": 2,
    }
    assert result.phase_results[1]["step_types"] == (
        "drain_in_flight",
        "return_sampling_result",
    )


def test_execute_sampling_request_runtime_state_driven_plan_traces_output_item_and_text_events():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    seeded = SamplingStreamedAssistantTextDeltaPlan(
        item_id="msg-1",
        visible_text_delta="Hello",
    )
    streamed = SamplingStreamedAssistantTextDeltaPlan(
        item_id="msg-1",
        visible_text_delta=", world",
    )
    added_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.added",
        output_item_added_apply_plan=SamplingOutputItemAddedApplyPlan(
            seeded_streamed_assistant_text_plan=seeded,
            active_item_is_streaming_to_client_after=True,
        ),
    )
    text_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_text.delta",
        output_text_delta_apply_plan=SamplingOutputTextDeltaApplyPlan(
            item_id="msg-1",
            streamed_assistant_text_plan=streamed,
            raw_content_delta="{raw}",
        ),
    )
    done_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            should_continue_loop=True,
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(),
        event_apply_plans=(added_plan, text_plan, done_plan),
        state=state,
        hooks=adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    event_summaries = result.phase_results[0]["event_summaries"]
    assert tuple(summary["event_type"] for summary in event_summaries) == (
        "response.output_item.added",
        "response.output_text.delta",
        "response.output_item.done",
    )
    assert event_summaries[0]["state_after"]["stream_event_counts"] == {
        "metadata": 0,
        "output_item_done": 0,
        "output_item_added": 1,
        "output_text_delta": 0,
        "assistant_text_delta": 1,
        "raw_content_delta": 0,
        "tool_call_input_delta": 0,
        "reasoning_delta": 0,
        "emitted_stream": 0,
    }
    assert event_summaries[1]["state_after"]["stream_event_counts"] == {
        "metadata": 0,
        "output_item_done": 0,
        "output_item_added": 1,
        "output_text_delta": 1,
        "assistant_text_delta": 2,
        "raw_content_delta": 1,
        "tool_call_input_delta": 0,
        "reasoning_delta": 0,
        "emitted_stream": 0,
    }
    assert event_summaries[2]["state_after"]["stream_event_counts"] == {
        "metadata": 0,
        "output_item_done": 1,
        "output_item_added": 1,
        "output_text_delta": 1,
        "assistant_text_delta": 2,
        "raw_content_delta": 1,
        "tool_call_input_delta": 0,
        "reasoning_delta": 0,
        "emitted_stream": 0,
    }
    assert event_summaries[2]["state_after"]["should_continue_loop"] is True
    assert result.phase_results[1]["step_types"] == (
        "drain_in_flight",
        "return_sampling_result",
    )


def test_execute_sampling_request_runtime_state_driven_plan_traces_mailbox_follow_up_state():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    output_result = OutputItemResult(
        last_agent_message="tool result tail",
        needs_follow_up=True,
        tool_future="future",
    )
    state_after = SamplingOutputState(
        needs_follow_up=True,
        last_agent_message="state tail",
        in_flight=("future",),
    )
    mailbox_preemption = SamplingMailboxPreemptionPlan(
        needs_follow_up=True,
        last_agent_message="mailbox tail",
    )
    done_plan = SamplingStreamEventApplyPlan(
        event_type="response.output_item.done",
        output_item_done_apply_plan=SamplingOutputItemDoneApplyPlan(
            transition_plan=SamplingOutputItemDoneTransitionPlan(),
            should_continue_loop=True,
            preempt_for_mailbox_mail=True,
            output_result=output_result,
            state_after_output_result=state_after,
            mailbox_preemption_plan=mailbox_preemption,
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(),
        event_apply_plans=(done_plan,),
        state=state,
        hooks=adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    event_summary = result.phase_results[0]["event_summaries"][0]
    assert event_summary["event_type"] == "response.output_item.done"
    assert event_summary["state_after"]["should_continue_loop"] is True
    assert event_summary["state_after"]["preempt_for_mailbox_mail"] is True
    assert event_summary["state_after"]["follow_up_state"] == {
        "needs_follow_up": True,
        "last_agent_message": "mailbox tail",
        "has_output_result": True,
        "has_state_after_output_result": True,
        "has_mailbox_preemption_plan": True,
    }
    assert result.final_result == {
        "needs_follow_up": True,
        "last_agent_message": "mailbox tail",
    }


def test_execute_sampling_request_runtime_state_driven_plan_traces_metadata_events():
    state = SamplingRuntimeEventApplicationState()
    adapter = SamplingRequestRuntimeHookAdapter(event_application_state=state)
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-1",
            token_usage_to_record={"total_tokens": 42},
            completed_response_id_after="resp-1",
        ),
    )
    reasoning_metadata_plan = SamplingStreamEventApplyPlan(
        event_type="server_reasoning_included",
        metadata_event_apply_plan=SamplingMetadataEventApplyPlan(
            event_type="server_reasoning_included",
            server_reasoning_included=True,
        ),
    )
    rate_limits_plan = SamplingStreamEventApplyPlan(
        event_type="rate_limits",
        metadata_event_apply_plan=SamplingMetadataEventApplyPlan(
            event_type="rate_limits",
            rate_limits_to_record={"remaining": 9},
            should_emit_token_count=True,
        ),
    )
    models_etag_plan = SamplingStreamEventApplyPlan(
        event_type="models_etag",
        metadata_event_apply_plan=SamplingMetadataEventApplyPlan(
            event_type="models_etag",
            models_etag_to_refresh="etag-1",
        ),
    )

    result = execute_sampling_request_runtime_state_driven_plan(
        FeatureSet(),
        event_apply_plans=(
            completed_plan,
            reasoning_metadata_plan,
            rate_limits_plan,
            models_etag_plan,
        ),
        state=state,
        hooks=adapter,
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    event_summaries = result.phase_results[0]["event_summaries"]
    assert tuple(summary["event_type"] for summary in event_summaries) == (
        "completed",
        "server_reasoning_included",
        "rate_limits",
        "models_etag",
    )
    assert event_summaries[0]["state_after"]["metadata_state"] == {
        "has_token_usage_to_record": True,
        "server_reasoning_included": None,
        "has_rate_limits_to_record": False,
        "models_etag_to_refresh": None,
    }
    assert event_summaries[1]["state_after"]["metadata_state"] == {
        "has_token_usage_to_record": True,
        "server_reasoning_included": True,
        "has_rate_limits_to_record": False,
        "models_etag_to_refresh": None,
    }
    assert event_summaries[2]["state_after"]["metadata_state"] == {
        "has_token_usage_to_record": True,
        "server_reasoning_included": True,
        "has_rate_limits_to_record": True,
        "models_etag_to_refresh": None,
    }
    assert event_summaries[2]["state_after"]["should_emit_token_count"] is True
    assert event_summaries[2]["state_after"]["stream_event_counts"]["metadata"] == 2
    assert event_summaries[3]["state_after"]["metadata_state"] == {
        "has_token_usage_to_record": True,
        "server_reasoning_included": True,
        "has_rate_limits_to_record": True,
        "models_etag_to_refresh": "etag-1",
    }
    assert event_summaries[3]["state_after"]["stream_event_counts"]["metadata"] == 3


def test_sampling_request_runtime_hook_adapter_noops_without_optional_io():
    adapter = SamplingRequestRuntimeHookAdapter()

    assert adapter.send_response_processed(
        {"type": "send_response_processed", "request": {"response_id": "resp-1"}}
    ) == {
        "sent": False,
        "reason": "missing_connection",
        "request": {"response_id": "resp-1"},
    }
    assert adapter.drain_in_flight({"type": "drain_in_flight"}) == {
        "drained": False,
        "reason": "missing_drainer",
    }
    assert adapter.send_token_count({"type": "send_token_count"}) == {
        "sent": False,
        "reason": "missing_token_count_sender",
    }
    assert adapter.send_turn_diff(
        {"type": "send_turn_diff", "unified_diff": "diff"}
    ) == {
        "sent": False,
        "reason": "missing_turn_diff_sender",
        "unified_diff": "diff",
    }
    assert adapter.return_sampling_result(
        {
            "type": "return_sampling_result",
            "needs_follow_up": True,
            "last_agent_message": "tail",
        }
    ) == {"needs_follow_up": True, "last_agent_message": "tail"}
    assert adapter.return_turn_aborted({"type": "return_turn_aborted"}) == {
        "error": "turn_aborted",
    }


def test_response_create_client_metadata_merges_w3c_trace_context():
    metadata = response_create_client_metadata(
        {"existing": "value"},
        SimpleNamespace(traceparent="00-abc", tracestate="vendor=state"),
    )

    assert metadata == {
        "existing": "value",
        WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "00-abc",
        WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY: "vendor=state",
    }


def test_response_create_client_metadata_returns_none_when_empty():
    assert response_create_client_metadata(None, None) is None


def test_response_create_client_metadata_trace_overrides_reserved_keys():
    metadata = response_create_client_metadata(
        {WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "old"},
        {"traceparent": "new"},
    )

    assert metadata == {WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "new"}


def test_response_create_client_metadata_rejects_non_string_values():
    with pytest.raises(TypeError, match="client_metadata values must be strings"):
        response_create_client_metadata({"bad": 1}, None)  # type: ignore[dict-item]
    with pytest.raises(TypeError, match="traceparent must be a string"):
        response_create_client_metadata(None, {"traceparent": 1})


def test_build_websocket_payload_replaces_http_metadata_with_ws_metadata_and_trace():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    request = {
        "model": "m",
        "input": [],
        "client_metadata": {"http-only": "value"},
    }

    payload = client.build_websocket_payload(
        request,
        trace={"traceparent": "00-abc", "tracestate": "vendor=state"},
        turn_metadata_header="turn-meta",
    )

    assert request["client_metadata"] == {"http-only": "value"}
    assert payload["client_metadata"] == {
        X_CODEX_INSTALLATION_ID_HEADER: "install",
        X_CODEX_WINDOW_ID_HEADER: "thread:0",
        X_CODEX_TURN_METADATA_HEADER: "turn-meta",
        WS_REQUEST_HEADER_TRACEPARENT_CLIENT_METADATA_KEY: "00-abc",
        WS_REQUEST_HEADER_TRACESTATE_CLIENT_METADATA_KEY: "vendor=state",
    }


def test_build_responses_request_uses_model_default_verbosity_when_state_unset():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-test",
        support_verbosity=True,
        default_verbosity="medium",
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info)

    assert request["text"]["verbosity"] == "medium"


def test_build_responses_request_state_verbosity_overrides_model_default():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", model_verbosity="high")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-test",
        support_verbosity=True,
        default_verbosity="medium",
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info)

    assert request["text"]["verbosity"] == "high"


def test_create_text_param_for_request_matches_rust_shapes():
    assert create_text_param_for_request(None, None, True) is None

    schema = {"type": "object", "properties": {"answer": {"type": "string"}}}
    text = create_text_param_for_request(None, schema, False)

    assert text == {
        "format": {
            "type": "json_schema",
            "strict": False,
            "schema": schema,
            "name": "codex_output_schema",
        }
    }


def test_build_responses_request_omits_text_controls_when_unset():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-test",
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info)

    assert request["text"] is None


def test_build_responses_request_records_ignored_model_verbosity_when_unsupported():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", model_verbosity="high")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-no-verbosity",
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info)

    assert request["text"] is None
    assert client.state.last_request_diagnostics == {
        "model_verbosity_ignored": {
            "model": "gpt-no-verbosity",
            "verbosity": "high",
            "reason": "model does not support verbosity",
        }
    }


def test_build_responses_request_clears_previous_diagnostics_on_next_request():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install", model_verbosity="high")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    unsupported = SimpleNamespace(
        slug="gpt-no-verbosity",
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )
    supported = SimpleNamespace(
        slug="gpt-with-verbosity",
        support_verbosity=True,
        default_verbosity="medium",
        service_tier_for_request=lambda tier: tier,
    )

    client.build_responses_request(provider, Prompt.default(), unsupported)
    request = client.build_responses_request(provider, Prompt.default(), supported)

    assert request["text"]["verbosity"] == "high"
    assert client.state.last_request_diagnostics == {}


def test_build_responses_request_includes_encrypted_reasoning_when_reasoning_is_present():
    client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
    )
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-reasoning",
        supports_reasoning_summaries=True,
        default_reasoning_level="medium",
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info, effort="high", summary="auto")

    assert request["reasoning"] == {"effort": "high", "summary": "auto"}
    assert request["include"] == ["reasoning.encrypted_content"]


def test_build_responses_request_omits_encrypted_reasoning_include_when_reasoning_is_absent():
    client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
    )
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-no-reasoning",
        supports_reasoning_summaries=False,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info, effort="high", summary="auto")

    assert request["reasoning"] is None
    assert request["include"] == []


def test_build_responses_request_uses_default_reasoning_effort_and_omits_none_summary():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-default-reasoning",
        supports_reasoning_summaries=True,
        default_reasoning_level="medium",
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(provider, Prompt.default(), model_info, effort=None, summary=None)

    assert request["reasoning"] == {"effort": "medium", "summary": None}
    assert request["include"] == ["reasoning.encrypted_content"]


def test_build_responses_request_treats_reasoning_summary_none_enum_as_absent_summary():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-default-reasoning",
        supports_reasoning_summaries=True,
        default_reasoning_level="medium",
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier,
    )

    request = client.build_responses_request(
        provider,
        Prompt.default(),
        model_info,
        effort=None,
        summary=ReasoningSummary.NONE,
    )

    assert request["reasoning"] == {"effort": "medium", "summary": None}


def test_build_responses_request_normalizes_service_tier_request_values():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    provider = SimpleNamespace(is_azure_responses_endpoint=lambda: False)
    model_info = SimpleNamespace(
        slug="gpt-service-tier",
        supports_reasoning_summaries=False,
        support_verbosity=False,
        service_tier_for_request=lambda tier: tier if tier in {"priority", "flex"} else None,
    )

    fast_request = client.build_responses_request(
        provider,
        Prompt.default(),
        model_info,
        service_tier=ServiceTier.FAST,
    )
    legacy_fast_request = client.build_responses_request(
        provider,
        Prompt.default(),
        model_info,
        service_tier="fast",
    )

    assert fast_request["service_tier"] == "priority"
    assert legacy_fast_request["service_tier"] == "priority"


def test_serialize_responses_request_matches_rust_skip_rules():
    request = {
        "model": "gpt-test",
        "instructions": "",
        "input": [],
        "tools": [],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "reasoning": None,
        "store": False,
        "stream": True,
        "include": [],
        "service_tier": None,
        "prompt_cache_key": None,
        "text": None,
        "client_metadata": None,
    }

    serialized = serialize_responses_request(request)

    assert "instructions" not in serialized
    assert "service_tier" not in serialized
    assert "prompt_cache_key" not in serialized
    assert "text" not in serialized
    assert "client_metadata" not in serialized
    assert serialized["reasoning"] is None


def test_serialize_responses_request_serializes_nested_enum_values():
    request = {
        "model": "gpt-test",
        "instructions": "base",
        "input": [],
        "tools": [],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "reasoning": {"effort": ReasoningEffort.HIGH},
        "store": False,
        "stream": True,
        "include": [],
    }

    serialized = serialize_responses_request(request)

    assert serialized["reasoning"] == {"effort": "high"}


def test_prepare_websocket_request_uses_serialized_payload_shape():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    payload = {
        "model": "m",
        "instructions": "",
        "input": [],
        "tools": [],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "reasoning": None,
        "store": False,
        "stream": True,
        "include": [],
        "service_tier": None,
        "prompt_cache_key": None,
        "text": None,
        "client_metadata": None,
    }

    prepared, from_warmup = session.prepare_websocket_request(payload, payload)

    assert from_warmup is False
    assert prepared["type"] == "response.create"
    assert "instructions" not in prepared
    assert "text" not in prepared
    assert "client_metadata" not in prepared


def test_prepare_websocket_request_wraps_incremental_delta_as_response_create():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    first = ResponseItem.message("one")
    second = ResponseItem.message("two")
    payload = {
        "model": "m",
        "instructions": "",
        "input": [first, second],
        "tools": [],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "reasoning": None,
        "store": False,
        "stream": True,
        "include": [],
        "service_tier": None,
        "prompt_cache_key": None,
        "text": None,
        "client_metadata": None,
    }
    previous = dict(payload)
    previous["input"] = [first]
    session.websocket_session.last_request = previous
    session.websocket_session.last_response = LastResponse("resp-1")

    prepared, from_warmup = session.prepare_websocket_request(payload, payload)

    assert from_warmup is False
    assert prepared["type"] == "response.create"
    assert prepared["previous_response_id"] == "resp-1"
    assert prepared["input"] == [second]


def test_prepare_http_request_uses_serialized_request_shape():
    client = ModelClient(session_id="session", thread_id="thread", installation_id="install")
    session = client.new_session()
    request = {
        "model": "m",
        "instructions": "",
        "input": [],
        "tools": [],
        "tool_choice": "auto",
        "parallel_tool_calls": False,
        "reasoning": None,
        "store": False,
        "stream": True,
        "include": [],
        "service_tier": None,
        "prompt_cache_key": None,
        "text": None,
        "client_metadata": None,
    }

    prepared = session.prepare_http_request(request)

    assert "instructions" not in prepared
    assert "service_tier" not in prepared
    assert "text" not in prepared
    assert prepared["reasoning"] is None


def test_create_tools_json_for_responses_api_serializes_tool_specs():
    tool = ToolSpec.freeform(
        name="run_python",
        description="Run a Python snippet",
        format=FreeformToolFormat.grammar(syntax="python", definition="stmt = .+"),
    )

    assert create_tools_json_for_responses_api([tool]) == [
        {
            "type": "custom",
            "name": "run_python",
            "description": "Run a Python snippet",
            "format": {
                "type": "grammar",
                "syntax": "python",
                "definition": "stmt = .+",
            },
        }
    ]


def test_create_tools_json_for_responses_api_preserves_mapping_tools():
    tool = {"type": "function", "name": "plain_mapping"}

    assert create_tools_json_for_responses_api([tool]) == [{"type": "function", "name": "plain_mapping"}]


def test_create_tools_json_for_responses_api_serializes_nested_enum_values():
    tool = {
        "type": "function",
        "name": "plain_mapping",
        "metadata": {"effort": ReasoningEffort.HIGH},
    }

    assert create_tools_json_for_responses_api([tool]) == [
        {
            "type": "function",
            "name": "plain_mapping",
            "metadata": {"effort": "high"},
        }
    ]


def test_create_tools_json_for_responses_api_rejects_non_json_tool():
    with pytest.raises(TypeError, match="tool must be a mapping"):
        create_tools_json_for_responses_api([object()])
