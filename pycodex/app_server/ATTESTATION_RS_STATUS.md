# codex-app-server src/attestation.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/attestation.rs`

Python module:

- `pycodex/app_server/attestation.py`

## Covered contract

- `ATTESTATION_GENERATE_TIMEOUT_MILLIS` mirrors Rust's 100 ms timeout constant.
- `AppServerAttestationStatus` preserves Rust wire status codes:
  `Ok = 0`, `Timeout = 1`, `RequestFailed = 2`,
  `RequestCanceled = 3`, and `MalformedResponse = 4`.
- `app_server_attestation_header_value(...)` mirrors Rust's compact JSON
  envelope shape with version `v = 1`, status `s`, and optional token `t`.
- `attestation_request_projection(...)` records the module-local result
  mapping for absent attestation-capable connections, success, request failure,
  request cancellation, timeout cancellation, and malformed response.

## Deferred

- The concrete `AttestationProvider` trait object, weak `OutgoingMessageSender`
  upgrade, `ThreadStateManager` lookup, async timeout execution, JSON-RPC
  request delivery, and HTTP `HeaderValue` validation remain runtime
  dependencies outside this pure projection.

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_attestation_rs.py -q`
  -> `4 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/attestation.py
  tests/test_app_server_attestation_rs.py`.
