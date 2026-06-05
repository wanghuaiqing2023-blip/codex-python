# Canonical crate migration batch 1

Date: 2026-06-05

## Summary

Moved the first low-risk set of existing Python implementations from legacy `pycodex/core/*` coordinates into Rust-tree-aligned canonical package paths.

## Canonical moves

| Rust crate | Old Python path | New Python path | Result |
|---|---|---|---|
| `codex-features` | `pycodex/core/features.py` | `pycodex/features/__init__.py` | moved |
| `codex-features` managed behavior | `pycodex/core/managed_features.py` | `pycodex/features/managed.py` | moved |
| `codex-git-utils` | `pycodex/core/git_info.py` | `pycodex/git_utils/__init__.py` | moved |
| `codex-network-proxy` helper surface | `pycodex/core/network_proxy_loader.py` | `pycodex/network_proxy/__init__.py` | moved |

## Import policy

Project and test imports were updated to use canonical paths. The legacy core files were deleted after canonical-path tests/import checks passed. No long-term compatibility shims were retained for this batch.

## Validation

- `python -m pytest tests/test_core_managed_features.py tests/test_core_network_proxy_loader.py -q`: 22 passed.
- `python -m pytest tests/test_core_network_proxy_loader.py -q`: 9 passed after lazy-import fix.
- Canonical import smoke passed after deleting legacy files.
- Residual old-coordinate search for the four moved modules returned no matches.

## Fixes discovered during migration

- `pycodex/network_proxy/__init__.py` needed a lazy import of `Decision` to avoid a top-level circular import through `pycodex.core`.
- CLI feature command imports were restored to `pycodex.cli.features`; only core feature-flag types now come from `pycodex.features`.