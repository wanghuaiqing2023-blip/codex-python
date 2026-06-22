"""Rust-derived tests for ``codex-api/src/error.rs``."""

from __future__ import annotations

import unittest

from pycodex.codex_api import ApiError
from pycodex.codex_client import TransportError


class _RateLimitErrorLike:
    def __str__(self) -> str:
        return "slow down"


class CodexApiErrorRsTests(unittest.TestCase):
    def test_api_error_display_matches_rust_variants(self) -> None:
        # Rust crate/module: codex-api/src/error.rs
        # Contract: thiserror display strings for every ApiError variant.
        cases = [
            (ApiError.api(400, "bad request"), "api error 400 Bad Request: bad request"),
            (ApiError.stream("closed"), "stream error: closed"),
            (ApiError.context_window_exceeded(), "context window exceeded"),
            (ApiError.quota_exceeded(), "quota exceeded"),
            (ApiError.usage_not_included(), "usage not included"),
            (ApiError.retryable("try again", delay=1.5), "retryable error: try again"),
            (ApiError.rate_limit("limited"), "rate limit: limited"),
            (ApiError.invalid_request("missing model"), "invalid request: missing model"),
            (ApiError.cyber_policy("blocked"), "cyber policy: blocked"),
            (ApiError.server_overloaded(), "server overloaded"),
        ]

        for error, expected in cases:
            with self.subTest(error=error.kind):
                self.assertEqual(str(error), expected)

    def test_transport_error_is_transparent(self) -> None:
        # Rust crate/module: codex-api/src/error.rs
        # Contract: ApiError::Transport is transparent over TransportError.
        cases = [
            (TransportError.network("dns"), "network error: dns"),
            (TransportError.build("bad header"), "request build error: bad header"),
        ]

        for transport, expected in cases:
            with self.subTest(kind=transport.kind):
                self.assertEqual(str(ApiError.transport_error(transport)), expected)

    def test_retryable_retains_delay_without_displaying_it(self) -> None:
        # Rust crate/module: codex-api/src/error.rs
        # Contract: ApiError::Retryable stores an optional Duration delay while
        # thiserror Display formats only the message.
        error = ApiError.retryable("try again", delay=2.25)

        self.assertEqual(error.delay, 2.25)
        self.assertEqual(str(error), "retryable error: try again")

    def test_rate_limit_error_conversion_preserves_display_text(self) -> None:
        # Rust crate/module: codex-api/src/error.rs
        # Contract: From<RateLimitError> for ApiError stores err.to_string()
        # in the RateLimit variant.
        error = ApiError.from_rate_limit_error(_RateLimitErrorLike())

        self.assertEqual(error.kind, "rate_limit")
        self.assertEqual(str(error), "rate limit: slow down")

    def test_api_status_accepts_preformatted_status_string(self) -> None:
        # Rust crate/module: codex-api/src/error.rs
        # Contract: ApiError::Api displays the StatusCode text verbatim. Python
        # accepts preformatted status strings for statuses not modeled by
        # HTTPStatus.
        self.assertEqual(
            str(ApiError.api("599 Network Connect Timeout", "upstream")),
            "api error 599 Network Connect Timeout: upstream",
        )


if __name__ == "__main__":
    unittest.main()
