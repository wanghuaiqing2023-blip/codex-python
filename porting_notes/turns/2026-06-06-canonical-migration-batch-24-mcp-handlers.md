# 2026-06-06 canonical migration batch 24: MCP handlers

## Scope

- Move MCP handler modules into the Rust-aligned handler subtree.
- Preserve existing MCP shim behavior without expanding MCP implementation scope.

## Rust anchors

- `codex/codex-rs/core/src/tools/handlers/mcp.rs`
- `codex/codex-rs/core/src/tools/handlers/mcp_resource.rs`
- `codex/codex-rs/core/src/tools/handlers/mcp_resource_spec.rs`

## Python canonical coordinates

- `pycodex/core/tools/handlers/mcp.py`
- `pycodex/core/tools/handlers/mcp_resource.py`

## Changes

- Moved `pycodex/core/mcp_tool_handler.py` into `pycodex/core/tools/handlers/mcp.py`.
- Moved `pycodex/core/mcp_resource_handler.py` into `pycodex/core/tools/handlers/mcp_resource.py`.
- Updated production and focused test imports.

## Validation

- Focused suite:
  - `tests/test_core_mcp_tool_handler.py`
  - `tests/test_core_mcp_resource_handler.py`
  - `tests/test_core_mcp_tool_exposure.py`
  - `tests/test_core_connectors.py`
  - `tests/test_core_spec_plan.py`
  - `tests/test_core_tool_router.py`
  - `tests/test_protocol_mcp_dynamic_tools.py`
- Result:
  - `151 passed`
- Import smoke:
  - `pycodex.core.tools.handlers.mcp`
  - `pycodex.core.tools.handlers.mcp_resource`
  - passed
- Old import residual check:
  - no matches for `pycodex.core.mcp_tool_handler`
  - no matches for `pycodex.core.mcp_resource_handler`

## Notes

- MCP remains outside the active deep-implementation target.
- This batch only preserves existing compatibility behavior while aligning module coordinates.
