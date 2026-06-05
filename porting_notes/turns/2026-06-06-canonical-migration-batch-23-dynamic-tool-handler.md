# 2026-06-06 canonical migration batch 23: dynamic tool handler

## Scope

- Move dynamic tool handler behavior into the Rust-aligned handler subtree.
- Keep behavior unchanged; this is a coordinate migration.

## Rust anchor

- `codex/codex-rs/core/src/tools/handlers/dynamic.rs`

## Python canonical coordinate

- `pycodex/core/tools/handlers/dynamic.py`

## Changes

- Moved `pycodex/core/dynamic_tool_handler.py` into `pycodex/core/tools/handlers/dynamic.py`.
- Updated `pycodex/core/tools/spec_plan.py`, the root `pycodex.core` facade, and focused tests to use the canonical coordinate.

## Validation

- Focused suite:
  - `tests/test_core_dynamic_tool_handler.py`
  - `tests/test_core_spec_plan.py`
  - `tests/test_core_tool_router.py`
  - `tests/test_core_tool_parallel.py`
  - `tests/test_protocol_mcp_dynamic_tools.py`
- Result:
  - `235 passed`
- Import smoke:
  - `pycodex.core.tools.handlers.dynamic`
  - passed
- Old import residual check:
  - no matches for `pycodex.core.dynamic_tool_handler`

## Notes

- This keeps dynamic tools on the core tool-dispatch path while avoiding any MCP/plugin behavior expansion.
