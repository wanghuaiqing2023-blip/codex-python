# 2026-06-02 local HTTP local_shell_call missing-output timeline

## Upstream slice

- Continued the core `exec -> history normalization -> user-visible command event` path.
- Confirmed Rust behavior in `codex/codex-rs/core/src/context_manager/normalize.rs`: a `ResponseItem::LocalShellCall` with a `call_id` but no matching `FunctionCallOutput` gets a synthetic `FunctionCallOutput` with text `aborted`.
- This is core Responses/history behavior, not MCP/plugin behavior.

## Python change

- Updated `pycodex/exec/local_runtime.py` timeline reconstruction to insert a synthetic `function_call_output` of `aborted` for `local_shell_call` items that have no matching output.
- This aligns live JSON event rendering with the existing prompt-visible rollout normalization, which already inserted the same synthetic output for persistence.

## Tests

- Extended `test_local_http_rollout_inserts_missing_output_for_local_shell_call` so it now verifies both prompt-visible rollout normalization and timeline rendering.
- Timeline now emits an in-progress `command_execution` followed by a completed `command_execution` with aggregated output `aborted`.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_inserts_missing_output_for_local_shell_call tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_maps_local_shell_call_to_command_execution`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_calls_when_raw_payload_is_absent tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_uses_response_item_outputs_when_raw_payload_is_absent tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_uses_reconstructed_model_history tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_runner_shell_tools_preserves_history_and_appends_followup tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_preserves_history_across_two_rounds`

## Known gaps

- This preserves the normalized event shape for missing local-shell outputs. It does not implement additional local-shell execution runtime beyond the existing shell tools.
