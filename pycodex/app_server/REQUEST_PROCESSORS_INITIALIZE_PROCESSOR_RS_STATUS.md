# codex-app-server src/request_processors/initialize_processor.rs alignment

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/initialize_processor.rs`

Python module:

- `pycodex/app_server/request_processors_initialize_processor.py`

Parity tests:

- `tests/test_app_server_request_processors_initialize_processor_rs.py`

## Behavior contract

- Rejects duplicate initialize requests before committing session state.
- Validates `clientInfo.name` as an HTTP header value before session mutation.
- Commits the initialized session capability state, opt-out notification
  method set, client name/version, and attestation flag.
- Projects Rust's non-originating client-name allowlist, analytics
  `track_initialize`, residency setter, user-agent suffix update, and
  `InitializeResponse` construction.
- Sends stored config-warning notifications to one connection or as broadcast.
- Forwards initialized request analytics via `track_initialized_request`.

## Notes

Global default-client mutation and platform/user-agent values are injectable so
the module can be verified without mutating process-global test state. Concrete
transport routing remains owned by the caller/runtime.

## Validation

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_initialize_processor_rs.py -q`
  -> `7 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_initialize_processor.py
  tests/test_app_server_request_processors_initialize_processor_rs.py`.
