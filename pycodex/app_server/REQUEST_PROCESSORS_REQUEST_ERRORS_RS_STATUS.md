# codex-app-server request_processors/request_errors.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/request_errors.rs`

Python module: `pycodex/app_server/request_processors_request_errors.py`

Status: `complete`

## Scope

Covered behavior:

- `environment_selection_error_message(...)` returns the raw
  `CodexErr::InvalidRequest(message)` message.
- Non-`InvalidRequest` errors fall through to their display string.
- Python also accepts mapping/duck-typed invalid-request values at the
  app-server boundary, while preserving the Rust behavior for `CodexErr`.

Deferred/out of module:

- Environment selection itself is owned by core environment-selection modules.
- The request processors that call this helper are separate Rust modules.
- JSON-RPC error construction remains owned by `src/error_code.rs`.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/request_errors.rs`

Python parity tests:

- `tests/test_app_server_request_processors_request_errors_rs.py`

## Validation

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_request_errors_rs.py -q`
  -> `3 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_request_errors.py
  tests/test_app_server_request_processors_request_errors_rs.py`.
