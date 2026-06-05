# Exec Output Schema Tool Follow-Up

## Upstream graph slice

- Core path: `exec -> InitialOperation::UserTurn -> final_output_json_schema -> build_prompt -> Responses request text format`.
- Rust source read:
  - `codex/codex-rs/exec/src/lib.rs`
  - `codex/codex-rs/core/src/session/turn_context.rs`
  - `codex/codex-rs/core/src/session/turn.rs`

## Rust behavior confirmed

- `codex exec --output-schema` loads the JSON schema into `InitialOperation::UserTurn`.
- The session turn context stores `final_output_json_schema` for the turn.
- Every prompt built from that turn context passes the schema to the model request, so tool-output follow-up sampling still uses the same final response schema.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Added an `output_schema` parameter to `run_exec_tool_output_http_sampling`.
  - Passed that schema into `run_user_turn_http_sampling_from_session` for tool-output follow-up requests.
  - Wired `run_exec_user_turn_with_shell_tools_http_sampling` to forward `plan.initial_operation.output_schema` into each follow-up round.

- `tests/test_exec_local_runtime.py`
  - Extended the shell-tool loop test to assert both the initial request and the follow-up request preserve the configured JSON output schema.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_result_maps_usage`
- `python -m unittest tests.test_exec_local_runtime`

## Known gaps

- This preserves request construction parity for local HTTP shell-tool loops. It does not add local JSON-schema validation of the final answer; Rust relies on the Responses request format for this path.
