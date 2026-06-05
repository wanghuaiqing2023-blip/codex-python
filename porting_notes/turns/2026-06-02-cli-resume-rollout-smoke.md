# CLI local HTTP resume rollout smoke

## Graph-guided slice

- Upstream graph/source entrypoint: `codex-rs/exec/src/lib.rs#run_exec_session`.
- Rust resume path confirmed from source:
  - `run_exec_session` handles `ExecCommand::Resume`.
  - It resolves the target thread and resumes it before executing the next
    user turn.
- Python target slice:
  - `pycodex.cli.parser` dispatches `codex exec resume`.
  - `pycodex.exec.local_runtime.align_local_http_exec_resume_model_client`
    resolves the local rollout.
  - `pycodex.exec.local_runtime.run_exec_resume_user_turn_http_sampling`
    reconstructs model history and appends the resumed turn to the same
    rollout JSONL file.

## Progress

- Added a CLI-level smoke test for local HTTP resume that runs through
  `main(["exec", "resume", ...])` instead of patching the resume runner.
- The test creates a prior rollout with a user and assistant message, resumes
  that thread through the CLI, verifies the request includes the prior visible
  history before the current prompt, and verifies the final assistant answer is
  appended to the same rollout file.
- Added a CLI-level resume shell-tools smoke that resumes a rollout, accepts a
  model `exec_command` tool call, executes a safe local Python subprocess,
  sends the resulting `function_call_output` in a follow-up request, and
  persists the final assistant answer back into the same rollout.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_posts_expected_request tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_last_uses_resume_runner tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_reads_history_and_appends_result_to_same_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_posts_expected_request tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_reads_history_and_appends_result_to_same_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup`
- `python -m py_compile tests\test_cli_parser.py`

## Deferred

- Full app-server `thread/resume` parity.
- Resume/fork handling for multi-agent and cloud paths.
