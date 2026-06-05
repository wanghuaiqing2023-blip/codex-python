# Core resume output-schema request

## Source slice

- Graph entrypoint: `function:codex-rs/exec/src/lib.rs#run_exec_session:564`.
- Graph-related node: `function:codex-rs/exec/src/lib.rs#load_output_schema:1661`.
- Rust source check: `codex-rs/exec/src/lib.rs` builds `InitialOperation::UserTurn { items, output_schema }` for both fresh `exec` and `resume`, then passes that schema through `TurnStartParams.output_schema`.
- Rust source check: `codex-rs/core/src/session/turn.rs::build_prompt` forwards `turn_context.final_output_json_schema` to the model `Prompt.output_schema`.

## Python port

- Added focused coverage for the direct core resume HTTP path in `tests/test_exec_local_runtime.py`.
- The test materializes a resumable rollout, runs `run_exec_resume_user_turn_core_http_sampling` with an `InitialOperation.user_turn(..., output_schema=...)`, and asserts that the outgoing Responses request preserves the schema under `text.format.schema`.
- No runtime change was needed; the existing implementation already routes the schema through the prepared plan into core request construction.

## Validation

- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_core_http_resume_runner_passes_output_schema_to_request`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_run_exec_user_turn_http_sampling_uses_exec_config_and_plan tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_core_http_resume_runner_uses_reconstructed_history_and_persists_output tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_core_http_resume_runner_passes_output_schema_to_request tests.test_exec_core_runtime`
