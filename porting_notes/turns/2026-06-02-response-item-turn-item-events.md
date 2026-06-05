# Response item turn item events

## Upstream slice

- Graph-guided target: core `exec -> context -> model request -> response handling -> final answer` path.
- Rust source confirmed in `codex/codex-rs/core/src/session/mod.rs`:
  - `Session::record_response_item_and_emit_turn_item` records the response item into conversation history.
  - It then calls `parse_turn_item`.
  - If parsing succeeds, it emits `TurnItemStarted` and `TurnItemCompleted`.

## Python port

- Added `InMemoryCodexSession.record_response_item_and_emit_turn_item`.
- Reused `pycodex.core.event_mapping.parse_turn_item` instead of duplicating turn-item mapping logic.
- Updated `pycodex.core.turn_runtime` so non-stream sampler response items use the session recorder when available.
- Kept stream-only response handling unchanged to avoid duplicate item lifecycle events on paths that already emit stream item events.

## Validation

- `python -m py_compile pycodex\core\session_runtime.py pycodex\core\turn_runtime.py`
- `python -m unittest tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_emits_turn_lifecycle_events tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_record_response_item_emits_turn_item_events tests.test_core_session_runtime.SessionRuntimeTests.test_in_memory_session_record_user_prompt_emits_turn_item_events`
- `python -m unittest tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_returns_streamed_last_agent_message tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_default_followups_continue_until_final_answer tests.test_core_turn_runtime.TurnRuntimeTests.test_run_user_turn_sampling_dispatches_stream_only_tool_call`
- `python -m unittest tests.test_local_http_core_smoke_suite`

## Known gaps

- This slice only covers the in-memory/core runtime path.
- Richer persistence and app-server protocol parity remain deferred unless the core CLI path needs a compatibility shim.
