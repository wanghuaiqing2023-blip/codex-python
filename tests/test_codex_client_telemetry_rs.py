"""Rust-derived tests for ``codex-client/src/telemetry.rs``.

Rust crate: ``codex-client``
Rust module: ``src/telemetry.rs``

Behavior contract:
- expose a request telemetry interface with ``on_request(attempt, status,
  error, duration)``;
- accept absent status/error values;
- keep concrete recording outside ``codex-client``.
"""

from __future__ import annotations

import unittest
from dataclasses import dataclass

from pycodex.codex_client import RequestTelemetry
from pycodex.codex_client import TransportError


@dataclass
class RecordedRequest:
    attempt: int
    status: int | None
    error: TransportError | None
    duration: float


class RecordingTelemetry:
    def __init__(self) -> None:
        self.requests: list[RecordedRequest] = []

    def on_request(
        self,
        attempt: int,
        status: int | None,
        error: TransportError | None,
        duration: float,
    ) -> None:
        self.requests.append(RecordedRequest(attempt, status, error, duration))


class CodexClientTelemetryRsTests(unittest.TestCase):
    def test_request_telemetry_is_structural_on_request_contract(self) -> None:
        telemetry = RecordingTelemetry()

        self.assertIsInstance(telemetry, RequestTelemetry)
        telemetry.on_request(2, 429, TransportError.http(429, body="slow"), 0.125)

        self.assertEqual(
            telemetry.requests,
            [RecordedRequest(2, 429, TransportError.http(429, body="slow"), 0.125)],
        )

    def test_request_telemetry_accepts_absent_status_and_error(self) -> None:
        telemetry = RecordingTelemetry()

        telemetry.on_request(0, None, None, 0.0)

        self.assertEqual(telemetry.requests, [RecordedRequest(0, None, None, 0.0)])


if __name__ == "__main__":
    unittest.main()
