# codex-app-server request_processors/windows_sandbox_processor.rs status

Rust module: `codex/codex-rs/app-server/src/request_processors/windows_sandbox_processor.rs`

Python module: `pycodex/app_server/request_processors_windows_sandbox_processor.py`

Status: `complete`

## Scope

Covered behavior:

- `WindowsSandboxRequestProcessor::new(...)` stores outgoing, config, and
  config-manager dependencies.
- `windows_sandbox_readiness(...)` projects Rust's readiness response contract,
  including non-Windows `notConfigured` behavior and the disabled,
  restricted-token, elevated-ready, and elevated-update-required state mapping.
- `windows_sandbox_setup_start(...)` returns no final client payload after
  delegating to the inner setup path.
- `windows_sandbox_setup_start_inner(...)` sends
  `WindowsSandboxSetupStartResponse { started: true }` to the request
  connection before the background setup task.
- Background setup projection mirrors Rust's command-cwd selection,
  config-manager reload call, setup-request assembly, and
  `WindowsSandboxSetupCompleted` notification shape for success and error
  results.

Deferred/out of module:

- Concrete Windows sandbox setup execution remains a core/runtime dependency
  and is injected in Python.
- Exact Tokio spawn scheduling and real process/environment side effects remain
  runtime integration boundaries.
- MessageProcessor JSON-RPC dispatch remains outside this module.

## Evidence

Rust source:

- `codex/codex-rs/app-server/src/request_processors/windows_sandbox_processor.rs`

Python parity tests:

- `tests/test_app_server_request_processors_windows_sandbox_processor_rs.py`

Focused validation passed on 2026-06-19:

- `python -m pytest tests/test_app_server_request_processors_windows_sandbox_processor_rs.py -q`
  -> 6 passed.
- `python -m py_compile pycodex/app_server/request_processors_windows_sandbox_processor.py tests/test_app_server_request_processors_windows_sandbox_processor_rs.py`
