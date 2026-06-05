# Core exec resume single resolution

## Source graph slice

- Graph nodes:
  - `function:codex-rs/exec/src/lib.rs#run_exec_session:564`
  - `function:codex-rs/exec/src/lib.rs#resolve_resume_thread_id:1335`
- Rust source resolves the resume target once inside `run_exec_session`.
- The result of that lookup directly chooses either `thread/resume` or `thread/start`; it does not re-run the lookup after printing configuration.

## Python port

- Added `resume_target_resolved` to `pycodex.exec.core_runtime.run_core_exec_command`.
- CLI core resume now passes `resume_target_resolved=True` after its pre-run target lookup.
- A pre-resolved miss now goes straight to the fresh core user turn fallback without doing a second local resume lookup.

## Validation

- `python -m unittest tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_run_core_exec_command_resume_pre_resolved_miss_does_not_lookup_again tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_run_core_exec_command_resume_without_target_starts_new_turn_and_persists tests.test_exec_core_runtime.ExecCoreRuntimeTests.test_run_core_exec_command_runs_resume_without_persisting`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_core_env_without_target_starts_new_core_turn tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_core_env_uses_core_resume_runner`

## Follow-up

- Once the core facade is no longer a compatibility layer over local rollout helpers, resume resolution should move from local rollout lookup toward the Rust `thread/list`/state-db shape.
