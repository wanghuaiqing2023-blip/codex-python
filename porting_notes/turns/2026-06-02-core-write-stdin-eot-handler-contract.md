# Core write_stdin EOT handler contract

## Upstream slice

- Graph-selected core path: `codex-rs/core/src/session/turn.rs#try_run_sampling_request` routes model tool calls through unified exec handlers.
- Rust source confirmed in `codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`.
- Rust behavior: `WriteStdinHandler` parses `session_id`, `chars`, `yield_time_ms`, and `max_output_tokens`, forwards `args.chars` unchanged into `WriteStdinRequest.input`, and emits a `TerminalInteractionEvent` for any non-empty stdin even when the process exits before the response returns.
- Rust suite coverage nearby: `codex-rs/core/tests/suite/unified_exec.rs#write_stdin_returns_exit_metadata_and_clears_session` uses `"\u{0004}"` to end an interactive session.

## Python work

- Added a core handler regression test in `tests/test_core_unified_exec_handler.py` that sends `"\x04"` through `WriteStdinHandler`.
- The test verifies the manager receives the exact EOT input and that the emitted terminal interaction preserves the same stdin with the original process id fallback.
- This complements the local HTTP runtime test that maps `"\x04"` to stdin closure for stdlib subprocess sessions.

## Validation

- `python -m unittest tests.test_core_unified_exec_handler tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_eot_closes_process_stdin tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_exit_clears_session`
  - Result: 29 tests OK, 1 skipped.

## Deferred

- Full PTY semantics still depend on the eventual unified exec process manager implementation. This turn only pins the model-facing handler contract and local HTTP compatibility behavior on the main exec/tool path.
