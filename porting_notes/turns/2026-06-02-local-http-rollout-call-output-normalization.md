# Local HTTP Rollout Call-Output Normalization

## Upstream graph slice

- Knowledge graph nodes:
  - `function:codex-rs/core/src/context_manager/normalize.rs#ensure_call_outputs_present`
  - `function:codex-rs/core/src/context_manager/history_tests.rs#normalize_adds_missing_output_for_local_shell_call_with_id:1265`
- Rust source read:
  - `codex/codex-rs/core/src/context_manager/normalize.rs`
  - `codex/codex-rs/core/src/session/turn.rs`

## Rust behavior confirmed

- Prompt history is normalized before model requests.
- Missing outputs are synthesized after client-side tool calls.
- `LocalShellCall` is paired with a `FunctionCallOutput`; when missing, Rust inserts an `aborted` output.
- Orphan outputs are removed unless their call id matches an existing function/custom/tool-search/local-shell call.

## Python changes

- `pycodex/exec/local_runtime.py`
  - Local HTTP rollout persistence now normalizes prompt-visible `ResponseItem` history with `normalize_call_outputs()` before serializing response payloads.
  - This covers local shell calls, function calls, custom tool calls, and client tool-search calls when persisted local rollouts are later resumed.
  - Non-protocol compatibility objects in tests or older call paths are preserved without normalization.

- `tests/test_exec_local_runtime.py`
  - Added coverage that a raw `local_shell_call` response gets a synthesized `function_call_output` with `aborted` before rollout serialization.
  - Kept existing tool-search interleaving coverage green.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_inserts_missing_output_for_local_shell_call tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_interleaves_multiple_client_tool_search_outputs tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_prefers_raw_response_items_for_persistence`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_resume_rollout_appends_to_existing_thread_file tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_rollout_inserts_missing_output_for_local_shell_call`
- `python -m unittest tests.test_exec_local_runtime`

## Follow-up debt

- This normalizes persisted local HTTP rollouts; the broader remote/app-server rollout paths still rely on their existing session/context normalization layers.
