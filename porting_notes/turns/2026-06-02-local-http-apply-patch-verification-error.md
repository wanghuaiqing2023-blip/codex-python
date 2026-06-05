# Local HTTP apply_patch verification error wording

## Source slice

- Followed the core tool handler path in `codex-rs/core/src/tools/handlers/apply_patch.rs`.
- Rust reports parse and verification failures as `apply_patch verification failed: <error>` so the model sees a specific repair signal.

## Python changes

- `_apply_local_http_apply_patch` now uses the Rust-style `apply_patch verification failed:` prefix for parse/verification failures.
- Runtime application failures still use the existing `apply_patch failed:` wording because those occur after verification.

## Validation

- `python -m py_compile pycodex\exec\local_runtime.py tests\test_exec_local_runtime.py`
- `python -m unittest tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_invalid_patch_returns_verification_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_missing_patch_returns_model_visible_error tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_apply_patch_tool_output_helper_applies_patch`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_apply_patch tests.test_core_http_transport tests.test_core_turn_runtime tests.test_core_spec_plan`
