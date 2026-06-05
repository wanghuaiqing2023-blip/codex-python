# 2026-06-06 - canonical migration batch 27: unified_exec package coordinate

## Purpose

Move the existing Python unified-exec implementation out of the root-level `pycodex/core/unified_exec.py` file and into a Rust-aligned `pycodex/core/unified_exec/` package coordinate.

## Rust source anchors

- `codex/codex-rs/core/src/unified_exec/mod.rs`
- `codex/codex-rs/core/src/unified_exec/errors.rs`
- `codex/codex-rs/core/src/unified_exec/head_tail_buffer.rs`
- `codex/codex-rs/core/src/unified_exec/process.rs`
- `codex/codex-rs/core/src/unified_exec/process_manager.rs`
- `codex/codex-rs/core/src/unified_exec/process_state.rs`

## Python canonical target

- `pycodex/core/unified_exec/__init__.py`

## Moved from old path

- `pycodex/core/unified_exec.py`

## Result

The public import path remains `pycodex.core.unified_exec`, but it is now backed by a package initializer instead of a root-level file. This preserves behavior while aligning the coordinate with Rust's `core/src/unified_exec/` directory.

## Validation

- Package import smoke: passed.
- Old file absent and new package initializer present.
- Focused adjacent test command:
  - `python -m pytest tests/test_core_unified_exec.py tests/test_core_unified_exec_handler.py tests/test_core_exec.py tests/test_exec_local_runtime.py tests/test_core_session_runtime.py tests/test_core_turn_runtime.py tests/test_core_code_mode.py`
- Result: `540 passed, 2 skipped`.

## Scope note

This is a coordinate conversion only. The Python implementation is intentionally left in `__init__.py` for now to avoid behavior churn. A later, separate refactor can split it into `errors.py`, `head_tail_buffer.py`, `process.py`, `process_manager.py`, and `process_state.py` if that becomes useful.
