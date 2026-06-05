# Tool Dispatch Trace Mapping Context Compatibility

## Graph slice

- `codex/codex-rs/core/src/tools/tool_dispatch_trace.rs#start`
- `codex/codex-rs/core/src/tools/router.rs#dispatch_any` (via trace start/complete lifecycle)
- `codex/codex-rs/core/src/tools/tool_dispatch_trace.rs#ToolDispatchTrace`

This slice is on the common tool execution path after a tool invocation is validated and before final result reporting.

## Rust behavior confirmed

- Trace startup goes through `start_tool_dispatch_trace` on the provided trace context.
- The trace context reports completion/failure through recorder callbacks; if tracing is unavailable, dispatch should still proceed without side effects.
- Enabled state is read from the trace context.

## Python changes

- `pycodex/core/tool_dispatch_trace.py`
  - Added mapping-safe access for trace context members in `ToolDispatchTrace.start`, `record_completed`, `record_failed`, and enabled checks.
  - `start_tool_dispatch_trace`, `record_completed`, and `record_failed` now work for both attribute-style contexts and `dict`/mapping-style contexts.
  - `is_enabled` now reads `is_enabled` from mappings as well as objects, with direct bool contexts treated as explicit enabled state.
- `tests/test_core_tool_dispatch_trace.py`
  - Added regression coverage for mapping trace context startup/completion/failure and disabled-mapping behavior.

## Validation

- `python -m pytest -q tests/test_core_tool_dispatch_trace.py tests/test_core_tool_router.py`
  - Result: 68 passed

## Deferred

- Keep this behavior as a focused compatibility shim for now; deeper trace context alternatives can be revisited once app-server/rollout transport path is in scope.
