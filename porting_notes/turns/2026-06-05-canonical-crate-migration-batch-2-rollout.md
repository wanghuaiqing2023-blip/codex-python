# Canonical crate migration batch 2: rollout

Date: 2026-06-05

## Summary

Moved the existing Python rollout persistence implementation from the legacy `pycodex/core/rollout.py` coordinate into the Rust-tree-aligned canonical package path `pycodex/rollout`.

## Canonical move

| Rust crate/module | Old Python path | New Python path | Result |
|---|---|---|---|
| `codex-rollout` (`codex/codex-rs/rollout`) | `pycodex/core/rollout.py` | `pycodex/rollout/__init__.py` | moved |

## Explicit non-moves

`pycodex/core/session_rollout_init_error.py` and `pycodex/core/thread_rollout_truncation.py` were not moved because their source anchors are Rust `core/src/session_rollout_init_error.rs` and `core/src/thread_rollout_truncation.rs`, not the `codex-rollout` crate.

## Import policy

Project and test imports were updated to use `pycodex.rollout`. The legacy `pycodex/core/rollout.py` file was deleted after canonical-path tests/import checks passed. No long-term compatibility shim was retained.

## Validation

- `python -m pytest tests/test_core_rollout.py tests/test_core_session_rollout_init_error.py -q`: 40 passed, 5 subtests passed.
- `python -m pytest tests/test_core_rollout.py -q`: 34 passed after lazy-import fix.
- Canonical import smoke passed before and after deleting the legacy file.
- Residual old-coordinate search for `pycodex.core.rollout` returned no matches.

## Fixes discovered during migration

- `pycodex/rollout/__init__.py` needed a lazy import of `is_user_turn_boundary` to avoid a top-level circular import through `pycodex.core`.