"""Guardian review helpers ported from ``codex-core::guardian``."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .approval_request import (
    FormattedGuardianAction,
    GuardianApprovalRequest,
    GuardianMcpAnnotations,
    GuardianNetworkAccessTrigger,
    format_guardian_action_pretty,
    guardian_approval_request_to_json,
    guardian_assessment_action,
    guardian_request_target_item_id,
    guardian_request_turn_id,
    guardian_reviewed_action,
)
from .review import (
    DEFAULT_GUARDIAN_REJECTION_RATIONALE,
    GUARDIAN_REVIEWER_NAME,
    GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT,
    GUARDIAN_REJECTION_INSTRUCTIONS,
    GUARDIAN_TIMEOUT_INSTRUCTIONS,
    GuardianApplyPatchApprovalRequest,
    GuardianRejection,
    GuardianShellApprovalRequest,
    SANDBOX_PERMISSIONS_USE_DEFAULT,
    SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS,
    apply_patch_files_for_guardian,
    format_apply_patch_changes_for_guardian,
    guardian_rejection_message,
    guardian_rejection_message_for_rejection,
    guardian_risk_level_str,
    guardian_timeout_message,
    is_guardian_reviewer_source,
    routes_approval_to_guardian,
)
from .metrics import (
    GuardianReviewAnalyticsResult,
    approval_request_source_tag,
    bool_tag,
    decision_tag,
    emit_guardian_review_metrics,
    emit_guardian_token_usage_histograms,
    failure_reason_tag,
    guardian_review_metric_tags,
    optional_bool_tag,
    outcome_tag,
    reviewed_action_tag,
    risk_level_tag,
    session_kind_tag,
    terminal_status_tag,
    user_authorization_tag,
)
from .prompt import (
    GuardianAssessment,
    GuardianPromptItems,
    GuardianPromptMode,
    GuardianTranscriptCursor,
    GuardianTranscriptEntry,
    GuardianTranscriptEntryKind,
    build_guardian_prompt_items,
    collect_guardian_transcript_entries,
    guardian_output_contract_prompt,
    guardian_output_schema,
    guardian_policy_prompt,
    guardian_policy_prompt_with_config,
    guardian_truncate_text,
    parse_guardian_assessment,
    render_guardian_transcript_entries,
    render_guardian_transcript_entries_with_offset,
    split_guardian_truncation_bounds,
)

GUARDIAN_REVIEW_TIMEOUT_SECONDS = 90
MAX_CONSECUTIVE_GUARDIAN_DENIALS_PER_TURN = 3
MAX_RECENT_AUTO_REVIEW_DENIALS_PER_TURN = 10
AUTO_REVIEW_DENIAL_WINDOW_SIZE = 50
AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX = (
    "The user has manually approved a specific action that was previously `Rejected`."
)
GUARDIAN_MAX_MESSAGE_TRANSCRIPT_TOKENS = 10_000
GUARDIAN_MAX_TOOL_TRANSCRIPT_TOKENS = 10_000
GUARDIAN_MAX_MESSAGE_ENTRY_TOKENS = 2_000
GUARDIAN_MAX_TOOL_ENTRY_TOKENS = 1_000
GUARDIAN_MAX_ACTION_STRING_TOKENS = 16_000
GUARDIAN_RECENT_ENTRY_LIMIT = 40
GUARDIAN_TRUNCATION_TAG = "truncated"


@dataclass(frozen=True)
class GuardianRejectionCircuitBreakerAction:
    type: str
    consecutive_denials: int | None = None
    recent_denials: int | None = None

    @classmethod
    def continue_(cls) -> "GuardianRejectionCircuitBreakerAction":
        return cls("continue")

    @classmethod
    def interrupt_turn(
        cls,
        *,
        consecutive_denials: int,
        recent_denials: int,
    ) -> "GuardianRejectionCircuitBreakerAction":
        if isinstance(consecutive_denials, bool) or not isinstance(consecutive_denials, int):
            raise TypeError("consecutive_denials must be an integer")
        if isinstance(recent_denials, bool) or not isinstance(recent_denials, int):
            raise TypeError("recent_denials must be an integer")
        return cls(
            "interrupt_turn",
            consecutive_denials=consecutive_denials,
            recent_denials=recent_denials,
        )

    def __post_init__(self) -> None:
        if self.type not in {"continue", "interrupt_turn"}:
            raise ValueError("unknown guardian circuit breaker action type")
        if self.type == "continue":
            if self.consecutive_denials is not None or self.recent_denials is not None:
                raise ValueError("continue action cannot include denial counts")
        else:
            if self.consecutive_denials is None or self.recent_denials is None:
                raise ValueError("interrupt_turn action requires denial counts")


@dataclass
class _GuardianRejectionCircuitBreakerTurn:
    consecutive_denials: int = 0
    recent_denials: deque[bool] = field(default_factory=deque)
    interrupt_triggered: bool = False


@dataclass
class GuardianRejectionCircuitBreaker:
    turns: dict[str, _GuardianRejectionCircuitBreakerTurn] = field(default_factory=dict)

    def clear_turn(self, turn_id: str) -> None:
        if not isinstance(turn_id, str):
            raise TypeError("turn_id must be a string")
        self.turns.pop(turn_id, None)

    def record_denial(self, turn_id: str) -> GuardianRejectionCircuitBreakerAction:
        if not isinstance(turn_id, str):
            raise TypeError("turn_id must be a string")
        turn = self.turns.setdefault(turn_id, _GuardianRejectionCircuitBreakerTurn())
        turn.consecutive_denials += 1
        self._record_recent_review(turn, denied=True)
        recent_denials = sum(1 for denied in turn.recent_denials if denied)
        if not turn.interrupt_triggered and (
            turn.consecutive_denials >= MAX_CONSECUTIVE_GUARDIAN_DENIALS_PER_TURN
            or recent_denials >= MAX_RECENT_AUTO_REVIEW_DENIALS_PER_TURN
        ):
            turn.interrupt_triggered = True
            return GuardianRejectionCircuitBreakerAction.interrupt_turn(
                consecutive_denials=turn.consecutive_denials,
                recent_denials=recent_denials,
            )
        return GuardianRejectionCircuitBreakerAction.continue_()

    def record_non_denial(self, turn_id: str) -> None:
        if not isinstance(turn_id, str):
            raise TypeError("turn_id must be a string")
        turn = self.turns.setdefault(turn_id, _GuardianRejectionCircuitBreakerTurn())
        turn.consecutive_denials = 0
        self._record_recent_review(turn, denied=False)

    @staticmethod
    def _record_recent_review(turn: _GuardianRejectionCircuitBreakerTurn, *, denied: bool) -> None:
        turn.recent_denials.append(bool(denied))
        if len(turn.recent_denials) > AUTO_REVIEW_DENIAL_WINDOW_SIZE:
            turn.recent_denials.popleft()

__all__ = [
    "AUTO_REVIEW_DENIAL_WINDOW_SIZE",
    "AUTO_REVIEW_DENIED_ACTION_APPROVAL_DEVELOPER_PREFIX",
    "DEFAULT_GUARDIAN_REJECTION_RATIONALE",
    "GUARDIAN_REVIEWER_NAME",
    "GUARDIAN_APPROVAL_REQUEST_SOURCE_DELEGATED_SUBAGENT",
    "GUARDIAN_REJECTION_INSTRUCTIONS",
    "GUARDIAN_TIMEOUT_INSTRUCTIONS",
    "GUARDIAN_MAX_ACTION_STRING_TOKENS",
    "GUARDIAN_MAX_MESSAGE_ENTRY_TOKENS",
    "GUARDIAN_MAX_MESSAGE_TRANSCRIPT_TOKENS",
    "GUARDIAN_MAX_TOOL_ENTRY_TOKENS",
    "GUARDIAN_MAX_TOOL_TRANSCRIPT_TOKENS",
    "GUARDIAN_RECENT_ENTRY_LIMIT",
    "GUARDIAN_REVIEW_TIMEOUT_SECONDS",
    "GUARDIAN_TRUNCATION_TAG",
    "FormattedGuardianAction",
    "GuardianApprovalRequest",
    "GuardianAssessment",
    "GuardianMcpAnnotations",
    "GuardianNetworkAccessTrigger",
    "GuardianPromptItems",
    "GuardianPromptMode",
    "GuardianApplyPatchApprovalRequest",
    "GuardianRejection",
    "GuardianRejectionCircuitBreaker",
    "GuardianRejectionCircuitBreakerAction",
    "GuardianReviewAnalyticsResult",
    "GuardianShellApprovalRequest",
    "GuardianTranscriptCursor",
    "GuardianTranscriptEntry",
    "GuardianTranscriptEntryKind",
    "MAX_CONSECUTIVE_GUARDIAN_DENIALS_PER_TURN",
    "MAX_RECENT_AUTO_REVIEW_DENIALS_PER_TURN",
    "SANDBOX_PERMISSIONS_USE_DEFAULT",
    "SANDBOX_PERMISSIONS_WITH_ADDITIONAL_PERMISSIONS",
    "apply_patch_files_for_guardian",
    "format_apply_patch_changes_for_guardian",
    "format_guardian_action_pretty",
    "guardian_output_contract_prompt",
    "guardian_output_schema",
    "guardian_policy_prompt",
    "guardian_policy_prompt_with_config",
    "guardian_approval_request_to_json",
    "guardian_assessment_action",
    "guardian_rejection_message",
    "guardian_rejection_message_for_rejection",
    "guardian_review_metric_tags",
    "guardian_request_target_item_id",
    "guardian_request_turn_id",
    "guardian_reviewed_action",
    "guardian_risk_level_str",
    "guardian_timeout_message",
    "guardian_truncate_text",
    "is_guardian_reviewer_source",
    "parse_guardian_assessment",
    "routes_approval_to_guardian",
    "approval_request_source_tag",
    "bool_tag",
    "build_guardian_prompt_items",
    "collect_guardian_transcript_entries",
    "decision_tag",
    "emit_guardian_review_metrics",
    "emit_guardian_token_usage_histograms",
    "failure_reason_tag",
    "optional_bool_tag",
    "outcome_tag",
    "reviewed_action_tag",
    "risk_level_tag",
    "render_guardian_transcript_entries",
    "render_guardian_transcript_entries_with_offset",
    "session_kind_tag",
    "split_guardian_truncation_bounds",
    "terminal_status_tag",
    "user_authorization_tag",
]
