# 2026-06-06 canonical migration batch 17: goal and plugin-install handlers

## Scope

- Continue relocating existing Python implementation into Rust-tree-aligned coordinates.
- Keep old root handler files from becoming long-lived shims.

## Rust anchors

- `codex/codex-rs/core/src/tools/handlers/goal.rs`
- `codex/codex-rs/core/src/tools/handlers/goal_spec.rs`
- `codex/codex-rs/core/src/tools/handlers/goal/create_goal.rs`
- `codex/codex-rs/core/src/tools/handlers/goal/get_goal.rs`
- `codex/codex-rs/core/src/tools/handlers/goal/update_goal.rs`
- `codex/codex-rs/core/src/tools/handlers/request_plugin_install.rs`
- `codex/codex-rs/core/src/tools/handlers/request_plugin_install_spec.rs`
- `codex/codex-rs/core/src/tools/handlers/list_available_plugins_to_install.rs`
- `codex/codex-rs/core/src/tools/handlers/list_available_plugins_to_install_spec.rs`

## Python canonical coordinates

- `pycodex/core/tools/handlers/goal/__init__.py`
- `pycodex/core/tools/handlers/request_plugin_install.py`

## Changes

- Moved `pycodex/core/goal_handler.py` into the canonical handler package as `pycodex/core/tools/handlers/goal/__init__.py`.
- Moved `pycodex/core/request_plugin_install.py` into `pycodex/core/tools/handlers/request_plugin_install.py`.
- Updated `pycodex/core/spec_plan.py`, `pycodex/core/connectors.py`, `pycodex/core/mcp_tool_exposure.py`, `pycodex/core/__init__.py`, and focused tests to import from the new coordinates.
- Extended `pycodex/core/tools/handlers/__init__.py` so the handler package exposes the migrated goal and plugin-install symbols.

## Validation

- Focused test command:
  - `python -m pytest tests/test_core_goal_handler.py tests/test_core_request_plugin_install.py tests/test_core_spec_plan.py tests/test_core_mcp_tool_exposure.py tests/test_core_connectors.py`
- Result:
  - `84 passed`
- Old import residual check:
  - no matches for `pycodex.core.goal_handler`
  - no matches for `pycodex.core.request_plugin_install`

## Notes

- `pycodex.core` remains a public facade that re-exports many symbols, but it now imports these handlers from canonical coordinates.
- The Python plugin-install handler still combines request-plugin-install and list-available-plugin-install behavior in one file. That is acceptable for this batch because the Rust anchors are tightly coupled and the current Python behavior was already implemented as one shared handler suite.
