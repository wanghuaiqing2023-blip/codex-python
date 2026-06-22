# codex-app-server src/request_processors/remote_control_processor.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/remote_control_processor.rs`

Python module: `pycodex/app_server/request_processors_remote_control_processor.py`

Status: `complete`

## Scope

Covered behavior:

- `RemoteControlRequestProcessor::new(...)` stores an optional remote-control
  handle.
- Missing handles map to `internal_error("remote control is unavailable for
  this app-server")` for enable, disable, and status reads.
- `enable()` delegates to the handle, maps `RemoteControlUnavailable`-style
  failures through `invalid_request(err.to_string())`, and projects the status
  snapshot into `RemoteControlEnableResponse`.
- `disable()` delegates to the handle and projects the returned status snapshot
  into `RemoteControlDisableResponse`.
- `status_read()` reads the handle status and copies `status`, `server_name`,
  `installation_id`, and `environment_id` into
  `RemoteControlStatusReadResponse`.

Deferred/out of module:

- Remote-control server startup, status watching, and concrete handle
  implementation are owned by transport/runtime modules.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/remote_control_processor.rs`

Python parity tests:

- `tests/test_app_server_request_processors_remote_control_processor_rs.py`

Focused validation passed on 2026-06-19:

- `python -m pytest tests/test_app_server_request_processors_remote_control_processor_rs.py -q`
  -> 4 passed.
- `python -m py_compile pycodex/app_server/request_processors_remote_control_processor.py tests/test_app_server_request_processors_remote_control_processor_rs.py`
