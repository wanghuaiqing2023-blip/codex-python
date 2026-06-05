# 2026-06-02 CLI in-memory core resume entrypoint

## Upstream slice

- Continued the graph-guided `codex exec` session path into resume:
  - `codex-rs/exec/src/lib.rs`
    - `run_exec_session` resolves `ExecCommand::Resume`, resumes the thread, and then submits the next user turn.
    - `resolve_resume_thread_id` handles `--last`, UUID thread ids, and named sessions before `thread/resume`.
  - `codex-rs/core/src/session/turn.rs`
    - the resumed thread still enters the same `run_turn` loop for request construction, tool dispatch, follow-up sampling, and final output.

## Python change

- Added `run_exec_resume_user_turn_core_http_sampling`.
- The new runner reuses the existing local rollout resume behavior:
  - resolve/align the rollout thread id;
  - read model-visible history from rollout;
  - run the next user turn through `run_exec_user_turn_core_http_sampling`;
  - append the resumed turn back to the rollout.
- `PYCODEX_EXEC_CORE=1` now covers fresh `codex exec` and `codex exec resume ...`.
- `review` remains on the existing path until its review-specific rendering and rollout behavior can be moved safely.

## Validation

- `uvx pytest tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_resume_core_env_uses_core_resume_runner tests/test_exec_local_runtime.py::ExecLocalRuntimeTests::test_core_http_resume_runner_uses_reconstructed_history_and_persists_output -q`
  - 2 passed.
- `uvx pytest tests/test_cli_parser.py -k "main_exec_resume_core_env or main_exec_resume_local_http_last or main_exec_core_env" -q`
  - 3 passed.
- `uvx pytest tests/test_exec_local_runtime.py -k "core_http_resume_runner or local_http_resume_runner_uses_core_exec_tool_loop or default_local_http_runtime_uses_env_provider" -q`
  - 3 passed.
- `python -m py_compile pycodex/cli/parser.py pycodex/exec/local_runtime.py tests/test_cli_parser.py tests/test_exec_local_runtime.py`
  - passed.
- `uvx pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 738 passed, 1 skipped, 98 subtests passed.

## Follow-up

- Move review onto the direct core path once its review-task prompt/output rendering is isolated from the local HTTP compatibility layer.
- Continue renaming or splitting `local_http` helpers that now serve both the compatibility path and the direct core path.
