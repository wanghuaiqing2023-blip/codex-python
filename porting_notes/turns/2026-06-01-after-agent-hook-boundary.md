## 2026-06-01 After-Agent Hook Completion Boundary

### Scope

- Added a lightweight Python shim for Rust's legacy `after_agent` hook boundary.
- This preserves the user-visible completion behavior without porting the full hook process runtime.
- If the session-like hook callback reports an abort, Python emits the Rust-shaped error message and completes the turn with `last_agent_message=None`.

### Upstream Graph/Source Slice

- Graph/source nodes used:
  - `function:codex-rs/core/src/session/turn.rs#run_turn:133`
  - `function:codex-rs/core/src/hook_runtime.rs#run_legacy_after_agent_hook:430`
  - `function:codex-rs/core/src/event_mapping.rs#parse_turn_item:136`
- Rust source confirmed:
  - `run_turn` calls `run_legacy_after_agent_hook` after stop hooks and before returning a successful final assistant message.
  - FailedContinue hook results log and allow completion.
  - FailedAbort hook results emit an error event with `after_agent hook '{hook_name}' failed and aborted turn completion: {error}` and make `run_turn` return `None`.
  - The task wrapper still emits the terminal `TurnComplete`, but with no `last_agent_message`.

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added optional session/turn-context callback discovery for `run_legacy_after_agent_hook`, `run_after_agent_hook`, or `after_agent_hook`.
  - Extracts prompt-visible user input messages from the current request input and passes them with the current last assistant message.
  - Supports bool, mapping, or object-like callback outcomes for abort decisions.
  - Emits the Rust error text and returns a completed result with `last_agent_message=None` on abort.
  - Preserves stop-hook continuation ordering so after-agent hooks only run once the model no longer needs follow-up.
- `tests/test_core_turn_runtime.py`
  - Added coverage for an after-agent abort: callback inputs, error event text, retained response item, cleared result last message, and `task_complete(last_agent_message=None)`.

### Validation

- `python -m py_compile pycodex\core\turn_runtime.py tests\test_core_turn_runtime.py`
  - Passed.
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_after_agent_abort_emits_error_and_clears_last_message`
  - 1 test passed.
- `python -m unittest tests.test_core_turn_runtime`
  - 54 tests passed.
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_session tests.test_core_request_permissions_handler tests.test_core_session_runtime tests.test_core_turn_runtime tests.test_core_tool_runtimes tests.test_core_tool_router tests.test_core_http_transport tests.test_core_turn_sampler`
  - 610 tests passed, 1 skipped.
