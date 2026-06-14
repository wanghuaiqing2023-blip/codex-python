"""Model safety downgrade signal helpers.

Rust parity anchor:
- `codex-rs/core/tests/suite/safety_check_downgrade.rs`

The Rust tests exercise session/runtime behavior, but the stable behavior
contract is the same small set of user-visible events:

- model mismatch means a high-risk-cyber reroute event plus one warning;
- cyber policy errors become typed `ErrorEvent`s and are not retried;
- trusted cyber-access verification becomes one structured verification event.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

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

CYBER_POLICY_MESSAGE = "This request has been flagged for potentially high-risk cyber activity."
TRUSTED_ACCESS_FOR_CYBER_VERIFICATION = "trusted_access_for_cyber"


@dataclass(frozen=True)
class SafetyCheckAttempt:
    """Observed safety-relevant response signals from one model attempt."""

    observed_model: str | None = None
    model_verifications: tuple[str | ModelVerification, ...] = ()
    error_code: str | None = None
    error_message: str | None = None


def normalize_model_for_compare(model: str | None) -> str | None:
    """Return the Rust-style case-insensitive comparison key for model slugs."""

    if model is None:
        return None
    return model.casefold()


def is_model_mismatch(requested_model: str | None, observed_model: str | None) -> bool:
    """Whether a server-observed model should be treated as a reroute."""

    if not requested_model or not observed_model:
        return False
    return normalize_model_for_compare(requested_model) != normalize_model_for_compare(observed_model)


def model_reroute_warning_message(requested_model: str, observed_model: str) -> str:
    """Warning text used when a model mismatch indicates safety downgrade."""

    return (
        f"{CYBER_POLICY_MESSAGE} Requested model {requested_model!r} was served by "
        f"{observed_model!r}."
    )


def model_reroute_events(
    requested_model: str,
    observed_model: str | None,
    *,
    already_emitted: bool = False,
) -> tuple[EventMsg, ...]:
    """Return the Rust-visible reroute events for one turn.

    Rust emits at most one reroute warning per turn, and model name casing alone
    must not trigger the warning path.
    """

    if already_emitted or not is_model_mismatch(requested_model, observed_model):
        return ()
    assert observed_model is not None
    return (
        EventMsg.with_payload(
            "model_reroute",
            ModelRerouteEvent(
                from_model=requested_model,
                to_model=observed_model,
                reason=ModelRerouteReason.HIGH_RISK_CYBER_ACTIVITY,
            ),
        ),
        EventMsg.with_payload("warning", WarningEvent(model_reroute_warning_message(requested_model, observed_model))),
    )


def cyber_policy_error_event(message: str = CYBER_POLICY_MESSAGE) -> EventMsg:
    """Return the typed event for an OpenAI cyber-policy error response."""

    return EventMsg.with_payload("error", ErrorEvent(message, CodexErrorInfo.cyber_policy()))


def is_cyber_policy_error(code: str | None, message: str | None = None) -> bool:
    """Whether an error response corresponds to Rust's cyber-policy handling."""

    if code == "cyber_policy":
        return True
    return message == CYBER_POLICY_MESSAGE


def model_verifications_from_metadata(values: Iterable[str | ModelVerification] | None) -> tuple[ModelVerification, ...]:
    """Convert response metadata verification strings into protocol values."""

    if values is None:
        return ()

    verifications: list[ModelVerification] = []
    for value in values:
        parsed: ModelVerification | None
        if isinstance(value, ModelVerification):
            parsed = value
        elif value == TRUSTED_ACCESS_FOR_CYBER_VERIFICATION:
            parsed = ModelVerification.TRUSTED_ACCESS_FOR_CYBER
        else:
            parsed = None

        if parsed is not None and parsed not in verifications:
            verifications.append(parsed)

    return tuple(verifications)


def model_verification_events(
    values: Iterable[str | ModelVerification] | None,
    *,
    already_emitted: bool = False,
) -> tuple[EventMsg, ...]:
    """Return a structured model-verification event, at most once per turn."""

    if already_emitted:
        return ()

    verifications = model_verifications_from_metadata(values)
    if not verifications:
        return ()

    return (EventMsg.with_payload("model_verification", ModelVerificationEvent(verifications)),)


def observed_model_from_response(
    *,
    http_headers: Mapping[str, str] | None = None,
    response_created_headers: Mapping[str, str] | None = None,
) -> str | None:
    """Extract the server-selected model from HTTP or response-created headers."""

    for headers in (http_headers, response_created_headers):
        if not headers:
            continue
        for key, value in headers.items():
            if key.casefold() == "openai-model":
                return value
    return None


def safety_check_events_for_turn(requested_model: str, attempts: Sequence[SafetyCheckAttempt]) -> tuple[EventMsg, ...]:
    """Collect Rust-equivalent safety events across one turn.

    This mirrors the Rust tests' once-per-turn behavior for reroute warnings and
    model verification events. Cyber-policy errors are terminal for that attempt
    and produce the typed error event without retry semantics.
    """

    events: list[EventMsg] = []
    reroute_emitted = False
    verification_emitted = False

    for attempt in attempts:
        if is_cyber_policy_error(attempt.error_code, attempt.error_message):
            events.append(cyber_policy_error_event(attempt.error_message or CYBER_POLICY_MESSAGE))
            continue

        reroute = model_reroute_events(
            requested_model,
            attempt.observed_model,
            already_emitted=reroute_emitted,
        )
        if reroute:
            reroute_emitted = True
            events.extend(reroute)

        verification = model_verification_events(
            attempt.model_verifications,
            already_emitted=verification_emitted,
        )
        if verification:
            verification_emitted = True
            events.extend(verification)

    return tuple(events)


__all__ = [
    "CYBER_POLICY_MESSAGE",
    "TRUSTED_ACCESS_FOR_CYBER_VERIFICATION",
    "SafetyCheckAttempt",
    "cyber_policy_error_event",
    "is_cyber_policy_error",
    "is_model_mismatch",
    "model_reroute_events",
    "model_reroute_warning_message",
    "model_verification_events",
    "model_verifications_from_metadata",
    "normalize_model_for_compare",
    "observed_model_from_response",
    "safety_check_events_for_turn",
]
