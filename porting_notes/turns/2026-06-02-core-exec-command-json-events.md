# 2026-06-02 - core exec command JSON events

## Upstream slice

- Continued the `codex-rs/exec/src/lib.rs#run_exec_session` event rendering slice.
- Rust `exec` exposes command execution as `CommandExecutionItem` values with in-progress/completed status, command text, aggregated output, and optional exit code.

## Python changes

- Added focused coverage for the default core HTTP `exec_command` path to prove it emits user-visible `command_execution` items.
- The runtime test now verifies that `run_exec_user_turn_http_sampling` maps core `tool_response_items` into in-progress/completed command timeline items and JSON `item.completed` events.
- Added a CLI `--json` smoke test that runs through `main(["exec", "--json", ...])`, receives an HTTP `exec_command` tool call, executes it via the core tool router, sends the tool output in the follow-up request, and emits command execution events plus the final agent message.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_core_exec_tool_loop_by_default`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_core_exec_command_smoke_outputs_command_execution`
- `python -m py_compile tests\test_cli_parser.py tests\test_exec_local_runtime.py pycodex\exec\local_runtime.py`
- `python -m unittest tests.test_cli_local_http_smoke_suite tests.test_local_http_core_smoke_suite`
- `git diff --check -- tests\test_cli_parser.py tests\test_exec_local_runtime.py pycodex\exec\local_runtime.py`

The local HTTP smoke run completed 80 tests successfully.

## Known gaps

- This locks JSON event rendering for `exec_command`; broader human live-progress rendering still depends on the current in-memory session event replay behavior.
- Full app-server parity and unrelated CLI suites remain outside this core exec slice.
