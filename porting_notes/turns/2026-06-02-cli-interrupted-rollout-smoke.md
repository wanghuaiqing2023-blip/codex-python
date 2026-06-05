# CLI interrupted rollout smoke

## Upstream slice

- Used the graph-guided core path for `exec -> turn runtime -> event processor -> rollout`.
- Confirmed Rust human output clears stale final-message state and prints `turn interrupted` for interrupted turns in `codex/codex-rs/exec/src/event_processor_with_human_output.rs`.
- Rust interrupted fork/session behavior records an interrupted-turn boundary marker instead of treating partial assistant text as a completed answer.

## Python slice

- Added CLI-level local HTTP smokes where the runtime returns `UserTurnSamplingResult(turn_status="interrupted")` with a partial assistant message.
- Human output verifies stdout is empty, `turn interrupted` is shown, and the partial assistant text is not rendered.
- JSON output verifies the public event stream stops at `thread.started`, `turn.started`, without emitting the partial assistant message.
- Both modes verify local rollout persistence appends the `<turn_aborted>` marker and a `turn_aborted` event with reason `interrupted`.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_human_without_partial_and_persists_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_json_without_partial_and_persists_marker tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_renders_interrupted_turn_without_final_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_rollout_persists_interrupted_turn_marker`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_runtime_prints_summary_and_final_message tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_json_outputs_thread_and_turn_events tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_human_without_partial_and_persists_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_interrupted_prints_json_without_partial_and_persists_marker tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_context_window_error_prints_json_error_event`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up

- Consolidate the core local HTTP CLI smokes into a maintainable regression subset and continue filling gaps around resume interrupted behavior and shell-tool interrupted follow-ups.
