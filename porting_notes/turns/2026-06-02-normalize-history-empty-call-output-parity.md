# normalize history empty call output parity

## Upstream graph and source slice

- Graph node: `codex-rs/core/src/context_manager/normalize.rs#remove_orphan_outputs`
- Source: `codex/codex-rs/core/src/context_manager/normalize.rs`
- Mainline path: `session/turn.rs -> history.for_prompt -> normalize call outputs -> Responses input`

Rust removes `FunctionCallOutput` items unless their `call_id` matches a
`FunctionCall` or `LocalShellCall` in the same prompt history. Empty string
`call_id` values are not special-cased; they are retained only when a matching
call with the same empty id exists.

## Python changes

- `remove_orphan_outputs` now drops empty `function_call_output` items when no
  matching function/local-shell call exists.
- Updated compact-remote tests to cover both the orphan empty-id case and the
  matching empty-id case.

## Validation

- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py -k "remove_orphan_outputs or normalize_call_outputs or normalize_history_for_prompt"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py tests/test_core_turn_runtime.py -k "normalize_history or call_outputs or build_user_turn_request_normalizes_history_call_outputs_for_prompt"`
- `$env:PYTHONPATH='.'; uvx pytest tests/test_core_compact_remote.py`
