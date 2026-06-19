# codex-app-server request_processors/environment_processor.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/environment_processor.rs`

Python module: `pycodex/app_server/request_processors_environment_processor.py`

Status: `complete`

## Scope

Covered behavior:

- `EnvironmentRequestProcessor::new(...)` stores the environment manager.
- `environment_add(...)` forwards `environment_id` and `exec_server_url` to
  `EnvironmentManager::upsert_environment`.
- Upsert errors are converted with `invalid_request(err.to_string())`.
- Successful adds return an empty `EnvironmentAddResponse`.

Deferred/out of module:

- Concrete environment manager persistence and validation.
- MessageProcessor JSON-RPC dispatch and response-envelope wrapping.
- Async runtime scheduling.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/environment_processor.rs`

Python parity tests:

- `tests/test_app_server_request_processors_environment_processor_rs.py`

## Validation

- 2026-06-19: `python -m pytest
  tests/test_app_server_request_processors_environment_processor_rs.py -q`
  -> `4 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/request_processors_environment_processor.py
  tests/test_app_server_request_processors_environment_processor_rs.py`.
