from dataclasses import asdict
from pathlib import Path

from pycodex.analytics import (
    AnalyticsJsonRpcError,
    CodexCompactionEvent,
    CompactionImplementation,
    CompactionPhase,
    CompactionReason,
    CompactionStatus,
    CompactionStrategy,
    CompactionTrigger,
    InputError,
    ThreadInitializationMode,
    TurnResolvedConfigFact,
    TurnSteerRejectionReason,
    TurnSteerRequestError,
    TurnStatus,
    TurnSubmissionType,
    turn_steer_rejection_reason_from_error,
)


def test_facts_enums_use_rust_serde_values() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/facts.rs
    # Contract: public facts enums use Rust serde rename_all values.
    assert [item.value for item in TurnSubmissionType] == ["default", "queued"]
    assert [item.value for item in ThreadInitializationMode] == ["new", "forked", "resumed"]
    assert [item.value for item in TurnStatus] == ["completed", "failed", "interrupted"]
    assert [item.value for item in CompactionTrigger] == ["manual", "auto"]
    assert [item.value for item in CompactionReason] == ["user_requested", "context_limit", "model_downshift"]
    assert [item.value for item in CompactionImplementation] == [
        "responses",
        "responses_compaction_v2",
        "responses_compact",
    ]
    assert [item.value for item in CompactionPhase] == ["standalone_turn", "pre_turn", "mid_turn"]
    assert [item.value for item in CompactionStrategy] == ["memento", "prefix_compaction"]
    assert [item.value for item in CompactionStatus] == ["completed", "failed", "interrupted"]


def test_turn_steer_errors_convert_to_rejection_reasons() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/facts.rs
    # Rust item: impl From<TurnSteerRequestError/InputError> for TurnSteerRejectionReason
    # Contract: JSON-RPC steer/input errors map to analytics rejection reasons.
    assert turn_steer_rejection_reason_from_error(TurnSteerRequestError.NO_ACTIVE_TURN) == (
        TurnSteerRejectionReason.NO_ACTIVE_TURN
    )
    assert turn_steer_rejection_reason_from_error(TurnSteerRequestError.EXPECTED_TURN_MISMATCH) == (
        TurnSteerRejectionReason.EXPECTED_TURN_MISMATCH
    )
    assert turn_steer_rejection_reason_from_error(TurnSteerRequestError.NON_STEERABLE_REVIEW) == (
        TurnSteerRejectionReason.NON_STEERABLE_REVIEW
    )
    assert turn_steer_rejection_reason_from_error(TurnSteerRequestError.NON_STEERABLE_COMPACT) == (
        TurnSteerRejectionReason.NON_STEERABLE_COMPACT
    )
    assert turn_steer_rejection_reason_from_error(InputError.EMPTY) == TurnSteerRejectionReason.EMPTY_INPUT
    assert turn_steer_rejection_reason_from_error(InputError.TOO_LARGE) == TurnSteerRejectionReason.INPUT_TOO_LARGE
    assert turn_steer_rejection_reason_from_error(
        AnalyticsJsonRpcError.turn_steer(TurnSteerRequestError.NON_STEERABLE_COMPACT)
    ) == TurnSteerRejectionReason.NON_STEERABLE_COMPACT
    assert turn_steer_rejection_reason_from_error(AnalyticsJsonRpcError.input(InputError.TOO_LARGE)) == (
        TurnSteerRejectionReason.INPUT_TOO_LARGE
    )


def test_compaction_event_carries_rust_fact_fields() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/facts.rs
    # Rust item: CodexCompactionEvent
    # Contract: compaction fact keeps Rust field names and enum-valued fields.
    event = CodexCompactionEvent(
        thread_id="thread-1",
        turn_id="turn-1",
        trigger=CompactionTrigger.AUTO,
        reason=CompactionReason.CONTEXT_LIMIT,
        implementation=CompactionImplementation.RESPONSES_COMPACT,
        phase=CompactionPhase.PRE_TURN,
        strategy=CompactionStrategy.PREFIX_COMPACTION,
        status=CompactionStatus.FAILED,
        error="too many tokens",
        active_context_tokens_before=120_000,
        active_context_tokens_after=60_000,
        started_at=10,
        completed_at=15,
        duration_ms=5,
    )

    payload = asdict(event)
    assert payload["thread_id"] == "thread-1"
    assert payload["phase"] == CompactionPhase.PRE_TURN
    assert payload["strategy"] == CompactionStrategy.PREFIX_COMPACTION
    assert payload["status"] == CompactionStatus.FAILED
    assert payload["active_context_tokens_before"] == 120_000
    assert payload["duration_ms"] == 5


def test_turn_resolved_config_fact_carries_rust_fact_fields() -> None:
    # Source: rust_source_contract
    # Rust crate: codex-analytics
    # Rust module: src/facts.rs
    # Rust item: TurnResolvedConfigFact
    # Contract: resolved-config fact exposes Rust field names used by reducer/event orchestration.
    fact = TurnResolvedConfigFact(
        turn_id="turn-1",
        thread_id="thread-1",
        num_input_images=2,
        submission_type=TurnSubmissionType.QUEUED,
        ephemeral=True,
        session_source="cli",
        model="gpt-5",
        model_provider="openai",
        permission_profile={"mode": "workspace-write"},
        permission_profile_cwd=Path("C:/repo"),
        reasoning_effort="high",
        reasoning_summary=None,
        service_tier="auto",
        approval_policy="on-request",
        approvals_reviewer="human",
        sandbox_network_access=False,
        collaboration_mode="default",
        personality=None,
        is_first_turn=True,
    )

    assert fact.turn_id == "turn-1"
    assert fact.submission_type == TurnSubmissionType.QUEUED
    assert fact.permission_profile_cwd == Path("C:/repo")
    assert fact.sandbox_network_access is False
    assert fact.is_first_turn is True
