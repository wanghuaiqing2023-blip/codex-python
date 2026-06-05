# CLI resume interrupted rollout smoke

## Upstream slice

- Continued the core `exec resume -> existing rollout history -> turn runtime -> event processor -> rollout append` path.
- Rust interrupted-turn behavior clears partial final-message output and records an interrupted boundary rather than treating partial assistant text as a completed turn.

## Python slice

- Added a CLI-level local HTTP resume smoke where the resumed turn returns `UserTurnSamplingResult(turn_status="interrupted")` with a partial assistant message.
- The test keeps the resume command path real: it creates an existing rollout, runs `codex exec resume <thread> ...`, and lets the resume runner append to that rollout.
- Verifies stdout stays empty, stderr reports `turn interrupted`, the partial assistant message is not rendered, and the existing rollout gets both the `<turn_aborted>` marker and a `turn_aborted` event with reason `interrupted`.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_interrupted_appends_marker_and_suppresses_partial tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_persists_interrupted_turn_event`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_human_without_partial_and_persists_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_json_without_partial_and_persists_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_interrupted_appends_marker_and_suppresses_partial tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up

- Cover interrupted shell-tool follow-up behavior, then consolidate the growing core CLI smoke set into a documented regression command group.
