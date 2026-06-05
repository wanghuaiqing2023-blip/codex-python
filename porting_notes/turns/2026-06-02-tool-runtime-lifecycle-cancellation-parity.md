# tool runtime lifecycle cancellation parity

## Upstream graph and source slice

- Graph path focus: `exec -> tool dispatch -> response item/final answer`
- Source: `codex/codex-rs/core/src/tools/parallel.rs`
- Source: `codex/codex-rs/core/src/tools/context.rs`

Rust `ToolCallRuntime::handle_tool_call_with_source` preserves a few visible
runtime boundaries that matter for common tool execution:

- Aborted tool outputs still provide code-mode-visible `{text, success:false}`
  result data.
- Runtime cancellation notifications keep the active turn lifecycle stores and
  source metadata.
- For tools that wait for runtime cancellation, cancellation owns the terminal
  outcome; runtime cleanup may finish, but the model-visible result remains an
  aborted response unless the tool had already claimed a terminal outcome.
- Post-tool-use hook type failures happen after the handler ran, so lifecycle
  finish is reported as `failed(handler_executed=true)`. The top-level runtime
  exposes these as fatal user-visible errors, while lower-level dispatch tests
  still see the original type-error shape.

## Python changes

- Added `AbortedToolOutput.code_mode_result()` with `{text, success:false}`.
- Added async `lifecycle_store_context()` so runtime-driven router dispatch can
  preserve `session_store`, `thread_store`, `turn_store`, and `turn_id` for
  lifecycle notifications issued inside custom router paths.
- Tightened waiting-runtime-cancellation handling so cleanup success is
  discarded after cancellation ownership, matching Rust's aborted response.
- Introduced a post-hook-specific TypeError boundary so direct dispatch keeps
  TypeError semantics while `ToolCallRuntime.handle_tool_call()` turns those
  post-handler failures into `RuntimeError`.
- Updated tool parallel tests to use `SearchToolCallParams` for tool-search
  payloads and to patch a private monotonic clock instead of the global stdlib
  `time.monotonic` used by asyncio.

## Validation

- `python -m py_compile pycodex/core/tool_context.py pycodex/core/tool_lifecycle.py pycodex/core/tool_parallel.py pycodex/core/tool_router.py tests/test_core_tool_parallel.py`
- `uvx pytest tests/test_core_tool_parallel.py -q`
- `uvx pytest tests/test_core_tool_context.py tests/test_core_tool_router.py tests/test_core_tool_parallel.py tests/test_core_turn_runtime.py -q`
