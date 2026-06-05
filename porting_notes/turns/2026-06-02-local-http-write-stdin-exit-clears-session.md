# Local HTTP write_stdin exit clears session

## Upstream graph and source slice

- Graph node: `function:codex-rs/exec/src/lib.rs#run_exec_session`
- Graph node: `function:codex-rs/core/tests/suite/unified_exec.rs#write_stdin_returns_exit_metadata_and_clears_session`
- Source: `codex/codex-rs/core/tests/suite/unified_exec.rs`

Rust's unified exec test verifies that a background `exec_command` session
continues to expose its process id while running, but after `write_stdin`
causes the process to exit, the final output reports exit metadata and the
session is cleared. A later write to the same id must therefore be treated as an
unknown process/session.

## Python changes

- Added a local HTTP exec end-to-end test that starts a stdin-driven background
  process, writes input through `write_stdin`, observes a clean exit, and then
  attempts to write to the stale session id.
- The stale write now has explicit regression coverage for the model-visible
  unknown-session error path.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_exit_clears_session`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_turn_runtime tests.test_core_session_runtime`

