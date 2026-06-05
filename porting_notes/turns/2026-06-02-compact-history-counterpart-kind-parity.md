# compact history counterpart kind parity

## Upstream graph and source slice

- Graph node: `codex-rs/core/src/context_manager/history.rs#for_prompt`
- Graph node: `codex-rs/core/src/context_manager/normalize.rs#remove_corresponding_for`
- Source: `codex/codex-rs/core/src/context_manager/normalize.rs`
- Source: `codex/codex-rs/core/src/compact_remote.rs`

Rust removes the corresponding call/output pair by response-item kind when
trimming generated tail history. A `ToolSearchOutput` only removes a
`ToolSearchCall` with the same call id; a `FunctionCallOutput` only removes a
`FunctionCall` or `LocalShellCall`; a `CustomToolCallOutput` only removes a
`CustomToolCall`.

## Python changes

- `_remove_corresponding_for` now uses Rust's kind-specific counterpart mapping
  instead of a broad shared set of call/output types.
- Added coverage for the same-call-id mixed-kind case so trimming a
  `tool_search_output` cannot delete an unrelated `function_call`.
- This note also includes the preceding empty-call-id parity fix in
  `remove_orphan_outputs`, where empty `function_call_output` values are no
  longer retained without a matching call.

## Validation

- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py -k "trim_function_call_history or remove_orphan_outputs or normalize_call_outputs"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py tests/test_core_turn_runtime.py -k "compact_remote or normalize_history or call_outputs or build_user_turn_request_normalizes_history_call_outputs_for_prompt"`
- `python -m py_compile pycodex/core/compact_remote.py tests/test_core_compact_remote.py`
