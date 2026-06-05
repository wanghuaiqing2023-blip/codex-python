# Session history tool output truncation

## Upstream graph and source slice

- Graph node: `function:codex-rs/core/src/context_manager/history.rs#record_items`
- Graph node: `function:codex-rs/core/src/context_manager/history.rs#truncate_function_output_payload`
- Graph node: `class:codex-rs/protocol/src/models.rs#FunctionCallOutputPayload`
- Source: `codex/codex-rs/core/src/session/mod.rs`
- Source: `codex/codex-rs/core/src/context_manager/history.rs`
- Source: `codex/codex-rs/core/src/session/turn_context.rs`

Rust `Session::record_conversation_items` persists and emits the raw response
items, but writes processed items into the in-memory history. The history
processing truncates `function_call_output` and `custom_tool_call_output`
payloads using the turn context truncation policy scaled by 1.2, preserving
payload success metadata.

## Python changes

- Added `truncate_function_output_payload` to `pycodex.core.tool_context` so
  text and structured tool-output payloads share the same truncation path.
- Added `truncation_policy` to `InMemoryTurnContext`, derived from
  `model_info.truncation_policy` with the existing 10,000-token fallback.
- Updated `InMemoryCodexSession.record_conversation_items` to keep
  `recorded_batches` raw while appending Rust-style truncated tool outputs to
  prompt history.
- Added coverage for both `function_call_output` and
  `custom_tool_call_output` history truncation.

## Validation

- `python -m unittest tests.test_core_session_runtime tests.test_core_tool_context`
- `python -m unittest tests.test_core_turn_runtime`
- `python -m unittest tests.test_core_session_runtime tests.test_core_tool_context tests.test_core_turn_runtime tests.test_core_tool_events`
