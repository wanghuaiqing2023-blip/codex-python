# bad tool_search follow-up history parity

## Upstream graph and source slice

- Graph node: `codex-rs/core/src/session/turn.rs#run_turn`
- Graph node: `codex-rs/core/src/stream_events_utils.rs#handle_output_item_done`
- Graph node: `codex-rs/core/src/context_manager/normalize.rs#ensure_call_outputs_present`
- Graph node: `codex-rs/core/src/context_manager/normalize.rs#remove_orphan_outputs`
- Source: `codex/codex-rs/core/src/stream_events_utils.rs`
- Source: `codex/codex-rs/core/src/tools/router.rs`
- Source: `codex/codex-rs/core/src/context_manager/normalize.rs`

Rust handles malformed client `tool_search_call` arguments as
`FunctionCallError::RespondToModel`, records a `function_call_output` with an
empty call id for the current turn, then normalizes the next prompt history.
During prompt normalization, the empty function-call output is removed as an
orphan while a missing `tool_search_output` is synthesized for the original
`tool_search_call`.

## Python changes

- Updated core turn-runtime coverage so malformed tool-search arguments remain
  visible in the turn result but do not survive as an empty-call-id
  `function_call_output` in the follow-up prompt.
- Added compact-history coverage for the same normalization shape:
  `tool_search_call + empty function_call_output` becomes
  `tool_search_call + synthesized tool_search_output`.

## Validation

- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_turn_runtime.py -k "bad_tool_search_arguments"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py -k "normalize_call_outputs or remove_orphan_outputs"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py tests/test_core_turn_runtime.py -k "normalize_call_outputs or remove_orphan_outputs or trim_function_call_history or tool_followup or tool_search_arguments or dispatches_and_records_tool_outputs or default_followups_continue_until_final_answer"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py tests/test_core_turn_runtime.py`
- `python -m py_compile pycodex/core/compact_remote.py tests/test_core_compact_remote.py tests/test_core_turn_runtime.py`
