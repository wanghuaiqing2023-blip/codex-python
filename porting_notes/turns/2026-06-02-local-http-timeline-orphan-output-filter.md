# 2026-06-02 local HTTP timeline orphan-output filter

## Upstream slice

- Continued the core `exec -> Responses history -> user-visible JSON timeline` path.
- Rust `codex-rs/core/src/context_manager/normalize.rs` removes orphan `FunctionCallOutput` and `CustomToolCallOutput` items when no matching call exists, while preserving special empty-call-id function outputs used for model-visible tool errors.

## Python change

- Updated `pycodex/exec/local_runtime.py` so local HTTP timeline rendering drops leftover orphan `function_call_output` and `custom_tool_call_output` items with non-empty call ids.
- Empty-call-id function outputs are preserved, keeping existing malformed-tool/error recovery visible.
- MCP outputs were left unchanged because the active implementation target avoids expanding MCP behavior unless core runtime requires it.

## Tests

- Added `test_local_http_tool_timeline_drops_orphan_function_and_custom_outputs`.
- The test verifies orphan function/custom outputs disappear from the JSON timeline while an empty-call-id error output remains visible.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_tool_timeline_drops_orphan_function_and_custom_outputs tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_removes_orphan_tool_outputs_from_raw_payload`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_core_compact_remote.CompactRemoteTests.test_remove_orphan_outputs_keeps_only_outputs_with_matching_calls tests.test_core_compact_remote.CompactRemoteTests.test_normalize_call_outputs_inserts_missing_outputs_then_removes_orphans`

## Known gaps

- Tool-search output timeline rendering remains separate from this function/custom output filter because local HTTP timeline currently does not model tool-search calls as command execution events.
