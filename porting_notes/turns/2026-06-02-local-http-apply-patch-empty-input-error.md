# Local HTTP apply_patch empty-input error

## Source slice

- Followed the same core tool dispatch slice through:
  - `codex-rs/core/src/tools/handlers/apply_patch.rs`
  - `codex-rs/core/src/tools/registry.rs`
- Rust `ApplyPatchHandler` returns model-visible errors instead of dropping malformed or non-patch `apply_patch` payloads.
- For non-patch input, Rust reports `apply_patch handler received non-apply_patch input`.

## Python changes

- `shell_tool_outputs_from_local_http_exec_result` now returns a failed tool output when an `apply_patch` tool call has no usable patch text.
- This prevents the local HTTP tool loop from silently ending without giving the model a tool result.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_missing_patch_returns_model_visible_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_follows_up_after_unknown_tool_error`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_stream_events_utils tests.test_core_spec_plan`

## Deferred

- Detailed Rust wording for every parse/verification variant remains a follow-up. This slice only fixes the no-output failure for empty or missing patch text.
