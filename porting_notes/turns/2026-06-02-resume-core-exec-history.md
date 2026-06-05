# 2026-06-02 - resume core exec history

## Upstream slice

- Continued the `codex-rs/exec/src/lib.rs#run_exec_session` resume branch.
- Rust `exec resume` resolves a thread, resumes it, sends the new user turn, and keeps the model-visible conversation history available for the next request.

## Python changes

- Added focused coverage for local HTTP resume on the default core tool route.
- The new test proves `run_exec_resume_user_turn_http_sampling` reconstructs prior rollout history, sends the resumed prompt, executes a new `exec_command` through the core tool router, sends the tool output in the follow-up HTTP request, and appends the function call, function call output, and final message back to the same rollout.
- No implementation change was needed for this slice; the coverage locks in behavior after the default route moved from the legacy shell-loop to the core runtime router.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_core_exec_tool_loop_and_persists_outputs`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_reads_history_and_appends_result_to_same_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_core_exec_tool_loop_and_persists_outputs tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history`
- `python -m py_compile tests\test_exec_local_runtime.py pycodex\exec\local_runtime.py`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite`
- `git diff --check -- tests\test_exec_local_runtime.py pycodex\exec\local_runtime.py tests\test_cli_parser.py`

The local HTTP smoke run completed 80 tests successfully.

## Known gaps

- Resume-by-app-server thread APIs are still represented by local rollout compatibility logic in this Python path.
- Live streaming and approval behavior inside resumed turns still need deeper parity coverage.
