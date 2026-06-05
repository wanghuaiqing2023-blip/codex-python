# HTTP guardian output schema strict inference

## Upstream slice

- Graph-selected core path: `codex-rs/core/src/session/turn.rs#run_sampling_request` builds the prompt and then sends it through the model client.
- Rust source behavior in `session/turn.rs#build_prompt`: `output_schema_strict` is false only when `guardian::is_guardian_reviewer_source(&turn_context.session_source)` is true; otherwise it is true.

## Python work

- The Python turn request path already inferred guardian reviewer strictness when `output_schema_strict` is `None`.
- Fixed `pycodex/core/http_transport.py` so `run_user_turn_http_sampling_from_session` defaults `output_schema_strict` to `None` instead of forcing `True`.
- Added an HTTP-path regression test proving a guardian subagent session sends `text.format.strict == False` in the actual prepared HTTP request body when an output schema is present.

## Validation

- `python -m unittest tests.test_core_http_transport.HttpTransportTests.test_run_user_turn_http_sampling_infers_guardian_output_schema_non_strict tests.test_core_turn_request.TurnRequestTests.test_build_turn_responses_request_infers_non_strict_schema_for_guardian_reviewer`
  - Result: 2 tests OK.
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_request tests.test_core_turn_runtime`
  - Result: 110 tests OK.

## Deferred

- This keeps the main HTTP sampling path aligned with Rust. Other specialized callers that intentionally force strictness, such as compaction, remain unchanged.
