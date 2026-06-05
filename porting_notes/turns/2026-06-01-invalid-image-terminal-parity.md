## 2026-06-01 Invalid Image Terminal Error Parity

### Scope

- Aligned the Python core turn runtime with Rust `run_turn` for unrecoverable invalid-image sampling errors.
- Recoverable invalid images in tool outputs still replace the offending image with `"Invalid image"` and retry.
- Unrecoverable invalid images now emit the `bad_request` lifecycle/error event and finish the current turn result without re-raising the sampler error.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/tasks/regular.rs#run:37`
  - `function:codex-rs/core/src/tasks/mod.rs#on_task_finished:570`
- Rust source confirmed:
  - `CodexErr::InvalidImageRequest` first attempts `replace_last_turn_images("Invalid image")` and continues the sampling loop when replacement succeeds.
  - If replacement fails, Rust emits `CodexErrorInfo::BadRequest` and an error event with the user-facing invalid-image message, then breaks the turn loop instead of propagating the error.
  - The regular task wrapper emits the normal terminal turn lifecycle after `run_turn` returns.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Initial sampling and follow-up sampling now return a completed `UserTurnSamplingResult` after unrecoverable invalid-image recovery has emitted the bad-request event.
  - Follow-up invalid-image termination preserves accumulated response/tool/stream state, matching the Rust loop's "break with current last agent message" behavior.
- `tests/test_core_turn_runtime.py`
  - Updated invalid user image coverage to expect event emission plus completed result instead of a raised `CodexErr`.
  - Added follow-up coverage proving accumulated assistant output is preserved when a later retry hits an unrecoverable invalid-image error.
- `tests/test_core_session_runtime.py`
  - Updated the in-memory session integration expectation to match the same bad-request event plus completed result behavior.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py tests\test_core_turn_runtime.py tests\test_core_session_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_replaces_invalid_tool_output_image_and_retries tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_invalid_user_image_emits_bad_request_and_completes tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_followup_invalid_user_image_preserves_accumulated_result`
  - 3 tests passed.
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_invalid_user_image_records_bad_request_lifecycle`
  - 1 test passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 50 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`
  - 605 tests passed, 1 skipped.
