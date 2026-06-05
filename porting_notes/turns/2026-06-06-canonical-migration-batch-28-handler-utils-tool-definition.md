# 2026-06-06 - canonical migration batch 28: handler utils and tools crate tool definition

## Purpose

Continue the high-risk-candidate cleanup by moving two clear boundary modules into Rust-aligned coordinates without changing behavior.

## Rust source anchors

- `codex/codex-rs/core/src/tools/handlers/mod.rs`
- `codex/codex-rs/tools/src/tool_definition.rs`

## Python canonical targets

- `pycodex/core/tools/handlers/utils.py`
- `pycodex/tools/tool_definition.py`

## Moved from old paths

- `pycodex/core/handler_utils.py`
- `pycodex/core/tool_definition.py`

## Result

`handler_utils.py` now lives with the core tool handlers it supports. `ToolDefinition` now lives under `pycodex/tools/`, matching the upstream Rust `tools` crate rather than the `core` crate. The root-level `pycodex.core.ToolDefinition` re-export remains available, but the old root-level module file is gone.

## Validation

- Residual old import search across `pycodex/` and `tests/`: clean.
- Canonical module import smoke: passed.
- Focused adjacent test command:
  - `python -m pytest tests/test_core_handler_utils.py tests/test_core_tool_definition.py tests/test_core_apply_patch.py tests/test_core_request_permissions_handler.py tests/test_core_unified_exec_handler.py tests/test_core_session_runtime.py tests/test_exec_local_runtime.py tests/test_core_tool_registry.py tests/test_core_spec_plan.py tests/test_core_code_mode.py`
- Result: `514 passed, 3 skipped`.

## Scope note

This batch only moves coordinates and rewrites imports. It does not attempt to split the large handler helper module further.
