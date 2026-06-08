from types import SimpleNamespace

from pycodex.core import (
    ModelClient,
    SamplingCompletedEventApplyPlan,
    SamplingOutputItemDoneApplyPlan,
    SamplingOutputItemDoneTransitionPlan,
    SamplingStreamEventApplyPlan,
    prepare_and_execute_sampling_request_runtime_state_driven_session_plan,
)
from pycodex.protocol import ContentItem, ResponseItem


class FeatureSet:
    def enabled(self, feature) -> bool:
        return False


def _session():
    provider = SimpleNamespace(info=lambda: SimpleNamespace(supports_websockets=True))
    client = ModelClient(
        session_id="session",
        thread_id="thread",
        installation_id="install",
        provider=provider,
    )
    session = client.new_session()
    session.websocket_session.connection = object()
    return session


def _assistant_item(text: str = "partial answer") -> ResponseItem:
    return ResponseItem.message("assistant", (ContentItem.output_text(text),))


def test_stream_mapping_records_last_model_feedback_ids_on_completed():
    # Rust source: codex/codex-rs/core/src/client.rs::map_response_events.
    # Rust test: response_stream_records_last_model_feedback_ids.
    session = _session()
    request = {"model": "m", "input": [ResponseItem.message("user", ())]}
    completed_plan = SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id="resp-123",
            completed_response_id_after="resp-123",
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
        websocket_upstream_request_id="req-123",
    )

    assert result.websocket_feedback_tags == {
        "last_model_request_id": "req-123",
        "last_model_response_id": "resp-123",
    }
    assert result.inference_trace_completed == {
        "response_id": "resp-123",
        "request_id": "req-123",
        "token_usage": None,
        "output_items": (),
    }


def test_stream_mapping_closed_before_completed_preserves_partial_output():
    # Rust source: codex/codex-rs/core/src/client.rs::map_response_events.
    # Rust behavior anchor: stream closed before response.completed records failure
    # with output items already observed.
    session = _session()
    user_item = ResponseItem.message("user", ())
    assistant_item = _assistant_item()
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
        websocket_connection_needs_new=False,
        websocket_stream_closed_before_completed=True,
        websocket_upstream_request_id="req-closed",
    )

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


def test_stream_mapping_consumer_dropped_records_cancelled_partial_output():
    # Rust source: codex/codex-rs/core/src/client.rs::map_response_events.
    # Rust tests: dropped_response_stream_traces_cancelled_partial_output and
    # dropped_backpressured_response_stream_traces_cancelled_partial_output.
    session = _session()
    user_item = ResponseItem.message("user", ())
    assistant_item = _assistant_item()
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
        websocket_connection_needs_new=False,
        websocket_consumer_dropped=True,
        websocket_upstream_request_id="req-drop",
    )

    assert result.websocket_stream_result == {
        "status": "cancelled",
        "stream_mapped": True,
        "last_response_receiver_registered": True,
        "terminal_event": "consumer_dropped",
    }
    assert result.inference_trace_cancelled == {
        "reason": "response stream dropped before provider terminal event",
        "request_id": "req-drop",
        "output_items": (assistant_item,),
    }
    assert result.websocket_feedback_tags == {"last_model_request_id": "req-drop"}
