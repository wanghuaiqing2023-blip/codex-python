# Tool Output Code-Mode Default

## Source slice

- Graph query identified `codex-rs/core/src/tools/context.rs` and `codex-rs/core/src/tools/router.rs` as the next output/result boundary on the core tool-dispatch path.
- Authoritative Rust behavior was confirmed in:
  - `codex/codex-rs/tools/src/tool_output.rs`
  - `codex/codex-rs/core/src/tools/context.rs`

## Confirmed Rust behavior

- `ToolOutput::code_mode_result` defaults to `response_input_to_code_mode_result(self.to_response_item("", payload))`.
- Function/custom tool outputs without a custom code-mode override expose the model-facing output body as the code-mode result.
- Content-item outputs are reduced to non-empty text items and image URLs joined with newlines.
- Tool-search outputs expose the tools array.
- `AbortedToolOutput` does not override `code_mode_result`, so aborted results use the default model-facing text instead of a custom object.
- `PostToolUseFeedbackOutput` delegates code-mode results to the original tool output, preserving original code-mode semantics while replacing only model-visible output.

## Python change

- Added `response_input_to_code_mode_result` in `pycodex/core/tool_context.py`.
- Updated `ToolCallResult.code_mode_result` in `pycodex/core/tool_parallel.py` to use the Rust default conversion when a result object does not provide a custom `code_mode_result`.
- Removed the non-Rust custom aborted code-mode object, so aborted results now fall back to their model-visible output text.
- Updated feedback-wrapper coverage so function outputs without a custom code-mode method still preserve their original response body under post-hook feedback.

## Validation

- `python -m py_compile pycodex/core/tool_context.py pycodex/core/tool_parallel.py tests/test_core_tool_context.py tests/test_core_tool_parallel.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_context.py tests/test_core_tool_parallel.py -q`
  - `166 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_router.py tests/test_core_turn_runtime.py -q`
  - `124 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_unified_exec_handler.py tests/test_core_tool_registry.py -q`
  - `57 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

## Deferred

- No extension/runtime expansion was taken. This only aligns the shared output conversion contract used by the core tool-dispatch and code-mode result path.
