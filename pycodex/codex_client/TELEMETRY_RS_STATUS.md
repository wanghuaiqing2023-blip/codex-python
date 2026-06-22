# codex-client/src/telemetry.rs status

Rust module: `codex/codex-rs/codex-client/src/telemetry.rs`

Python module: `pycodex/codex_client/telemetry.py`

Status: `complete`

Ported contract:

- `RequestTelemetry` is represented as a structural Python protocol.
- Implementors provide `on_request(attempt, status, error, duration)`.
- `status` and `error` may be absent, matching Rust's `Option<StatusCode>` and `Option<&TransportError>`.
- Concrete metrics recording remains owned by core/session telemetry code, not by `codex-client`.

Validation:

- `tests/test_codex_client_telemetry_rs.py`
- Focused command passed on 2026-06-20:
  `C:\Program Files\Maxon Cinema 4D 2025\resource\modules\python\libs\win64\python.exe -m unittest tests.test_codex_client_telemetry_rs tests.test_codex_client_request_rs tests.test_codex_client_error_retry_rs tests.test_codex_client_chatgpt_hosts_rs -v`

