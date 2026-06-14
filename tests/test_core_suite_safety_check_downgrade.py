from pycodex.core.safety_check_downgrade import (
    CYBER_POLICY_MESSAGE,
    TRUSTED_ACCESS_FOR_CYBER_VERIFICATION,
    SafetyCheckAttempt,
    cyber_policy_error_event,
    model_reroute_events,
    model_verification_events,
    observed_model_from_response,
    safety_check_events_for_turn,
)
from pycodex.protocol import (
    CodexErrorInfo,
    ErrorEvent,
    EventMsg,
    ModelRerouteEvent,
    ModelRerouteReason,
    ModelVerification,
    ModelVerificationEvent,
    WarningEvent,
)

SERVER_MODEL = "gpt-5.2"
REQUESTED_MODEL = "gpt-5.3-codex"


def _payloads(events: tuple[EventMsg, ...], event_type: str):
    return [event.payload for event in events if event.type == event_type]


def test_openai_model_header_mismatch_emits_warning_event():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `openai_model_header_mismatch_emits_warning_event`.
    observed = observed_model_from_response(http_headers={"OpenAI-Model": SERVER_MODEL})

    events = model_reroute_events(REQUESTED_MODEL, observed)

    assert events[0] == EventMsg.with_payload(
        "model_reroute",
        ModelRerouteEvent(
            REQUESTED_MODEL,
            SERVER_MODEL,
            ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY,
        ),
    )
    assert isinstance(events[1].payload, WarningEvent)
    assert REQUESTED_MODEL in events[1].payload.message
    assert SERVER_MODEL in events[1].payload.message


def test_cyber_policy_response_emits_typed_error_without_retry():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `cyber_policy_response_emits_typed_error_without_retry`.
    event = cyber_policy_error_event(CYBER_POLICY_MESSAGE)

    assert event == EventMsg.with_payload(
        "error",
        ErrorEvent(CYBER_POLICY_MESSAGE, CodexErrorInfo.cyber_policy()),
    )
    assert len(safety_check_events_for_turn(REQUESTED_MODEL, (SafetyCheckAttempt(error_code="cyber_policy"),))) == 1


def test_response_model_field_mismatch_emits_warning_when_header_matches_requested():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `response_model_field_mismatch_emits_warning_when_header_matches_requested`.
    observed = observed_model_from_response(response_created_headers={"OpenAI-Model": SERVER_MODEL})

    events = model_reroute_events(REQUESTED_MODEL, observed)
    warning = events[1].payload

    assert events[0].payload == ModelRerouteEvent(
        REQUESTED_MODEL,
        SERVER_MODEL,
        ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY,
    )
    assert isinstance(warning, WarningEvent)
    assert "flagged for potentially high-risk cyber activity" in warning.message
    assert REQUESTED_MODEL in warning.message
    assert SERVER_MODEL in warning.message


def test_openai_model_header_mismatch_only_emits_one_warning_per_turn():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `openai_model_header_mismatch_only_emits_one_warning_per_turn`.
    events = safety_check_events_for_turn(
        REQUESTED_MODEL,
        (
            SafetyCheckAttempt(observed_model=SERVER_MODEL),
            SafetyCheckAttempt(observed_model=SERVER_MODEL),
        ),
    )

    warnings = _payloads(events, "warning")
    assert len([warning for warning in warnings if REQUESTED_MODEL in warning.message]) == 1


def test_openai_model_header_casing_only_mismatch_does_not_warn():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `openai_model_header_casing_only_mismatch_does_not_warn`.
    events = model_reroute_events(REQUESTED_MODEL, REQUESTED_MODEL.upper())

    assert _payloads(events, "model_reroute") == []
    assert _payloads(events, "warning") == []


def test_model_verification_emits_structured_event_without_reroute_or_warning():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `model_verification_emits_structured_event_without_reroute_or_warning`.
    events = model_verification_events((TRUSTED_ACCESS_FOR_CYBER_VERIFICATION,))

    assert events == (
        EventMsg.with_payload(
            "model_verification",
            ModelVerificationEvent((ModelVerification.TRUSTED_ACCESS_FOR_CYBER,)),
        ),
    )
    assert _payloads(events, "warning") == []
    assert _payloads(events, "model_reroute") == []


def test_model_verification_only_emits_once_per_turn():
    # Rust: core/tests/suite/safety_check_downgrade.rs
    # test `model_verification_only_emits_once_per_turn`.
    events = safety_check_events_for_turn(
        REQUESTED_MODEL,
        (
            SafetyCheckAttempt(model_verifications=(TRUSTED_ACCESS_FOR_CYBER_VERIFICATION,)),
            SafetyCheckAttempt(model_verifications=(TRUSTED_ACCESS_FOR_CYBER_VERIFICATION,)),
        ),
    )

    assert len(_payloads(events, "model_verification")) == 1
    assert "high-risk cyber activity" not in " ".join(
        warning.message for warning in _payloads(events, "warning")
    )
