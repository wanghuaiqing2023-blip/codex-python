# codex-app-server src/server_request_error.rs alignment

Rust module:

`codex/codex-rs/app-server/src/server_request_error.rs`

Python target:

`pycodex/app_server/server_request_error.py`

Status: `complete`

## Covered

- `TURN_TRANSITION_PENDING_REQUEST_ERROR_REASON` mirrors Rust's
  `"turnTransition"` constant used to mark server-request cancellation caused
  by a turn-state transition.
- `is_turn_transition_server_request_error(...)` mirrors the Rust helper:
  inspect the JSON-RPC error's optional `data.reason` field and return true
  only when it is the exact string `"turnTransition"`.
- The Python helper accepts the existing protocol `JSONRPCErrorError`
  dataclass as well as mapping/object-shaped errors so later app-server modules
  can share this local boundary without importing concrete transport runtime
  types.

## Evidence

- Rust source:
  `codex/codex-rs/app-server/src/server_request_error.rs`
- Rust local tests:
  `turn_transition_error_is_detected`
  `unrelated_error_is_not_detected`
- Python tests:
  `tests/test_app_server_server_request_error_rs.py`

## Validation

- 2026-06-19: `python -m pytest
  tests/test_app_server_server_request_error_rs.py -q` -> `3 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/server_request_error.py
  tests/test_app_server_server_request_error_rs.py`.
