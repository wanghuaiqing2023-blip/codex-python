from __future__ import annotations

import unittest

from pycodex.analytics import (
    GuardianApprovalRequestSource,
    GuardianReviewDecision,
    GuardianReviewFailureReason,
    GuardianReviewSessionKind,
    GuardianReviewTerminalStatus,
)
from pycodex.core.guardian import (
    GuardianReviewAnalyticsResult,
    bool_tag,
    decision_tag,
    emit_guardian_review_metrics,
    failure_reason_tag,
    guardian_review_metric_tags,
    optional_bool_tag,
    reviewed_action_tag,
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


class Telemetry:
    def __init__(self) -> None:
        self.counters: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []
        self.durations: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []
        self.histograms: list[tuple[str, int, tuple[tuple[str, str], ...]]] = []

    def counter(self, metric: str, inc: int, tags: tuple[tuple[str, str], ...]) -> None:
        self.counters.append((metric, inc, tuple(tags)))

    def record_duration(self, metric: str, duration: int, tags: tuple[tuple[str, str], ...]) -> None:
        self.durations.append((metric, duration, tuple(tags)))

    def histogram(self, metric: str, value: int, tags: tuple[tuple[str, str], ...]) -> None:
        self.histograms.append((metric, value, tuple(tags)))


class GuardianMetricsTests(unittest.TestCase):
    def test_tag_helpers_match_rust_labels(self) -> None:
        self.assertEqual(decision_tag(GuardianReviewDecision.APPROVED), "approved")
        self.assertEqual(failure_reason_tag(GuardianReviewFailureReason.PARSE_ERROR), "parse_error")
        self.assertEqual(failure_reason_tag(None), "none")
        self.assertEqual(optional_bool_tag(True), "true")
        self.assertEqual(optional_bool_tag(False), "false")
        self.assertEqual(optional_bool_tag(None), "unknown")
        self.assertEqual(bool_tag(True), "true")
        self.assertEqual(reviewed_action_tag({"type": "network_access"}), "network_access")
        self.assertEqual(reviewed_action_tag({"action": "mcp_tool_call"}), "mcp_tool_call")

    def test_guardian_review_metric_tags_match_rust_order_and_sanitization(self) -> None:
        result = GuardianReviewAnalyticsResult(
            decision=GuardianReviewDecision.APPROVED,
            terminal_status=GuardianReviewTerminalStatus.APPROVED,
            failure_reason=None,
            guardian_session_kind=GuardianReviewSessionKind.TRUNK_REUSED,
            had_prior_review_context=True,
            reviewed_action_truncated=True,
            risk_level=GuardianRiskLevel.LOW,
            user_authorization=GuardianUserAuthorization.HIGH,
            outcome=GuardianAssessmentOutcome.ALLOW,
            guardian_model="gpt-5.4 guardian",
            guardian_reasoning_effort="low",
        )

        self.assertEqual(
            guardian_review_metric_tags(
                result,
                GuardianApprovalRequestSource.DELEGATED_SUBAGENT,
                {"type": "network_access"},
            ),
            (
                ("decision", "approved"),
                ("terminal_status", "approved"),
                ("failure_reason", "none"),
                ("approval_request_source", "delegated_subagent"),
                ("action", "network_access"),
                ("session_kind", "trunk_reused"),
                ("had_prior_review_context", "true"),
                ("reviewed_action_truncated", "true"),
                ("risk_level", "low"),
                ("user_authorization", "high"),
                ("outcome", "allow"),
                ("guardian_model", "gpt-5.4_guardian"),
                ("guardian_reasoning_effort", "low"),
            ),
        )

    def test_emit_guardian_review_metrics_records_count_duration_ttft_and_token_histograms(self) -> None:
        telemetry = Telemetry()
        result = GuardianReviewAnalyticsResult(
            decision="approved",
            terminal_status="approved",
            guardian_session_kind="trunk_reused",
            had_prior_review_context=True,
            reviewed_action_truncated=True,
            risk_level="low",
            user_authorization="high",
            outcome="allow",
            guardian_model="gpt-5.4 guardian",
            guardian_reasoning_effort="low",
            token_usage=TokenUsage(
                input_tokens=10,
                cached_input_tokens=4,
                output_tokens=3,
                reasoning_output_tokens=2,
                total_tokens=15,
            ),
            time_to_first_token_ms=123,
        )

        emit_guardian_review_metrics(
            telemetry,
            result,
            "delegated_subagent",
            {"type": "network_access"},
            456,
        )

        self.assertEqual(telemetry.counters[0][0], GUARDIAN_REVIEW_COUNT_METRIC)
        self.assertEqual(telemetry.counters[0][1], 1)
        self.assertEqual(
            telemetry.durations,
            [
                (GUARDIAN_REVIEW_DURATION_METRIC, 456, telemetry.counters[0][2]),
                (GUARDIAN_REVIEW_TTFT_DURATION_METRIC, 123, telemetry.counters[0][2]),
            ],
        )
        self.assertEqual(
            {dict(tags)["token_type"]: value for metric, value, tags in telemetry.histograms if metric == GUARDIAN_REVIEW_TOKEN_USAGE_METRIC},
            {
                "total": 15,
                "input": 10,
                "cached_input": 4,
                "non_cached_input": 6,
                "output": 3,
                "reasoning_output": 2,
            },
        )

    def test_invalid_shapes_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            reviewed_action_tag({"type": "bad"})
        with self.assertRaises(TypeError):
            bool_tag(1)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            emit_guardian_review_metrics(
                Telemetry(),
                GuardianReviewAnalyticsResult(decision="approved", terminal_status="approved"),
                "main_turn",
                {"type": "shell"},
                -1,
            )


if __name__ == "__main__":
    unittest.main()
