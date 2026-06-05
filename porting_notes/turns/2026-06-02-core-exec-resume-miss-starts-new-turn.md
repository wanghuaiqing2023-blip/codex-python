# Core exec resume miss starts new turn

## Source graph slice

- Graph nodes:
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:564`
  - `function:codex-rs/exec/src/lib.rs#resolve_resume_thread_id:1335`
- Rust source shows `run_exec_session` calls `resolve_resume_thread_id` for `exec resume`.
- If a matching thread is found, Rust sends `thread/resume`.
- If no matching thread is found, Rust sends `thread/start` and continues with the same initial user turn instead of failing.

## Python port

- `pycodex.exec.core_runtime.resolve_core_exec_resume_target` now returns `None` when the local resume lookup misses, rather than raising `no local rollout found for resume`.
- `run_core_exec_command(command="resume")` treats a missing target as a fresh core user turn, runs `run_exec_user_turn_core_http_sampling`, and persists the new turn as an owned exec rollout.
- CLI core resume now allows `resume_target=None` through to the core runner, matching Rust's `thread/start` fallback shape.

## Validation

- `python -m unittest tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_resolve_core_exec_resume_target_rejects_missing_args_and_returns_none_without_rollout tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_run_core_exec_command_resume_without_target_starts_new_turn_and_persists tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_run_core_exec_command_runs_resume_without_persisting`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_core_env_without_target_starts_new_core_turn tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_core_env_uses_core_resume_runner`

## Follow-up

- The explicit local HTTP compatibility resume path still reports missing local rollouts as an error. The core default path now follows Rust's fallback behavior; the compatibility path can be cleaned up once the core path has fully replaced it.
