# Context History Call Output Normalization

## Scope

- Continued the graph-guided core request path around retained history normalization before model request construction.
- Focused on preserving Rust Codex behavior for tool/call output pairing in conversation history.

## Upstream Graph/Source Slice

- Graph nodes used:
  - `file:codex-rs/core/src/context_manager/normalize.rs`
  - `function:codex-rs/core/src/context_manager/normalize.rs#ensure_call_outputs_present:14`
  - `function:codex-rs/core/src/context_manager/normalize.rs#remove_orphan_outputs:122`
  - `function:codex-rs/core/src/context_manager/normalize.rs#remove_corresponding_for:197`
  - `function:codex-rs/core/src/context_manager/normalize.rs#strip_images_when_unsupported:295`
- Rust source confirmed:
  - Missing `function_call`, `tool_search_call`, `custom_tool_call`, and `local_shell_call` outputs are synthesized immediately after the call item.
  - Function/custom/local-shell synthetic outputs use the user-visible text `aborted`.
  - Synthetic tool-search outputs use `status: completed`, `execution: client`, and an empty tool list.
  - Orphan outputs are dropped unless they still match a call; server-side tool-search outputs and tool-search outputs without a `call_id` are retained.
  - Rust `ContextManager::for_prompt()` applies this normalization immediately before prompt construction: first `ensure_call_outputs_present()`, then `remove_orphan_outputs()`, then image stripping when needed.
  - When the model lacks image input support, `InputImage` content in messages and function/custom tool outputs is replaced with `image content omitted because you do not support image input`, and image-generation call results are cleared.

## Python Changes

- `pycodex/core/compact_remote.py`
  - Added `ensure_call_outputs_present()`, `remove_orphan_outputs()`, and `normalize_call_outputs()`.
  - Added `strip_images_when_unsupported()` and `normalize_history_for_prompt()` for full current `ContextManager::for_prompt()` parity.
  - Kept the helpers pure and standard-library only, returning normalized tuples without mutating caller-owned history.
- `pycodex/core/turn_runtime.py`
  - Wired prompt-history normalization into both initial user-turn request construction and tool follow-up request construction.
- `pycodex/core/session_runtime.py`
  - Made the in-memory `History.for_prompt()` reflect the same prompt-history normalization for model-visible history snapshots.
- `pycodex/core/__init__.py`
  - Exported the normalization helpers.
- `tests/test_core_compact_remote.py`
  - Added focused coverage for synthetic output insertion, orphan-output retention/removal, insert-then-remove normalization order, unsupported-image stripping, supported-image preservation, and combined prompt-history normalization.
- `tests/test_core_turn_runtime.py`
  - Added request-path coverage proving missing call outputs are synthesized, orphan outputs are removed, and unsupported image content is omitted from model request input.

## Validation

- `python -m unittest tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils`
  - 142 tests passed.
- `python -m unittest tests.test_core_compact_remote tests.test_core_turn_runtime tests.test_core_turn_request tests.test_core_stream_events_utils`
  - 146 tests passed.
- `python -m unittest tests.test_core_compact_remote tests.test_core_turn_runtime tests.test_core_turn_request tests.test_protocol_models_content`
  - 73 tests passed.
- `python -m unittest tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils`
  - 167 tests passed.
- `python -m unittest tests.test_core_turn_request tests.test_core_turn_runtime tests.test_core_compact_remote tests.test_core_compact_remote_v2 tests.test_core_stream_events_utils tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 674 tests passed, 1 skipped.
- `python -m unittest tests.test_core_unified_exec tests.test_core_unified_exec_handler tests.test_core_tool_runtimes tests.test_core_tool_orchestrator tests.test_core_tool_events tests.test_exec_local_runtime tests.test_exec_session tests.test_exec_event_processor tests.test_exec_cli tests.test_exec_websocket`
  - 502 tests passed, 1 skipped.

## Follow-up Debt

- The Python history normalization is now wired into the in-memory/runtime request path. A future persistence-backed history object should delegate to the same `normalize_history_for_prompt()` helper to keep parity.
