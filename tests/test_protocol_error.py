import unittest
from datetime import datetime, timedelta, timezone

from pycodex.protocol import (
    AuthPlanType,
    CLOUDFLARE_BLOCKED_MESSAGE,
    CodexErr,
    CodexErrorInfo,
    ErrorEvent,
    EventMsg,
    ExecToolCallOutput,
    KnownPlan,
    NonSteerableTurnKind,
    RateLimitReachedType,
    RateLimitSnapshot,
    ResponseStreamFailed,
    SandboxDenied,
    SandboxTimeout,
    StreamOutput,
    UnexpectedResponseError,
    UsageLimitReachedError,
    format_retry_timestamp,
    get_error_message_ui,
    retry_now_override,
)


def rate_limit_snapshot(limit_name=None):
    return RateLimitSnapshot(limit_name=limit_name)


class ProtocolErrorTests(unittest.TestCase):
    def test_codex_error_info_round_trips_and_turn_status(self):
        error = CodexErrorInfo.from_mapping({"responseTooManyFailedAttempts": {"httpStatusCode": 429}})

        self.assertEqual(error, CodexErrorInfo.response_too_many_failed_attempts(429))
        self.assertEqual(error.to_mapping(), {"response_too_many_failed_attempts": {"http_status_code": 429}})
        self.assertTrue(ErrorEvent("boom", error).affects_turn_status())

        steer_error = CodexErrorInfo.active_turn_not_steerable(NonSteerableTurnKind.REVIEW)
        self.assertEqual(steer_error.to_mapping(), {"active_turn_not_steerable": {"turn_kind": "review"}})
        self.assertFalse(ErrorEvent("busy", steer_error).affects_turn_status())
        self.assertFalse(ErrorEvent("rollback", "threadRollbackFailed").affects_turn_status())

    def test_error_event_parses_codex_error_info_from_event_msg(self):
        event = EventMsg.from_mapping(
            {
                "type": "error",
                "message": "cannot steer review",
                "codex_error_info": {"active_turn_not_steerable": {"turn_kind": "compact"}},
            }
        )

        self.assertEqual(event.payload.codex_error_info, CodexErrorInfo.active_turn_not_steerable("compact"))
        self.assertFalse(event.payload.affects_turn_status())

    def test_usage_limit_reached_error_formats_plan_and_workspace_cases(self):
        err = UsageLimitReachedError(
            plan_type=AuthPlanType.known_plan(KnownPlan.PLUS),
            rate_limits=rate_limit_snapshot(),
        )

        self.assertEqual(
            str(err),
            "You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), "
            "visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again later.",
        )

        owner_credits = UsageLimitReachedError(
            plan_type=AuthPlanType.known_plan(KnownPlan.PLUS),
            rate_limits=rate_limit_snapshot(),
            rate_limit_reached_type=RateLimitReachedType.WORKSPACE_OWNER_CREDITS_DEPLETED,
        )
        self.assertEqual(str(owner_credits), "Your workspace is out of credits. Add credits to continue.")

        other_limit = UsageLimitReachedError(
            plan_type=AuthPlanType.known_plan(KnownPlan.PLUS),
            rate_limits=rate_limit_snapshot("codex_other"),
        )
        self.assertEqual(
            str(other_limit),
            "You've hit your usage limit for codex_other. Switch to another model now, or try again later.",
        )

        free = UsageLimitReachedError(
            plan_type=AuthPlanType.known_plan(KnownPlan.FREE),
            rate_limits=rate_limit_snapshot(),
        )
        self.assertEqual(
            str(free),
            "You've hit your usage limit. Upgrade to Plus to continue using Codex "
            "(https://chatgpt.com/explore/plus), or try again later.",
        )

        business = UsageLimitReachedError(
            plan_type=AuthPlanType.known_plan(KnownPlan.BUSINESS),
            rate_limits=rate_limit_snapshot(),
        )
        self.assertEqual(
            str(business),
            "You've hit your usage limit. To get more access now, send a request to your admin "
            "or try again later.",
        )

        enterprise = UsageLimitReachedError(
            plan_type=AuthPlanType.known_plan(KnownPlan.ENTERPRISE),
            rate_limits=rate_limit_snapshot(),
        )
        self.assertEqual(str(enterprise), "You've hit your usage limit. Try again later.")

        promo = UsageLimitReachedError(
            promo_message="To continue using Codex, start a free trial of <PLAN> today",
            rate_limits=rate_limit_snapshot(),
        )
        self.assertEqual(
            str(promo),
            "You've hit your usage limit. To continue using Codex, start a free trial of <PLAN> today,"
            " or try again later.",
        )

    def test_usage_limit_reached_formats_retry_timestamp(self):
        base = datetime(2024, 1, 1, 0, 0, tzinfo=timezone.utc)
        resets_at = base + timedelta(hours=1)

        with retry_now_override(base):
            expected_time = format_retry_timestamp(resets_at)
            err = UsageLimitReachedError(
                plan_type=AuthPlanType.known_plan(KnownPlan.TEAM),
                resets_at=resets_at,
                rate_limits=rate_limit_snapshot(),
            )
            self.assertEqual(
                str(err),
                "You've hit your usage limit. To get more access now, send a request to your admin "
                f"or try again at {expected_time}.",
            )

    def test_unexpected_status_prefers_json_message_and_cloudflare_copy(self):
        err = UnexpectedResponseError(
            status=401,
            body='{"error":{"message":"Workspace is not authorized in this region."},"status":401}',
            url="https://chatgpt.com/backend-api/codex/responses",
            request_id="req-123",
        )
        self.assertEqual(
            str(err),
            "unexpected status 401 Unauthorized: Workspace is not authorized in this region., "
            "url: https://chatgpt.com/backend-api/codex/responses, request id: req-123",
        )

        blocked = UnexpectedResponseError(
            status=403,
            body="<html><body>Cloudflare error: Sorry, you have been blocked</body></html>",
            url="http://example.com/blocked",
            cf_ray="ray-id",
        )
        self.assertEqual(
            str(blocked),
            f"{CLOUDFLARE_BLOCKED_MESSAGE} (status 403 Forbidden), "
            "url: http://example.com/blocked, cf-ray: ray-id",
        )

        lower_blocked = UnexpectedResponseError(
            status=403,
            body="<html><body>cloudflare error: blocked by policy</body></html>",
            request_id="req-lower",
        )
        self.assertEqual(
            str(lower_blocked),
            "unexpected status 403 Forbidden: "
            "<html><body>cloudflare error: blocked by policy</body></html>, request id: req-lower",
        )

        auth_details = UnexpectedResponseError(
            status=401,
            body="plain text error",
            url="https://chatgpt.com/backend-api/codex/models",
            cf_ray="cf-ray-auth-401-test",
            request_id="req-auth",
            identity_authorization_error="missing_authorization_header",
            identity_error_code="token_expired",
        )
        self.assertEqual(
            str(auth_details),
            "unexpected status 401 Unauthorized: plain text error, "
            "url: https://chatgpt.com/backend-api/codex/models, cf-ray: cf-ray-auth-401-test, "
            "request id: req-auth, auth error: missing_authorization_header, auth error code: token_expired",
        )

    def test_codex_error_maps_to_protocol_error_event(self):
        source = "HTTP status client error (429 Too Many Requests) for url (http://example.com/)"
        err = CodexErr.response_stream_failed(ResponseStreamFailed(source, request_id="req-123", status_code=429))

        event = err.to_error_event("prefix")

        self.assertEqual(
            event.message,
            "prefix: Error while reading the server response: "
            "HTTP status client error (429 Too Many Requests) for url (http://example.com/), request id: req-123",
        )
        self.assertEqual(event.codex_error_info, CodexErrorInfo.response_stream_connection_failed(429))
        self.assertTrue(CodexErr.simple("timeout").is_retryable())
        self.assertFalse(CodexErr.simple("server_overloaded").is_retryable())
        self.assertEqual(CodexErr.simple("server_overloaded").to_codex_protocol_error(), CodexErrorInfo.server_overloaded())

    def test_sandbox_error_ui_messages_match_upstream_cases(self):
        output = ExecToolCallOutput(aggregated_output=StreamOutput.new("aggregate detail"))
        self.assertEqual(get_error_message_ui(CodexErr.sandbox(SandboxDenied(output))), "aggregate detail")

        output = ExecToolCallOutput(
            exit_code=9,
            stdout=StreamOutput.new("stdout detail"),
            stderr=StreamOutput.new("stderr detail"),
        )
        self.assertEqual(get_error_message_ui(CodexErr.sandbox(SandboxDenied(output))), "stderr detail\nstdout detail")

        output = ExecToolCallOutput(
            exit_code=9,
            stdout=StreamOutput.new(" stdout detail\n"),
            stderr=StreamOutput.new(" stderr detail\n"),
        )
        self.assertEqual(get_error_message_ui(CodexErr.sandbox(SandboxDenied(output))), "stderr detail\nstdout detail")

        output = ExecToolCallOutput(exit_code=11, stdout=StreamOutput.new("stdout only"))
        self.assertEqual(get_error_message_ui(CodexErr.sandbox(SandboxDenied(output))), "stdout only")

        output = ExecToolCallOutput(exit_code=13)
        self.assertEqual(
            get_error_message_ui(CodexErr.sandbox(SandboxDenied(output))),
            "command failed inside sandbox with exit code 13",
        )

        output = ExecToolCallOutput(duration=timedelta(milliseconds=2500))
        self.assertEqual(
            get_error_message_ui(CodexErr.sandbox(SandboxTimeout(output))),
            "error: command timed out after 2500 ms",
        )


if __name__ == "__main__":
    unittest.main()
