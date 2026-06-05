# Canonical migration batch 15: simple core tool handlers

## Summary

Moved four simple core tool handlers from top-level `pycodex/core` into the canonical `pycodex/core/tools/handlers` package.

## Rust anchors and Python coordinates

| Rust anchor | Python coordinate |
|---|---|
| `codex/codex-rs/core/src/tools/handlers/plan.rs` | `pycodex/core/tools/handlers/plan.py` |
| `codex/codex-rs/core/src/tools/handlers/request_user_input.rs` | `pycodex/core/tools/handlers/request_user_input.py` |
| `codex/codex-rs/core/src/tools/handlers/request_permissions.rs` | `pycodex/core/tools/handlers/request_permissions.py` |
| `codex/codex-rs/core/src/tools/handlers/test_sync.rs` | `pycodex/core/tools/handlers/test_sync.py` |

## Deleted old coordinates

- `pycodex/core/plan_handler.py`
- `pycodex/core/request_user_input_handler.py`
- `pycodex/core/request_permissions_handler.py`
- `pycodex/core/test_sync_handler.py`

## Import policy

- Use `pycodex.core.tools.handlers.plan` for update-plan behavior.
- Use `pycodex.core.tools.handlers.request_user_input` for request-user-input behavior.
- Use `pycodex.core.tools.handlers.request_permissions` for request-permissions behavior.
- Use `pycodex.core.tools.handlers.test_sync` for internal test synchronization behavior.
- Root `pycodex.core` no longer exports these moved handler symbols.

## Validation

- Focused validation before deletion: `260 passed`, `1 skipped`
- Focused validation after deletion: `260 passed`, `1 skipped`
- Old import residual check: no matches for the four old handler module paths or moved root-facade imports.

## Notes

This batch intentionally excludes more complex handlers such as MCP, shell, unified exec, dynamic tools, view image, request plugin install, and multi-agent handlers. Those should be migrated in smaller follow-up batches because they have deeper runtime dependencies.
