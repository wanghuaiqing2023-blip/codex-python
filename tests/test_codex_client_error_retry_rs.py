"""Rust-derived tests for ``codex-client/src/error.rs`` and ``src/retry.rs``.

Rust crate: ``codex-client``
Rust modules:
- ``src/error.rs``
- ``src/retry.rs``

Behavior contract:
- mirror public error variant display strings;
- retry only selected HTTP/transport errors before ``max_attempts``;
- compute exponential backoff with 0.9..1.1 jitter;
- call ``make_req`` per attempt and stop on success or non-retryable errors.
"""

from __future__ import annotations

import unittest

from pycodex.codex_client import RetryOn
from pycodex.codex_client import RetryPolicy
from pycodex.codex_client import StreamError
from pycodex.codex_client import TransportError
from pycodex.codex_client import backoff
from pycodex.codex_client import run_with_retry


class CodexClientErrorRetryRsTests(unittest.TestCase):
    def test_transport_and_stream_error_display_matches_rust_variants(self) -> None:
        self.assertEqual(str(TransportError.http(429, body="slow down")), "http 429: 'slow down'")
        self.assertEqual(str(TransportError.http(500)), "http 500: None")
        self.assertEqual(str(TransportError.retry_limit()), "retry limit reached")
        self.assertEqual(str(TransportError.timeout()), "timeout")
        self.assertEqual(str(TransportError.network("dns")), "network error: dns")
        self.assertEqual(str(TransportError.build("bad header")), "request build error: bad header")
        self.assertEqual(str(StreamError.stream("closed")), "stream failed: closed")
        self.assertEqual(str(StreamError.timeout()), "timeout")

    def test_retry_on_matches_http_and_transport_branches(self) -> None:
        policy = RetryOn(retry_429=True, retry_5xx=True, retry_transport=True)

        self.assertTrue(policy.should_retry(TransportError.http(429), 0, 1))
        self.assertTrue(policy.should_retry(TransportError.http(500), 0, 1))
        self.assertTrue(policy.should_retry(TransportError.http(599), 0, 1))
        self.assertTrue(policy.should_retry(TransportError.timeout(), 0, 1))
        self.assertTrue(policy.should_retry(TransportError.network("reset"), 0, 1))

        self.assertFalse(policy.should_retry(TransportError.http(400), 0, 1))
        self.assertFalse(policy.should_retry(TransportError.http(503), 1, 1))
        self.assertFalse(policy.should_retry(TransportError.build("bad"), 0, 1))
        self.assertFalse(RetryOn(False, False, False).should_retry(TransportError.http(429), 0, 1))

    def test_backoff_uses_rust_attempt_zero_and_jittered_exponential_shape(self) -> None:
        self.assertEqual(backoff(0.25, 0, random_range=lambda _a, _b: 1.0), 0.25)
        self.assertEqual(backoff(0.25, 1, random_range=lambda _a, _b: 1.0), 0.25)
        self.assertEqual(backoff(0.25, 2, random_range=lambda _a, _b: 1.0), 0.50)
        self.assertEqual(backoff(0.25, 3, random_range=lambda _a, _b: 0.9), 0.90)
        self.assertEqual(backoff(0.25, 3, random_range=lambda _a, _b: 1.1), 1.10)

    def test_run_with_retry_rebuilds_request_per_attempt_until_success(self) -> None:
        made: list[str] = []
        attempts: list[int] = []
        sleeps: list[float] = []

        def make_req() -> str:
            req = f"req-{len(made)}"
            made.append(req)
            return req

        def op(req: str, attempt: int) -> str:
            attempts.append(attempt)
            if attempt < 2:
                raise TransportError.network(req)
            return req

        result = run_with_retry(
            RetryPolicy(3, 0.001, RetryOn(False, False, True)),
            make_req,
            op,
            sleep=sleeps.append,
        )

        self.assertEqual(result, "req-2")
        self.assertEqual(made, ["req-0", "req-1", "req-2"])
        self.assertEqual(attempts, [0, 1, 2])
        self.assertEqual(len(sleeps), 2)

    def test_run_with_retry_returns_non_retryable_error_without_sleep(self) -> None:
        sleeps: list[float] = []

        with self.assertRaisesRegex(TransportError, "request build error: bad"):
            run_with_retry(
                RetryPolicy(3, 0.001, RetryOn(True, True, True)),
                lambda: object(),
                lambda _req, _attempt: (_ for _ in ()).throw(TransportError.build("bad")),
                sleep=sleeps.append,
            )

        self.assertEqual(sleeps, [])

    def test_run_with_retry_stops_at_max_attempts_boundary(self) -> None:
        attempts: list[int] = []

        with self.assertRaisesRegex(TransportError, "network error: reset"):
            run_with_retry(
                RetryPolicy(1, 0.001, RetryOn(False, False, True)),
                lambda: object(),
                lambda _req, attempt: (
                    attempts.append(attempt),
                    (_ for _ in ()).throw(TransportError.network("reset")),
                )[1],
                sleep=lambda _delay: None,
            )

        self.assertEqual(attempts, [0, 1])


if __name__ == "__main__":
    unittest.main()
