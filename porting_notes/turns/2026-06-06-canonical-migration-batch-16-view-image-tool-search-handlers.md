# Canonical migration batch 16: view-image and tool-search handlers

## Summary

Moved the view-image and tool-search handlers from top-level `pycodex/core` into the canonical `pycodex/core/tools/handlers` package.

## Rust anchors and Python coordinates

| Rust anchor | Python coordinate |
|---|---|
| `codex/codex-rs/core/src/tools/handlers/view_image.rs` | `pycodex/core/tools/handlers/view_image.py` |
| `codex/codex-rs/core/src/tools/handlers/tool_search.rs` | `pycodex/core/tools/handlers/tool_search.py` |

## Deleted old coordinates

- `pycodex/core/view_image_handler.py`
- `pycodex/core/tool_search_handler.py`

## Import policy

- Use `pycodex.core.tools.handlers.view_image` for view-image handler behavior.
- Use `pycodex.core.tools.handlers.tool_search` for tool-search handler behavior.
- `ToolSearchOutput` remains in `pycodex.core.tool_context`, matching its role as a tool output context type rather than a handler implementation.
- Root `pycodex.core` no longer exports these moved handler symbols.

## Validation

- Focused validation before deletion: `304 passed`
- Focused validation after deletion: `304 passed`
- Old import residual check: no matches for the two old handler module paths or moved root-facade imports.

## Notes

This batch intentionally keeps deeper handler families for later: MCP handlers, shell/unified exec handlers, dynamic tool handlers, request-plugin-install, and multi-agent handlers all have broader runtime dependencies and should be migrated in smaller slices.
