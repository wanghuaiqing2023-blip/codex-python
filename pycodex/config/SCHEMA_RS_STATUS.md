# codex-config src/schema.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/schema.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/schema.rs` |
| Python module | `pycodex/config/schema.py` |
| Python exports | `pycodex.config.canonicalize`, `pycodex.config.config_schema`, `pycodex.config.config_schema_json`, `pycodex.config.write_config_schema` |
| Python tests | `tests/test_core_bin_config_schema.py` |
| Status | `complete_candidate` |

`src/schema.rs` owns config schema construction, recursive JSON
canonicalization, pretty JSON rendering, and writing the schema fixture to
disk.

## Covered Behavior Areas

- `canonicalize` recursively sorts JSON object keys while preserving array
  order.
- `config_schema` exposes the checked-in config schema object.
- `config_schema_json` renders canonical pretty-printed JSON bytes.
- `write_config_schema` writes those bytes to an explicit output path.
- Python intentionally reads the upstream checked-in schema fixture instead of
  regenerating it through `schemars`, preserving a dependency-light port while
  keeping the public helper surface aligned.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python coverage is provided
through config-schema command tests that call `write_config_schema` and compare
the output with `config_schema_json`.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the config schema helper/CLI
  tests and promote this module from `complete_candidate` to `complete`.
