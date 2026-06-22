# codex-config src/overrides.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/overrides.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/overrides.rs` |
| Python module | `pycodex/config/overrides.py` |
| Python exports | `pycodex.config.default_empty_table`, `pycodex.config.build_cli_overrides_layer`, `pycodex.config.apply_single_override` |
| Python tests | `tests/test_config_overrides.py` |
| Status | `complete_candidate` |

`src/overrides.rs` owns construction of a TOML-shaped config layer from parsed
CLI override path/value pairs.

## Covered Behavior Areas

- `default_empty_table` returns an empty TOML table shape.
- `build_cli_overrides_layer` applies overrides in order onto one root table.
- Dotted paths create nested tables.
- A leaf segment overwrites any previous value at that path.
- A non-table intermediate is replaced with a table before applying deeper
  path segments.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from source-level contracts for `default_empty_table`, `build_cli_overrides_layer`,
and `apply_toml_override` behavior.

## Python Adaptation Notes

`pycodex/config/overrides.py` also includes raw CLI override parsing helpers
from `codex/codex-rs/utils/cli/src/config_override.rs`. Those helpers are
covered by the same Python test file but are outside this module's
`codex-config/src/overrides.rs` completion boundary.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused override tests and
  promote this module from `complete_candidate` to `complete`.
