# codex-api/src/telemetry.rs status

Rust module: `codex/codex-rs/codex-api/src/telemetry.rs`

Python module: `pycodex/codex_api/telemetry.py`

Status: `complete`

Ported contract:

- Public `SseTelemetry` and `WebsocketTelemetry` trait surfaces are represented
  as structural Python protocols.
- `response_status` mirrors the local `WithStatus` status extraction boundary.
- `http_status` mirrors the Rust helper that returns a status only for
  `TransportError::Http`.
- `run_with_request_telemetry` wraps an async send boundary, records elapsed
  duration per attempt, reports `(attempt, status, error, duration)` to
  `RequestTelemetry`, retries only when the supplied `RetryPolicy` accepts the
  transport error, allows absent telemetry without changing retry/send
  behavior, and propagates the final transport error otherwise.

Intentional adaptation:

- Rust delegates retry timing to `codex_client::run_with_retry` and Tokio.
  Python keeps an async local loop in this module because the existing
  dependency-light `codex_client.run_with_retry` helper is synchronous.

Validation:

- `tests/test_codex_api_telemetry_rs.py`
- Focused validation command:
  `python -m pytest tests/test_codex_api_telemetry_rs.py -q --tb=short`
  (`6 passed`)
- Syntax validation:
  `python -m py_compile pycodex\codex_api\telemetry.py tests\test_codex_api_telemetry_rs.py`
- Codex API focused validation:
  `python -m pytest $tests -q --tb=short` where `$tests` is expanded from
  `tests/test_codex_api_*_rs.py` (`213 passed, 47 subtests passed`)
