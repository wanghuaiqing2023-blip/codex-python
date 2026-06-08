from types import SimpleNamespace

import pytest

from pycodex.core.guardian.review import (
    DEFAULT_GUARDIAN_REJECTION_RATIONALE,
    GUARDIAN_REJECTION_INSTRUCTIONS,
    GuardianRejection,
    guardian_rejection_message,
    guardian_rejection_message_for_rejection,
    guardian_risk_level_str,
    guardian_timeout_message,
)
from pycodex.protocol import GuardianRiskLevel


def test_guardian_timeout_message_matches_rust_user_visible_contract() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/review.rs::guardian_timeout_message
    # Rust test: guardian_timeout_message_distinguishes_timeout_from_policy_denial
    message = guardian_timeout_message()

    assert "did not finish before its deadline" in message
    assert "retry once" in message
    assert "unacceptable risk" not in message


def test_guardian_risk_level_str_matches_rust_labels() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/review.rs::guardian_risk_level_str
    assert guardian_risk_level_str(GuardianRiskLevel.LOW) == "low"
    assert guardian_risk_level_str(GuardianRiskLevel.MEDIUM) == "medium"
    assert guardian_risk_level_str(GuardianRiskLevel.HIGH) == "high"
    assert guardian_risk_level_str(GuardianRiskLevel.CRITICAL) == "critical"


def test_guardian_rejection_message_trims_rationale_and_appends_instructions() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/review.rs::guardian_rejection_message
    message = guardian_rejection_message_for_rejection(GuardianRejection("  risky command  "))

    assert message == (
        "This action was rejected due to unacceptable risk.\n"
        "Reason: risky command\n"
        f"{GUARDIAN_REJECTION_INSTRUCTIONS}"
    )


def test_guardian_rejection_message_uses_default_for_missing_or_empty_rationale() -> None:
    # Rust behavior: missing stored rejection or blank rationale falls back to the
    # default auto-reviewer rationale before formatting the denial message.
    missing = guardian_rejection_message_for_rejection(None)
    blank = guardian_rejection_message_for_rejection({"rationale": "   "})

    assert f"Reason: {DEFAULT_GUARDIAN_REJECTION_RATIONALE}" in missing
    assert f"Reason: {DEFAULT_GUARDIAN_REJECTION_RATIONALE}" in blank


@pytest.mark.asyncio
async def test_guardian_rejection_message_pops_session_rejection_by_review_id() -> None:
    # Rust source: codex/codex-rs/core/src/guardian/review.rs::guardian_rejection_message
    guardian_rejections = {
        "review-1": GuardianRejection("deny this"),
        "review-2": GuardianRejection("keep this"),
    }
    session = SimpleNamespace(services=SimpleNamespace(guardian_rejections=guardian_rejections))

    message = await guardian_rejection_message(session, "review-1")

    assert "Reason: deny this" in message
    assert "review-1" not in guardian_rejections
    assert "review-2" in guardian_rejections
