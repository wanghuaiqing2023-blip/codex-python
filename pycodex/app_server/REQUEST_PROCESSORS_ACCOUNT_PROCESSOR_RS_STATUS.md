# codex-app-server src/request_processors/account_processor.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/account_processor.rs`

Python module:

- `pycodex/app_server/request_processors_account_processor.py`

Parity tests:

- `tests/test_app_server_request_processors_account_processor_rs.py`

## Behavior contract

- Preserves the module-owned active-login replacement and cancellation state.
- Mirrors account/login validation for external ChatGPT auth and forced API or
  ChatGPT login modes.
- Projects `AccountLoginCompleted`, `AccountUpdated`, logout, cancel-login,
  get-account, rate-limit, and add-credits nudge response shapes.
- Maps missing ChatGPT account details and missing/non-backend auth to Rust's
  invalid-request messages.
- Keeps browser login, device-code completion, backend HTTP, and concrete
  plugin-cache refresh as injected boundaries.

## Notes

This module intentionally does not perform real credential persistence,
browser/device-code login, backend HTTP calls, or plugin/MCP cache refresh.
Those are neighboring dependency/runtime concerns in Rust and are represented
with injectable call sites here.

## Validation

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_account_processor_rs.py -q`
  -> `13 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_account_processor.py
  tests/test_app_server_request_processors_account_processor_rs.py`.
