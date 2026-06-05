# Local HTTP write_stdin EOT closes stdin

## Upstream graph and source slice

- Graph node: `function:codex-rs/core/src/session/turn.rs#try_run_sampling_request`
- Graph node: `function:codex-rs/core/tests/suite/unified_exec.rs#write_stdin_returns_exit_metadata_and_clears_session`
- Source: `codex/codex-rs/core/tests/suite/unified_exec.rs`

Rust unified exec supports terminal-style EOF through `write_stdin` by sending
EOT (`\u{0004}` / Ctrl-D) to a live session. The upstream test uses that input
to terminate a running `cat` session and then expects exit metadata with no
process id/session id in the final output.

## Python changes

- Updated `LocalHttpExecSession.write` so a `write_stdin` payload containing
  exactly `"\x04"` closes the subprocess stdin pipe instead of writing a literal
  EOT byte.
- Added a local HTTP exec end-to-end test that starts a stdin-reading process,
  writes a normal line while the session remains live, then sends `"\x04"` and
  verifies the process exits cleanly and no `session_id` remains in the output.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_eot_closes_process_stdin`
- `python -m unittest tests.test_exec_local_runtime tests.test_core_unified_exec_handler tests.test_core_turn_runtime tests.test_core_session_runtime`

