# view_image argument error parity

## Upstream graph and source slice

- Graph node: `class:codex-rs/core/src/tools/handlers/view_image.rs#ViewImageHandler`
- Source: `codex/codex-rs/core/src/tools/handlers/view_image.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/mod.rs`

Rust parses `view_image` function arguments with `parse_arguments`, so malformed
JSON is returned to the model as `failed to parse function arguments: ...`.
Semantic `detail` validation happens after parsing and keeps the dedicated
`view_image.detail only supports ...` message.

## Python changes

- `parse_view_image_arguments` now wraps JSON decode failures with
  `failed to parse function arguments: ...`.
- Invalid `detail` values still return the Rust-style dedicated detail message.
- Added core handler coverage for malformed JSON and missing required `path`.

## Validation

- `python -m py_compile pycodex\core\view_image_handler.py tests\test_core_view_image_handler.py`
- `python -m unittest tests.test_core_view_image_handler tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_view_image_tool_loop_returns_image_output`
- `python -m unittest tests.test_exec_local_runtime`
- `python -m unittest tests.test_core_view_image_handler tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
