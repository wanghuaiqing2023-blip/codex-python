# codex-app-server src/error_code.rs alignment

Rust module:

`codex/codex-rs/app-server/src/error_code.rs`

Python target:

`pycodex/app_server/error_code.py`

Status: `complete`

## Covered

- JSON-RPC error code constants:
  `INVALID_REQUEST_ERROR_CODE`, `METHOD_NOT_FOUND_ERROR_CODE`,
  `INVALID_PARAMS_ERROR_CODE`, `INTERNAL_ERROR_CODE`,
  `OVERLOADED_ERROR_CODE`, and `INPUT_TOO_LARGE_ERROR_CODE`.
- `invalid_request(...)`, `method_not_found(...)`, `invalid_params(...)`,
  and `internal_error(...)` construct `JSONRPCErrorError` values with the
  Rust module's fixed code, string message, and `data = None`.
- The Python module depends only on the already-ported protocol
  `JSONRPCErrorError` shape.

## Evidence

- Rust source:
  `codex/codex-rs/app-server/src/error_code.rs`
- Rust consumers:
  `codex/codex-rs/app-server/src/command_exec.rs`
  `codex/codex-rs/app-server/src/in_process.rs`
  `codex/codex-rs/app-server/src/message_processor.rs`
  `codex/codex-rs/app-server/src/outgoing_message.rs`
  `codex/codex-rs/app-server/src/request_processors.rs`
- Python tests:
  `tests/test_app_server_error_code_rs.py`

## Validation

- 2026-06-19: `python -m pytest tests/test_app_server_error_code_rs.py -q`
  -> `3 passed`.
- 2026-06-19: `python -m py_compile pycodex/app_server/error_code.py
  tests/test_app_server_error_code_rs.py`.
