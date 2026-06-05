# Canonical crate migration batch 3: utils string and approval presets

Date: 2026-06-05

## Summary

Moved two existing Python utility implementations from legacy `pycodex/core/*` coordinates into Rust-tree-aligned canonical package paths under `pycodex/utils/*`.

## Canonical moves

| Rust crate | Old Python path | New Python path | Result |
|---|---|---|---|
| `codex-utils-string` | `pycodex/core/string_utils.py` | `pycodex/utils/string/__init__.py` | moved |
| `codex-utils-approval-presets` | `pycodex/core/approval_presets.py` | `pycodex/utils/approval_presets/__init__.py` | moved |

## Explicit non-move

`pycodex/core/paths.py` was not moved in this batch. Its source anchors are mixed: `codex-rs/utils/home-dir/src/lib.rs`, `codex-rs/state/src/lib.rs`, and `codex-rs/state/src/runtime.rs`. It should be split or mapped deliberately later instead of being forced into one `utils/*` target.

## Import policy

Project and test imports were updated to use canonical paths. The legacy core files were deleted after canonical-path tests/import checks passed. No long-term compatibility shims were retained.

## Validation

- `python -m pytest tests/test_core_string_utils.py tests/test_core_approval_presets.py -q`: 17 passed.
- Canonical import smoke passed before deleting legacy files.
- `python -m pytest tests/test_core_string_utils.py tests/test_core_approval_presets.py -q`: 17 passed after deleting legacy files.
- Post-delete canonical import smoke passed.
- Residual old-coordinate search for `pycodex.core.string_utils` and `pycodex.core.approval_presets` returned no matches.