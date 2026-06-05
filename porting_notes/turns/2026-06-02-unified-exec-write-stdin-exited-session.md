## Unified exec write_stdin exited-session parity

Slice:

- Upstream graph nodes:
  - `codex-rs/core/src/unified_exec/process_manager.rs#write_stdin`
  - `codex-rs/core/src/unified_exec/process_manager.rs#refresh_process_state`
  - `codex-rs/core/src/unified_exec/mod_tests.rs#reusing_completed_process_returns_unknown_process`
- Authoritative Rust behavior:
  - `write_stdin` attempts to write non-empty input to the live process.
  - If writing fails, Rust refreshes the process state. When the process has already exited, it continues to collect output and returns an `ExecCommandToolOutput` with `process_id: None` and the exit code instead of surfacing `StdinClosed`.
  - Unknown already-removed process ids still return `UnknownProcessId`.

Python changes:

- `pycodex/core/unified_exec.py`
  - `UnifiedExecProcessManager.write_stdin` now catches unified-exec write errors and, if the session has already exited, continues to snapshot and clean up the process.
  - `_ManagedUnifiedExecSession.close` tolerates stale stream close errors after process exit, matching the user-visible cleanup behavior needed for the returned final output path.
- `tests/test_core_unified_exec.py`
  - Added a subprocess-backed regression test where a session exits between the initial `exec_command` snapshot and the follow-up `write_stdin`; Python now returns the final output instead of failing with stdin closed.

Validation:

- `python -m py_compile pycodex\core\unified_exec.py pycodex\core\unified_exec_handler.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_unified_exec.py -q`
  - `46 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_unified_exec.py tests\test_core_unified_exec_handler.py tests\test_core_exec.py tests\test_core_tool_router.py -q`
  - `150 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

Known gaps:

- Python still uses a lightweight stdlib process manager rather than Rust's full async watcher and PTY implementation; this slice preserves the common user-facing exited-session result behavior.
