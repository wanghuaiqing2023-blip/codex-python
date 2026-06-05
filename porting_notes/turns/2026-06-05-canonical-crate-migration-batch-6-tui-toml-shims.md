# Canonical crate migration batch 6: remove root TOML shim and canonicalize TUI

Date: 2026-06-05

## Summary

Removed the final two root-level legacy shim files and canonicalized the TUI package path according to the Rust crate tree.

## Removed legacy paths

| Legacy Python path | Canonical Python path | Result |
|---|---|---|
| `pycodex/_toml.py` | `pycodex/config/toml_compat.py` | deleted |
| `pycodex/tui.py` | `pycodex/tui/__init__.py` | replaced by canonical package |
| `pycodex/cli/tui.py` | `pycodex/tui/__init__.py` | deleted |

## Alignment notes

`pycodex/_toml.py` was a root compatibility shim only. Code should import TOML helpers from `pycodex.config.toml_compat`.

`codex/codex-rs/tui` maps to `pycodex/tui` under the crate-level alignment rule. Because Python cannot have both `pycodex/tui.py` and `pycodex/tui/` at the same time, this migration replaced the old file shim atomically with a canonical package directory.

## Import policy

Production and tests now use canonical paths:

- `pycodex.config.toml_compat`
- `pycodex.tui`

No long-term compatibility shim was retained.

## Validation

- Canonical import smoke passed for `pycodex.tui`, `pycodex.config.toml_compat`, and `pycodex.cli.parser`.
- `python -m pytest tests/test_pycodex_init.py tests/test_config_overrides.py tests/test_core_config_edit.py tests/test_core_config_lock.py tests/test_exec_config_plan.py -q`: 151 passed.
- Post-delete canonical import smoke passed.
- Old file existence check confirmed:
  - `pycodex/_toml.py=False`
  - `pycodex/tui.py=False`
  - `pycodex/cli/tui.py=False`
  - `pycodex/tui/__init__.py=True`
  - `pycodex/config/toml_compat.py=True`