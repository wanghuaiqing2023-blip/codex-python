## 2026-06-01 Stop Hook Continuation Runtime Slice

### Scope

- Added the core turn-loop behavior for Stop hook continuation without porting the full hooks runtime.
- When a session-like object exposes `run_turn_stop_hook` or `run_stop_hook`, the Python runtime now calls it after a final model response and before completing the turn.
- If the hook outcome blocks with continuation fragments, the runtime records the generated hook prompt user message and performs another model sampling request.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/hook_runtime.rs#run_turn_stop_hooks:294`
  - `function:codex-rs/protocol/src/items.rs#build_hook_prompt_message:369`
- Rust source confirmed:
  - `run_turn` calls `run_turn_stop_hooks` only once the model no longer needs follow-up.
  - `should_block` plus a non-empty hook prompt records the prompt into conversation history, marks stop-hook continuation active, and continues the sampling loop.
  - `should_block` without a prompt emits the warning `"Stop hook requested continuation without a prompt; ignoring the block."`.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added a lightweight stop-hook callback shim for session-like runtimes.
  - Converts continuation fragments to the existing protocol `build_hook_prompt_message()` shape.
  - Preserves the Rust `stop_hook_active` flag across the continuation loop.
  - Emits the Rust warning event for block-without-prompt outcomes.
- `tests/test_core_turn_runtime.py`
  - Added coverage proving a stop-hook continuation prompt is recorded and causes a second model request.
  - Verifies the second hook invocation sees `stop_hook_active=True` and the updated last assistant message.
  - Added warning-path coverage for `should_block` without a generated hook prompt.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py tests\test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_stop_hook_continuation_prompts_followup tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_stop_hook_block_without_prompt_warns_and_finishes`
  - 2 tests passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 52 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`
  - 607 tests passed, 1 skipped.
