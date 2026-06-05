# Local HTTP apply_patch verified file-change boundary

## Source slice

- Confirmed Rust behavior in `codex-rs/core/src/tools/handlers/apply_patch.rs`.
- Rust parses and verifies `apply_patch` input before constructing `ToolEmitter::apply_patch`.
- Parse errors, verification errors, invalid patch input, and non-patch input return model-visible tool errors without emitting a file-change item.

## Python changes

- `tool_timeline_items_from_local_http_exec_result` now emits `file_change` for `apply_patch` only when patch changes are known.
- Invalid or non-patch `apply_patch` tool calls keep their model-visible failed tool result, but no longer create misleading empty `file_change` timeline items.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_missing_patch_returns_model_visible_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_invalid_patch_returns_verification_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_requires_approval_before_write`
- `python -m unittest tests.test_exec_local_runtime tests.test_exec_event_processor`
- `python -m unittest tests.test_core_apply_patch tests.test_core_tool_events tests.test_core_turn_runtime tests.test_core_spec_plan`
