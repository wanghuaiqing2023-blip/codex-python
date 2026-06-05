# 2026-06-02 - exec core sampling bridge

## Upstream slice

- Used `codex/.understand-anything/knowledge-graph.json` to narrow the current core exec path to `codex-rs/exec/src/lib.rs`.
- Confirmed from Rust source that `run_exec_session` prepares an `InitialOperation::UserTurn`, starts/resumes a thread, sends `TurnStartParams`, then processes events until the turn completes.
- Deferred the remote/app-server event loop details; the current Python slice focuses on the user-turn handoff into the in-memory core loop.

## Python changes

- Added `run_exec_user_turn_core_sampling` in `pycodex/exec/local_runtime.py`.
- The helper accepts an `ExecSessionConfig`, prepared `ExecRunPlan`, model client/provider/model info, and an injected sampler, then runs `InMemoryCodexSession -> run_user_turn_sampling_from_session`.
- Session construction now includes a default local environment selection so the core runtime exposes the default `exec_command`/`write_stdin` tool route.
- Added an offline exec smoke test proving a prepared exec plan can request `exec_command`, receive the tool output in the follow-up request, and finish with a final assistant message.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_core_sampling_runs_default_exec_tool_loop`
- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime tests.test_core_turn_runtime tests.test_core_unified_exec tests.test_core_unified_exec_handler`

The combined suite ran 337 tests successfully with 1 skipped test.

## Known gaps

- The default CLI `exec` entrypoint still uses the existing remote/app-server path unless the local HTTP path is explicitly enabled.
- The new bridge is intentionally sampler-injected and offline-testable; wiring it to the real default CLI transport is the next core-path step.
