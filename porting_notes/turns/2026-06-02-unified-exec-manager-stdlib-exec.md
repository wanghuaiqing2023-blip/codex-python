# 2026-06-02 unified exec manager stdlib execution

## Upstream slice

- Checked `codex/codex-rs/core/src/unified_exec/process_manager.rs`.
- The core path stores a live process before the initial yield, collects output until a deadline, returns `ExecCommandToolOutput`, keeps `process_id` for live sessions, and resolves `write_stdin` polls with the empty-input background timeout bounds.

## Python slice

- Added a stdlib-backed `_ManagedUnifiedExecSession` in `pycodex/core/unified_exec.py`.
- `UnifiedExecProcessManager.exec_command()` now starts local subprocesses, applies the unified exec environment overlay, captures combined stdout/stderr, returns completed outputs, and keeps live sessions in the process store.
- `UnifiedExecProcessManager.write_stdin()` now writes to tty sessions, polls incremental output, returns exit codes, and clears completed sessions.
- Process release now closes completed subprocess pipes to keep test output clean.

## Validation

- `python -m py_compile pycodex/core/unified_exec.py tests/test_core_unified_exec.py`
- `python -m unittest tests.test_core_unified_exec`
- `python -m unittest tests.test_core_unified_exec_handler tests.test_core_tool_router tests.test_exec_local_runtime`

## Known follow-up debt

- This is a local stdlib approximation, not the full Rust sandbox/network/PTY implementation.
- Non-tty stdin remains intentionally closed, matching the user-facing Rust error boundary for `write_stdin`.
- Event emission and app-server daemon integration remain outside this core manager slice.
