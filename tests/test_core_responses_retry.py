import unittest
from datetime import timedelta

from pycodex.core.responses_retry import (
    ResponsesStreamRequest,
    RetryableResponseStreamAction,
    response_stream_retry_decision,
    retry_delay_for_error,
    retry_log_message,
)
from pycodex.protocol import CodexErr, UsageLimitReachedError


class ResponsesRetryTests(unittest.TestCase):
    def test_switches_to_fallback_transport_after_max_retries(self) -> None:
        """Rust source contract: fallback transport is tried before failing at max retries."""

        err = CodexErr.stream("websocket disconnected")

        decision = response_stream_retry_decision(
            retries=3,
            max_retries=3,
            err=err,
            request=ResponsesStreamRequest.SAMPLING,
            fallback_transport_available=True,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertIs(decision.action, RetryableResponseStreamAction.FALLBACK_TRANSPORT)
        self.assertEqual(decision.retries, 0)
        self.assertIn("Falling back from WebSockets to HTTPS transport.", decision.warning_message or "")
        self.assertIsNone(decision.error)

    def test_retries_before_max_retries(self) -> None:
        """Rust source contract: stream errors below max retries increment retry count and sleep."""

        decision = response_stream_retry_decision(
            retries=0,
            max_retries=3,
            err=CodexErr.stream("disconnect", timedelta(seconds=7)),
            request=ResponsesStreamRequest.SAMPLING,
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertIs(decision.action, RetryableResponseStreamAction.RETRY)
        self.assertEqual(decision.retries, 1)
        self.assertEqual(decision.delay, timedelta(seconds=7))
        self.assertFalse(decision.report_error)
        self.assertIsNone(decision.notify_message)

    def test_release_reports_second_websocket_retry(self) -> None:
        """Rust source contract: release builds hide only the first websocket retry notification."""

        decision = response_stream_retry_decision(
            retries=1,
            max_retries=3,
            err=CodexErr.stream("disconnect"),
            request=ResponsesStreamRequest.SAMPLING,
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertIs(decision.action, RetryableResponseStreamAction.RETRY)
        self.assertEqual(decision.retries, 2)
        self.assertTrue(decision.report_error)
        self.assertEqual(decision.notify_message, "Reconnecting... 2/3")

    def test_reports_first_retry_when_debug_or_not_websocket(self) -> None:
        """Rust source contract: debug builds and non-websocket transports report the first retry."""

        debug_decision = response_stream_retry_decision(
            retries=0,
            max_retries=3,
            err=CodexErr.stream("disconnect"),
            request=ResponsesStreamRequest.SAMPLING,
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=True,
        )
        https_decision = response_stream_retry_decision(
            retries=0,
            max_retries=3,
            err=CodexErr.stream("disconnect"),
            request=ResponsesStreamRequest.SAMPLING,
            fallback_transport_available=False,
            responses_websocket_enabled=False,
            debug_assertions=False,
        )

        self.assertTrue(debug_decision.report_error)
        self.assertEqual(debug_decision.notify_message, "Reconnecting... 1/3")
        self.assertTrue(https_decision.report_error)
        self.assertEqual(https_decision.notify_message, "Reconnecting... 1/3")

    def test_fails_after_max_retries_without_fallback(self) -> None:
        """Rust source contract: max retries without fallback returns the original stream error."""

        err = CodexErr.stream("disconnect")

        decision = response_stream_retry_decision(
            retries=3,
            max_retries=3,
            err=err,
            request=ResponsesStreamRequest.REMOTE_COMPACTION_V2,
            fallback_transport_available=False,
            responses_websocket_enabled=True,
            debug_assertions=False,
        )

        self.assertIs(decision.action, RetryableResponseStreamAction.FAIL)
        self.assertEqual(decision.retries, 3)
        self.assertIs(decision.error, err)

    def test_retry_delay_uses_stream_requested_delay_or_backoff(self) -> None:
        """Rust source contract: stream errors use requested delay when present, otherwise backoff."""

        self.assertEqual(
            retry_delay_for_error(CodexErr.stream("disconnect", 2.5), 1),
            timedelta(seconds=2.5),
        )
        delay = retry_delay_for_error(CodexErr.stream("disconnect"), 1)
        self.assertGreaterEqual(delay, timedelta(milliseconds=180))
        self.assertLessEqual(delay, timedelta(milliseconds=220))

    def test_retry_delay_uses_backoff_for_non_stream_errors(self) -> None:
        """Rust source contract: non-stream errors always use retry-count backoff."""

        delay = retry_delay_for_error(CodexErr.usage_limit_reached(UsageLimitReachedError()), 1)

        self.assertGreaterEqual(delay, timedelta(milliseconds=180))
        self.assertLessEqual(delay, timedelta(milliseconds=220))

    def test_retry_delay_rejects_bad_inputs(self) -> None:
        """Python parity guard: invalid retry delay inputs fail before caller side effects."""

        with self.assertRaisesRegex(TypeError, "err must be a CodexErr"):
            retry_delay_for_error(ValueError("x"), 1)  # type: ignore[arg-type]
        with self.assertRaisesRegex(ValueError, "positive"):
            retry_delay_for_error(CodexErr.stream("disconnect"), 0)
        with self.assertRaisesRegex(TypeError, "retry-after delay"):
            retry_delay_for_error(CodexErr.stream("disconnect", "later"), 1)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            retry_delay_for_error(CodexErr.stream("disconnect", -1), 1)

    def test_retry_log_messages_match_request_kind(self) -> None:
        """Rust source contract: retry log text changes by response stream request kind."""

        self.assertIn(
            "retrying sampling request",
            retry_log_message(
                ResponsesStreamRequest.SAMPLING,
                retries=1,
                max_retries=3,
                delay=timedelta(milliseconds=200),
                err=CodexErr.stream("disconnect"),
            ),
        )
        self.assertIn(
            "remote compaction v2 stream failed",
            retry_log_message(
                ResponsesStreamRequest.REMOTE_COMPACTION_V2,
                retries=1,
                max_retries=3,
                delay=timedelta(milliseconds=200),
                err=CodexErr.stream("disconnect"),
                turn_id="turn-1",
            ),
        )


if __name__ == "__main__":
    unittest.main()
