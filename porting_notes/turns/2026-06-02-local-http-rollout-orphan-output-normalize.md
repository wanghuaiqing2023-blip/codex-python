# 2026-06-02 local HTTP rollout orphan-output normalize

## Upstream slice

- Continued the graph-selected `exec -> Responses history -> rollout/resume normalization` path.
- Confirmed Rust orphan-output behavior in `codex/codex-rs/core/src/context_manager/normalize.rs`.
- Python already has the matching core implementation in `pycodex/core/compact_remote.py` via `remove_orphan_outputs()` and `normalize_call_outputs()`.

## Python change

- Added a local HTTP rollout regression test showing raw Responses payloads are normalized before becoming prompt-visible rollout items.
- The test verifies orphan `function_call_output`, `custom_tool_call_output`, and client `tool_search_output` items are dropped, while server `tool_search_output`, unkeyed `tool_search_output`, and the assistant message remain.

## Validation

- `python -m py_compile tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_removes_orphan_tool_outputs_from_raw_payload tests.test_core_compact_remote.CompactRemoteTests.test_remove_orphan_outputs_keeps_only_outputs_with_matching_calls tests.test_core_compact_remote.CompactRemoteTests.test_normalize_call_outputs_inserts_missing_outputs_then_removes_orphans`
- `python -m unittest tests.test_cli_local_http_smoke_suite`

## Known gaps

- This turn strengthened coverage for existing normalize behavior. It did not change timeline rendering for orphan-only outputs, which still remains a separate user-visible rendering decision.
