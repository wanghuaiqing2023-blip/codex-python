# codex-app-server request_processors/config_errors.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/config_errors.rs`

Python module: `pycodex/app_server/request_processors_config_errors.py`

Status: `complete`

## Scope

Covered behavior:

- `cloud_requirements_load_error(...)` walks the wrapped/source exception chain
  and returns the first cloud requirements load error.
- `config_load_error(...)` returns an `invalid_request` JSON-RPC error with
  message prefix `failed to load configuration: ...`.
- Cloud requirements failures add structured data with
  `reason: cloudRequirements`, Rust Debug-style `errorCode`, and `detail`.
- Cloud requirements failures with a status code include `statusCode`.
- Auth cloud requirements failures include `action: relogin`.
- Non-cloud requirements failures keep `data` unset.

Deferred/out of module:

- Loading configuration and cloud requirements remains owned by neighboring
  config modules.
- Request processors that call this helper remain separate module boundaries.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/config_errors.rs`

Rust behavior anchors:

- `config_load_error_marks_cloud_requirements_failures_for_relogin`
- `config_load_error_leaves_non_cloud_requirements_failures_unmarked`
- `config_load_error_marks_non_auth_cloud_requirements_failures_without_relogin`

Python parity tests:

- `tests/test_app_server_request_processors_config_errors_rs.py`

## Validation

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_config_errors_rs.py -q`
  -> `3 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_config_errors.py
  tests/test_app_server_request_processors_config_errors_rs.py`.
