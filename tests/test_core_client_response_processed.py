from pycodex.core import (
    SamplingCompletedEventApplyPlan,
    SamplingStreamEventApplyPlan,
    response_processed_request_for_sampling_turn,
    response_processed_ws_request,
    sampling_request_state_machine_plan,
)
from pycodex.features import Feature


class FeatureSet:
    def __init__(self, *features: Feature) -> None:
        self.features = set(features)

    def enabled(self, feature: Feature) -> bool:
        return feature in self.features


def _completed_plan(response_id: str = "resp-1") -> SamplingStreamEventApplyPlan:
    return SamplingStreamEventApplyPlan(
        event_type="completed",
        completed_event_apply_plan=SamplingCompletedEventApplyPlan(
            response_id=response_id,
            completed_response_id_after=response_id,
        ),
    )


def test_response_processed_ws_request_matches_rust_payload_shape():
    # Rust source: codex/codex-rs/codex-api/src/endpoint/responses_websocket.rs
    # Rust suite: responses_websocket_sends_response_processed_when_feature_enabled.
    assert response_processed_ws_request("resp-1") == {
        "type": "response.processed",
        "response_id": "resp-1",
    }


def test_response_processed_request_requires_feature_success_and_completed_id():
    # Rust source: codex/codex-rs/core/src/client.rs::send_response_processed.
    # Rust suite: enabled sends response.processed; disabled omits it.
    enabled = FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED)
    disabled = FeatureSet()

    assert response_processed_request_for_sampling_turn(
        enabled,
        outcome_ok=True,
        completed_response_id="resp-1",
    ) == {"type": "response.processed", "response_id": "resp-1"}
    assert response_processed_request_for_sampling_turn(
        disabled,
        outcome_ok=True,
        completed_response_id="resp-1",
    ) is None
    assert response_processed_request_for_sampling_turn(
        enabled,
        outcome_ok=False,
        completed_response_id="resp-1",
    ) is None
    assert response_processed_request_for_sampling_turn(
        enabled,
        outcome_ok=True,
        completed_response_id=None,
    ) is None


def test_sampling_state_machine_schedules_response_processed_when_feature_enabled():
    # Rust suite: responses_websocket_sends_response_processed_when_feature_enabled.
    plan = sampling_request_state_machine_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=(_completed_plan("resp-1"),),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert plan.loop_tail_plan.response_processed_request == {
        "type": "response.processed",
        "response_id": "resp-1",
    }


def test_sampling_state_machine_omits_response_processed_without_feature():
    # Rust suite: responses_websocket_omits_response_processed_without_feature.
    plan = sampling_request_state_machine_plan(
        FeatureSet(),
        event_apply_plans=(_completed_plan("resp-1"),),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert plan.loop_tail_plan.response_processed_request is None


def test_sampling_state_machine_schedules_response_processed_after_compaction_completion():
    # Rust suite: responses_websocket_sends_response_processed_after_remote_compaction_v2.
    plan = sampling_request_state_machine_plan(
        FeatureSet(Feature.RESPONSES_WEBSOCKET_RESPONSE_PROCESSED),
        event_apply_plans=(_completed_plan("resp-compact"),),
        outcome_ok=True,
        cancellation_requested=False,
        unified_diff=None,
    )

    assert plan.loop_tail_plan.response_processed_request == {
        "type": "response.processed",
        "response_id": "resp-compact",
    }
