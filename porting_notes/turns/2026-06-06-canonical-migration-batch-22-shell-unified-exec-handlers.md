# 2026-06-06 canonical migration batch 22: shell and unified-exec handlers

## Scope

- Move command-execution handler code into the Rust-aligned handler subtree.
- This batch targets the handler layer for shell and unified exec, not the underlying runtime implementation.

## Rust anchors

- `codex/codex-rs/core/src/tools/handlers/shell.rs`
- `codex/codex-rs/core/src/tools/handlers/shell_spec.rs`
- `codex/codex-rs/core/src/tools/handlers/unified_exec.rs`

## Python canonical coordinates

- `pycodex/core/tools/handlers/shell.py`
- `pycodex/core/tools/handlers/shell_spec.py`
- `pycodex/core/tools/handlers/unified_exec.py`

## Changes

- Moved `pycodex/core/shell_handler.py` into `pycodex/core/tools/handlers/shell.py`.
- Moved `pycodex/core/shell_spec.py` into `pycodex/core/tools/handlers/shell_spec.py`.
- Moved `pycodex/core/unified_exec_handler.py` into `pycodex/core/tools/handlers/unified_exec.py`.
- Updated production and focused test imports.
- Replaced eager re-exports in `pycodex/core/tools/handlers/__init__.py` with a light package initializer. This avoids importing the full router/memory/spec-plan stack when a single handler submodule is imported.

## Validation

- Focused suite:
  - `tests/test_core_shell_handler.py`
  - `tests/test_core_shell_spec.py`
  - `tests/test_core_unified_exec_handler.py`
  - `tests/test_core_spec_plan.py`
  - `tests/test_core_tool_runtimes.py`
  - `tests/test_core_exec_policy.py`
  - `tests/test_core_session_runtime.py`
  - `tests/test_core_tool_router.py`
- Result:
  - `354 passed`
  - `2 skipped`
- Import smoke:
  - `pycodex.core.tools.handlers.shell`
  - `pycodex.core.tools.handlers.shell_spec`
  - `pycodex.core.tools.handlers.unified_exec`
  - passed
- Old import residual check:
  - no matches for moved root module paths.

## Notes

- This batch keeps the `pycodex.core` facade intact while moving the real implementation coordinates under `core.tools.handlers`.
- The light `handlers/__init__.py` is intentional: package-level eager imports created a circular dependency through router and memory usage.
