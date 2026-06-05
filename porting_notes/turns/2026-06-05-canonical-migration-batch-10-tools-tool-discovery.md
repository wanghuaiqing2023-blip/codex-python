# 2026-06-05 canonical migration batch 10: tools/tool_discovery

## Scope

Move discoverable tool metadata and request-plugin-install list-entry helpers from the old `pycodex.core` coordinate to `pycodex.tools`.

## Rust source coordinates

- `codex/codex-rs/tools/src/tool_discovery.rs`
- `codex/codex-rs/app-server-protocol/src/protocol/v2/apps.rs` for `AppInfo`

## Python target coordinates

- `pycodex/tools/tool_discovery.py`
- `pycodex/app_server_protocol/apps.py`

## Old Python coordinate

- `pycodex/core/tool_discovery.py`

## Dependency correction

`ToolSearchSourceInfo` is sourced from the Rust tools crate, so Python core tool-search entry code now imports it from `pycodex.tools.tool_discovery` instead of defining a second core-local copy.

## Validation before deleting old coordinate

- Focused tests: 133 passed.
- Import smoke for `pycodex.app_server_protocol.apps`, `pycodex.tools.tool_discovery`, and dependent core modules: passed.

## Old coordinate deletion

Deleted `pycodex/core/tool_discovery.py` after focused validation.

## Validation after deleting old coordinate

- Focused tests: 133 passed.
- Import smoke after deletion: passed.
- Strict residual old-coordinate check: no matches for `pycodex.core.tool_discovery`.
