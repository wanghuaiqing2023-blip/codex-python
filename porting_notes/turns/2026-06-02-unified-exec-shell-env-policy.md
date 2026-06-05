# Unified Exec Shell Environment Policy

- Upstream graph slice: `codex-rs/core/src/exec_env.rs`, `codex-rs/protocol/src/shell_environment.rs`, and `codex-rs/core/src/tools/handlers/shell/shell_command.rs`.
- Confirmed Rust behavior: shell execution builds the child process environment with `create_env(&turn_context.shell_environment_policy, Some(thread_id))`, applying inherit/exclude/include/set rules and injecting `CODEX_THREAD_ID`.
- Python change: `ExecCommandHandler.handle` now uses the invocation turn's `shell_environment_policy` plus the session/turn thread id when spawning its local subprocess fallback, instead of passing through `os.environ.copy()`.
- Added coverage that a non-core environment variable from the parent process does not leak into the child under `inherit=core`, while explicit `set_values` and `CODEX_THREAD_ID` are visible.
- Validation:
  - `python -m unittest tests.test_core_unified_exec_handler`
  - `python -m unittest tests.test_core_unified_exec_handler tests.test_core_exec_env tests.test_protocol_shell_environment tests.test_exec_local_runtime tests.test_exec_run`

Known gaps:

- This aligns the stdlib local fallback path. Full unified exec session/process-manager behavior still remains broader parity work.
