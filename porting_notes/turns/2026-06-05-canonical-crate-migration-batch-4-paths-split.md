# Canonical crate migration batch 4: split core paths

Date: 2026-06-05

## Summary

Split the mixed-source legacy `pycodex/core/paths.py` module into two Rust-tree-aligned canonical package paths.

## Canonical split

| Rust source | Old Python path | New Python path | Result |
|---|---|---|---|
| `codex-utils-home-dir` (`codex/codex-rs/utils/home-dir`) | `pycodex/core/paths.py` | `pycodex/utils/home_dir/__init__.py` | moved/split |
| `codex-state` runtime path helpers (`codex/codex-rs/state`) | `pycodex/core/paths.py` | `pycodex/state/__init__.py` | moved/split |

## Import policy

Production and test imports now use canonical paths:

- `pycodex.utils.home_dir.find_codex_home`
- `pycodex.state.runtime_db_paths` and DB filename/path helpers

The legacy `pycodex/core/paths.py` file was deleted after canonical-path tests/import checks passed. No long-term compatibility shim was retained.

## Status nuance

`codex-utils-home-dir` is marked `implemented` in the crate ledger because the moved helper is the active home-dir behavior surface.

`codex-state` is marked `shim` with `partial_runtime_helpers` because this migration covers runtime DB path helpers only, not the full upstream state crate.

## Validation

- `python -m pytest tests/test_core_paths.py -q`: 6 passed before deleting the legacy file.
- Canonical import smoke passed before deleting the legacy file.
- `python -m pytest tests/test_core_paths.py -q`: 6 passed after deleting the legacy file.
- Post-delete canonical import smoke passed.
- Residual old-coordinate search for `pycodex.core.paths` and `.paths` imports returned no matches.