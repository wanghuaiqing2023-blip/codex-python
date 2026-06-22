"""Rust-derived tests for ``codex-api/src/telemetry.rs``."""

from __future__ import annotations

import asyncio
import unittest
from dataclasses import dataclass

from pycodex.codex_api import SseTelemetry
from pycodex.codex_api import WebsocketTelemetry
from pycodex.codex_api import http_status
from pycodex.codex_api import response_status
from pycodex.codex_api import run_with_request_telemetry
from pycodex.codex_client import Request
from pycodex.codex_client import RetryOn
from pycodex.codex_client import RetryPolicy
from pycodex.codex_client import TransportError


@dataclass(frozen=True)
class _Response:
    status: int


class _Telemetry:
    def __init__(self) -> None:
        self.events: list[tuple[int, int | None, TransportError | None, float]] = []

    def on_request(
        self,
        attempt: int,
        status: int | None,
        error: TransportError | None,
        duration: float,
    ) -> None:
        self.events.append((attempt, status, error, duration))


class _SseRecorder:
    def on_sse_poll(self, result: object, duration: float) -> None:
        pass


class _WsRecorder:
    def on_ws_request(self, duration: float, error: BaseException | None, connection_reused: bool) -> None:
        pass

    def on_ws_event(self, result: object, duration: float) -> None:
        pass


class CodexApiTelemetryRsTests(unittest.TestCase):
    def test_public_telemetry_protocols_are_structural(self) -> None:
        # Rust crate/module: codex-api/src/telemetry.rs
        # Contract: SseTelemetry and WebsocketTelemetry are public traits with
        # method-only structural requirements.
        self.assertIsInstance(_SseRecorder(), SseTelemetry)
        self.assertIsInstance(_WsRecorder(), WebsocketTelemetry)

    def test_status_helpers_match_rust_with_status_and_http_status(self) -> None:
        # Rust crate/module: codex-api/src/telemetry.rs
        # Contract: WithStatus extracts response status, and http_status only
        # returns a status for TransportError::Http.
        self.assertEqual(response_status(_Response(201)), 201)
        self.assertEqual(http_status(TransportError.http(429)), 429)
        self.assertIsNone(http_status(TransportError.timeout()))

    def test_run_with_request_telemetry_records_success_attempt(self) -> None:
        # Rust crate/module: codex-api/src/telemetry.rs
        # Contract: successful unary/streaming calls record attempt, response
        # status, no error, and elapsed duration after send returns.
        telemetry = _Telemetry()
        clock_values = iter([10.0, 10.25])

        async def send(_request: Request) -> _Response:
            return _Response(204)

        result = asyncio.run(
            run_with_request_telemetry(
                _policy(max_attempts=0),
                telemetry,
                lambda: Request("GET", "https://example.test"),
                send,
                clock=lambda: next(clock_values),
            )
        )

        self.assertEqual(result.status, 204)
        self.assertEqual(telemetry.events, [(0, 204, None, 0.25)])

    def test_run_with_request_telemetry_records_http_error_and_retries(self) -> None:
        # Rust crate/module: codex-api/src/telemetry.rs
        # Contract: HTTP TransportError attempts record their status and error
        # before retry policy decides whether to retry.
        telemetry = _Telemetry()
        requests: list[Request] = []
        sleeps: list[float] = []
        clock_values = iter([1.0, 1.1, 2.0, 2.3])

        async def send(request: Request) -> _Response:
            requests.append(request)
            if len(requests) == 1:
                raise TransportError.http(500)
            return _Response(200)

        result = asyncio.run(
            run_with_request_telemetry(
                _policy(max_attempts=1),
                telemetry,
                lambda: Request("POST", "https://example.test"),
                send,
                sleep=lambda delay: sleeps.append(delay),
                clock=lambda: next(clock_values),
            )
        )

        self.assertEqual(result.status, 200)
        self.assertEqual(len(requests), 2)
        self.assertEqual(len(sleeps), 1)
        self.assertEqual(telemetry.events[0][0:3], (0, 500, TransportError.http(500)))
        self.assertEqual(telemetry.events[0][3], 0.10000000000000009)
        self.assertEqual(telemetry.events[1], (1, 200, None, 0.2999999999999998))

    def test_run_with_request_telemetry_records_non_http_error_without_status(self) -> None:
        # Rust crate/module: codex-api/src/telemetry.rs
        # Contract: non-HTTP transport errors record no status and are
        # propagated when retry policy declines them.
        telemetry = _Telemetry()
        clock_values = iter([7.0, 7.5])

        async def send(_request: Request) -> _Response:
            raise TransportError.network("dns")

        with self.assertRaises(TransportError):
            asyncio.run(
                run_with_request_telemetry(
                    _policy(max_attempts=0),
                    telemetry,
                    lambda: Request("GET", "https://example.test"),
                    send,
                    clock=lambda: next(clock_values),
                )
            )

        self.assertEqual(len(telemetry.events), 1)
        attempt, status, error, duration = telemetry.events[0]
        self.assertEqual(attempt, 0)
        self.assertIsNone(status)
        self.assertEqual(error, TransportError.network("dns"))
        self.assertEqual(duration, 0.5)

    def test_run_with_request_telemetry_allows_absent_telemetry(self) -> None:
        # Rust crate/module: codex-api/src/telemetry.rs
        # Contract: telemetry is Option<Arc<dyn RequestTelemetry>>; None skips
        # callbacks while preserving retry/send behavior.
        attempts: list[str] = []
        sleeps: list[float] = []

        async def send(_request: Request) -> _Response:
            attempts.append("send")
            if len(attempts) == 1:
                raise TransportError.http(503)
            return _Response(202)

        result = asyncio.run(
            run_with_request_telemetry(
                _policy(max_attempts=1),
                None,
                lambda: Request("GET", "https://example.test"),
                send,
                sleep=lambda delay: sleeps.append(delay),
            )
        )

        self.assertEqual(result.status, 202)
        self.assertEqual(attempts, ["send", "send"])
        self.assertEqual(len(sleeps), 1)


def _policy(*, max_attempts: int) -> RetryPolicy:
    return RetryPolicy(
        max_attempts=max_attempts,
        base_delay=0.0,
        retry_on=RetryOn(retry_429=True, retry_5xx=True, retry_transport=False),
    )


if __name__ == "__main__":
    unittest.main()
