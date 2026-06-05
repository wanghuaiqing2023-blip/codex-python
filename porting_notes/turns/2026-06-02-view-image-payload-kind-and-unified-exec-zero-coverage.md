# view_image payload kind and unified exec zero coverage

## Upstream graph and source slice

- Graph node: `class:codex-rs/core/src/tools/handlers/view_image.rs#ViewImageHandler`
- Graph node: `class:codex-rs/core/src/tools/handlers/unified_exec.rs#ExecCommandArgs`
- Graph node: `class:codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs#WriteStdinArgs`
- Source: `codex/codex-rs/core/src/tools/handlers/view_image.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/unified_exec.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`

Rust `ViewImageHandler::matches_kind` accepts only function payloads. The
Python core handler had allowed `tool_search` payloads even though `handle`
would reject them later.

Rust also parses `max_output_tokens` as `Option<usize>` for unified
`exec_command` and `write_stdin`, so a value of `0` is preserved. The local HTTP
runtime already gained behavioral coverage; this note adds core-handler coverage
for the same contract.

## Python changes

- `ViewImageHandler.matches_kind` now returns true only for function payloads.
- Added core view_image coverage for rejecting `tool_search` payload kind.
- Added core unified exec coverage proving `max_output_tokens=0` is preserved
  by both `ExecCommandArgs` and `WriteStdinArgs`.

## Validation

- `python -m py_compile pycodex\core\view_image_handler.py tests\test_core_view_image_handler.py`
- `python -m py_compile tests\test_core_unified_exec_handler.py`
- `python -m unittest tests.test_core_view_image_handler tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_view_image_tool_loop_returns_image_output`
- `python -m unittest tests.test_core_unified_exec_handler.CoreUnifiedExecHandlerTests.test_unified_exec_preserves_zero_max_output_tokens tests.test_core_unified_exec_handler.CoreUnifiedExecHandlerTests.test_unified_exec_numeric_bounds_match_rust_deserialization`
- `python -m unittest tests.test_core_view_image_handler tests.test_core_unified_exec_handler tests.test_core_turn_runtime tests.test_core_tool_events tests.test_core_apply_patch tests.test_core_spec_plan`
- `python -m unittest tests.test_exec_local_runtime`
