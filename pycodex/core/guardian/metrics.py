"""Guardian review metric helpers ported from ``codex-core::guardian::metrics``."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from typing import Any

from pycodex.analytics import (
    GuardianApprovalRequestSource,
    GuardianReviewDecision,
    GuardianReviewFailureReason,
    GuardianReviewSessionKind,
    GuardianReviewTerminalStatus,
)
from pycodex.otel import (
    GUARDIAN_REVIEW_COUNT_METRIC,
    GUARDIAN_REVIEW_DURATION_METRIC,
    GUARDIAN_REVIEW_TOKEN_USAGE_METRIC,
    GUARDIAN_REVIEW_TTFT_DURATION_METRIC,
)
from pycodex.protocol import (
    GuardianAssessmentOutcome,
    GuardianRiskLevel,
    GuardianUserAuthorization,
    TokenUsage,
)
from pycodex.utils.string import sanitize_metric_tag_value

JsonValue = Any


@dataclass(frozen=True)
class GuardianReviewAnalyticsResult:
    decision: GuardianReviewDecision
    terminal_status: GuardianReviewTerminalStatus
    failure_reason: GuardianReviewFailureReason | None = None
    guardian_session_kind: GuardianReviewSessionKind | None = None
    had_prior_review_context: bool | None = None
    reviewed_action_truncated: bool = False
    risk_level: GuardianRiskLevel | None = None
    user_authorization: GuardianUserAuthorization | None = None
    outcome: GuardianAssessmentOutcome | None = None
    guardian_model: str | None = None
    guardian_reasoning_effort: str | None = None
    token_usage: TokenUsage | None = None
    time_to_first_token_ms: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision", _coerce_enum(self.decision, GuardianReviewDecision, "decision"))
        object.__setattr__(
            self,
            "terminal_status",
            _coerce_enum(self.terminal_status, GuardianReviewTerminalStatus, "terminal_status"),
        )
        if self.failure_reason is not None:
            object.__setattr__(
                self,
                "failure_reason",
                _coerce_enum(self.failure_reason, GuardianReviewFailureReason, "failure_reason"),
            )
        if self.guardian_session_kind is not None:
            object.__setattr__(
                self,
                "guardian_session_kind",
                _coerce_enum(self.guardian_session_kind, GuardianReviewSessionKind, "guardian_session_kind"),
            )
        if self.had_prior_review_context is not None and not isinstance(self.had_prior_review_context, bool):
            raise TypeError("had_prior_review_context must be a bool or None")
        if not isinstance(self.reviewed_action_truncated, bool):
            raise TypeError("reviewed_action_truncated must be a bool")
        if self.risk_level is not None:
            object.__setattr__(self, "risk_level", _coerce_enum(self.risk_level, GuardianRiskLevel, "risk_level"))
        if self.user_authorization is not None:
            object.__setattr__(
                self,
                "user_authorization",
                _coerce_enum(self.user_authorization, GuardianUserAuthorization, "user_authorization"),
            )
        if self.outcome is not None:
            object.__setattr__(self, "outcome", _coerce_enum(self.outcome, GuardianAssessmentOutcome, "outcome"))
        if self.guardian_model is not None and not isinstance(self.guardian_model, str):
            raise TypeError("guardian_model must be a string or None")
        if self.guardian_reasoning_effort is not None and not isinstance(self.guardian_reasoning_effort, str):
            raise TypeError("guardian_reasoning_effort must be a string or None")
        if self.token_usage is not None and not isinstance(self.token_usage, TokenUsage):
            object.__setattr__(self, "token_usage", TokenUsage.from_mapping(self.token_usage))
        if self.time_to_first_token_ms is not None:
            object.__setattr__(self, "time_to_first_token_ms", _nonnegative_int(self.time_to_first_token_ms, "time_to_first_token_ms"))

    @classmethod
    def from_mapping(cls, value: Mapping[str, JsonValue]) -> "GuardianReviewAnalyticsResult":
        return cls(
            decision=value["decision"],
            terminal_status=value["terminal_status"],
            failure_reason=value.get("failure_reason"),
            guardian_session_kind=value.get("guardian_session_kind"),
            had_prior_review_context=value.get("had_prior_review_context"),
            reviewed_action_truncated=bool(value.get("reviewed_action_truncated", False)),
            risk_level=value.get("risk_level"),
            user_authorization=value.get("user_authorization"),
            outcome=value.get("outcome"),
            guardian_model=value.get("guardian_model"),
            guardian_reasoning_effort=value.get("guardian_reasoning_effort"),
            token_usage=value.get("token_usage"),
            time_to_first_token_ms=value.get("time_to_first_token_ms"),
        )


def emit_guardian_review_metrics(
    session_telemetry: Any,
    result: GuardianReviewAnalyticsResult | Mapping[str, JsonValue],
    approval_request_source: GuardianApprovalRequestSource | str,
    reviewed_action: Mapping[str, JsonValue] | object,
    completion_latency_ms: int,
) -> None:
    result = _coerce_result(result)
    source = _coerce_enum(approval_request_source, GuardianApprovalRequestSource, "approval_request_source")
    completion_latency_ms = _nonnegative_int(completion_latency_ms, "completion_latency_ms")
    tags = guardian_review_metric_tags(result, source, reviewed_action)
    tag_refs = tuple(tags)

    session_telemetry.counter(GUARDIAN_REVIEW_COUNT_METRIC, 1, tag_refs)
    session_telemetry.record_duration(GUARDIAN_REVIEW_DURATION_METRIC, completion_latency_ms, tag_refs)

    if result.time_to_first_token_ms is not None:
        session_telemetry.record_duration(
            GUARDIAN_REVIEW_TTFT_DURATION_METRIC,
            result.time_to_first_token_ms,
            tag_refs,
        )

    if result.token_usage is not None:
        emit_guardian_token_usage_histograms(session_telemetry, result.token_usage, tag_refs)


def emit_guardian_token_usage_histograms(
    session_telemetry: Any,
    token_usage: TokenUsage,
    base_tags: Sequence[tuple[str, str]],
) -> None:
    if not isinstance(token_usage, TokenUsage):
        token_usage = TokenUsage.from_mapping(token_usage)
    for token_type, value in (
        ("total", max(token_usage.total_tokens, 0)),
        ("input", max(token_usage.input_tokens, 0)),
        ("cached_input", token_usage.cached_input()),
        ("non_cached_input", token_usage.non_cached_input()),
        ("output", max(token_usage.output_tokens, 0)),
        ("reasoning_output", max(token_usage.reasoning_output_tokens, 0)),
    ):
        session_telemetry.histogram(
            GUARDIAN_REVIEW_TOKEN_USAGE_METRIC,
            value,
            tuple(base_tags) + (("token_type", token_type),),
        )


def guardian_review_metric_tags(
    result: GuardianReviewAnalyticsResult | Mapping[str, JsonValue],
    approval_request_source: GuardianApprovalRequestSource | str,
    reviewed_action: Mapping[str, JsonValue] | object,
) -> tuple[tuple[str, str], ...]:
    result = _coerce_result(result)
    source = _coerce_enum(approval_request_source, GuardianApprovalRequestSource, "approval_request_source")
    return (
        ("decision", decision_tag(result.decision)),
        ("terminal_status", terminal_status_tag(result.terminal_status)),
        ("failure_reason", failure_reason_tag(result.failure_reason)),
        ("approval_request_source", approval_request_source_tag(source)),
        ("action", reviewed_action_tag(reviewed_action)),
        ("session_kind", session_kind_tag(result.guardian_session_kind)),
        ("had_prior_review_context", optional_bool_tag(result.had_prior_review_context)),
        ("reviewed_action_truncated", bool_tag(result.reviewed_action_truncated)),
        ("risk_level", risk_level_tag(result.risk_level)),
        ("user_authorization", user_authorization_tag(result.user_authorization)),
        ("outcome", outcome_tag(result.outcome)),
        ("guardian_model", sanitize_metric_tag_value(result.guardian_model) if result.guardian_model is not None else "none"),
        (
            "guardian_reasoning_effort",
            sanitize_metric_tag_value(result.guardian_reasoning_effort)
            if result.guardian_reasoning_effort is not None
            else "none",
        ),
    )


def decision_tag(decision: GuardianReviewDecision | str) -> str:
    return _coerce_enum(decision, GuardianReviewDecision, "decision").value


def terminal_status_tag(status: GuardianReviewTerminalStatus | str) -> str:
    return _coerce_enum(status, GuardianReviewTerminalStatus, "terminal_status").value


def failure_reason_tag(reason: GuardianReviewFailureReason | str | None) -> str:
    return "none" if reason is None else _coerce_enum(reason, GuardianReviewFailureReason, "failure_reason").value


def approval_request_source_tag(source: GuardianApprovalRequestSource | str) -> str:
    return _coerce_enum(source, GuardianApprovalRequestSource, "approval_request_source").value


def reviewed_action_tag(action: Mapping[str, JsonValue] | object) -> str:
    action_type = _action_type(action)
    if action_type == "shell":
        return "shell"
    if action_type == "unified_exec":
        return "unified_exec"
    if action_type == "execve":
        return "execve"
    if action_type == "apply_patch":
        return "apply_patch"
    if action_type == "network_access":
        return "network_access"
    if action_type == "mcp_tool_call":
        return "mcp_tool_call"
    if action_type == "request_permissions":
        return "request_permissions"
    raise ValueError(f"unsupported guardian reviewed action: {action_type}")


def session_kind_tag(kind: GuardianReviewSessionKind | str | None) -> str:
    return "none" if kind is None else _coerce_enum(kind, GuardianReviewSessionKind, "guardian_session_kind").value


def optional_bool_tag(value: bool | None) -> str:
    if value is True:
        return "true"
    if value is False:
        return "false"
    return "unknown"


def bool_tag(value: bool) -> str:
    if not isinstance(value, bool):
        raise TypeError("value must be a bool")
    return "true" if value else "false"


def risk_level_tag(risk_level: GuardianRiskLevel | str | None) -> str:
    return "none" if risk_level is None else _coerce_enum(risk_level, GuardianRiskLevel, "risk_level").value


def user_authorization_tag(user_authorization: GuardianUserAuthorization | str | None) -> str:
    return "none" if user_authorization is None else _coerce_enum(user_authorization, GuardianUserAuthorization, "user_authorization").value


def outcome_tag(outcome: GuardianAssessmentOutcome | str | None) -> str:
    return "none" if outcome is None else _coerce_enum(outcome, GuardianAssessmentOutcome, "outcome").value


def _coerce_result(value: GuardianReviewAnalyticsResult | Mapping[str, JsonValue]) -> GuardianReviewAnalyticsResult:
    if isinstance(value, GuardianReviewAnalyticsResult):
        return value
    if isinstance(value, Mapping):
        return GuardianReviewAnalyticsResult.from_mapping(value)
    raise TypeError("result must be a GuardianReviewAnalyticsResult or mapping")


def _coerce_enum(value: Any, enum_type: type[Enum], label: str) -> Any:
    if isinstance(value, enum_type):
        return value
    if isinstance(value, str):
        return enum_type(value)
    raise TypeError(f"{label} must be a {enum_type.__name__} or string")


def _action_type(action: Mapping[str, JsonValue] | object) -> str:
    if isinstance(action, Mapping):
        value = action.get("type") or action.get("action")
    else:
        value = getattr(action, "type", None) or getattr(action, "action", None)
    if isinstance(value, Enum):
        value = value.value
    if not isinstance(value, str):
        raise TypeError("reviewed_action must expose a string type/action")
    return value


def _nonnegative_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{label} must be an integer")
    if value < 0:
        raise ValueError(f"{label} must be non-negative")
    return value


__all__ = [
    "GuardianReviewAnalyticsResult",
    "approval_request_source_tag",
    "bool_tag",
    "decision_tag",
    "emit_guardian_review_metrics",
    "emit_guardian_token_usage_histograms",
    "failure_reason_tag",
    "guardian_review_metric_tags",
    "optional_bool_tag",
    "outcome_tag",
    "reviewed_action_tag",
    "risk_level_tag",
    "session_kind_tag",
    "terminal_status_tag",
    "user_authorization_tag",
]
