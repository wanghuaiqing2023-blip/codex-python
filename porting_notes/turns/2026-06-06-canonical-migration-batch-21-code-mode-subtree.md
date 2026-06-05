# 2026-06-06 canonical migration batch 21: code-mode tool subtree

## Scope

- Move Python code-mode behavior out of the `pycodex/core` root and into the Rust-aligned tools subtree.
- This batch is coordinate-only: it does not split Python's large `code_mode` module into Rust-like internal files.

## Rust anchors

- `codex/codex-rs/core/src/tools/code_mode/mod.rs`
- `codex/codex-rs/core/src/tools/code_mode/execute_handler.rs`
- `codex/codex-rs/core/src/tools/code_mode/execute_spec.rs`
- `codex/codex-rs/core/src/tools/code_mode/wait_handler.rs`
- `codex/codex-rs/core/src/tools/code_mode/wait_spec.rs`
- `codex/codex-rs/core/src/tools/code_mode/response_adapter.rs`

## Python canonical coordinate

- `pycodex/core/tools/code_mode/__init__.py`

## Changes

- Moved `pycodex/core/code_mode.py` into `pycodex/core/tools/code_mode/__init__.py`.
- Updated production imports, the root `pycodex.core` facade, and focused tests from `pycodex.core.code_mode` to `pycodex.core.tools.code_mode`.
- Left the Python code-mode implementation consolidated in one package module for now.

## Validation

- Focused suite:
  - `tests/test_core_code_mode.py`
  - `tests/test_core_spec_plan.py`
  - `tests/test_core_tool_router.py`
  - `tests/test_core_tool_parallel.py`
  - `tests/test_core_turn_runtime.py`
- Result:
  - `349 passed`
- Import smoke:
  - `pycodex.core.tools.code_mode`
  - passed
- Old import residual check:
  - no matches for `pycodex.core.code_mode`

## Notes

- Future refinement can split the package into `execute_handler.py`, `execute_spec.py`, `wait_handler.py`, `wait_spec.py`, and `response_adapter.py` if the module becomes hard to maintain.
- For this pass, preserving behavior and deleting the old root coordinate was higher value than splitting a large working module.
