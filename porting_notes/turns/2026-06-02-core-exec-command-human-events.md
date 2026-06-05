# 2026-06-02 - core exec command human events

## Upstream slice

- Continued the `codex-rs/exec/src/lib.rs#run_exec_session` event-processing path.
- Rust `exec` routes command execution items through the human event processor as command lifecycle output, not only JSON output.

## Python changes

- Updated the local HTTP/core exec human rendering path so synthetic command timeline items are replayed through `HumanEventProcessor` as `item/started` and `item/completed` notifications.
- This makes the default core `exec_command` path visible in normal human output: command start, command/cwd, completion status, and aggregated command output are rendered before the final answer is printed.
- Extended the default core HTTP exec runtime test to verify human output includes `exec`, the command string, `succeeded`, and the command output.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_core_exec_command_smoke_outputs_command_execution tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default`
- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite`
- `git diff --check -- pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py tests\test_cli_parser.py`

The local HTTP smoke run completed 80 tests successfully.

## Known gaps

- This covers synthesized command lifecycle output at turn completion. Fine-grained live streaming deltas for long-running commands still need deeper parity work.
- Full app-server daemon parity remains deferred outside the active core exec path.
