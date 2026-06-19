# codex-config `src/loader/layer_io.rs` alignment

Status: `complete_candidate`

## Scope

- Rust crate: `codex-config`
- Rust module: `codex/codex-rs/config/src/loader/layer_io.rs`
- Python module: `pycodex/config/loader.py`
- Python tests: `tests/test_config_loader.py`

This status covers only the `loader/layer_io.rs` module-scoped behavior:
managed config file path selection, dependency-light config file reads,
missing-file handling, strict config validation, loaded managed layer shapes,
and aggregation of managed file and managed preference layers.

The broader `loader/mod.rs` orchestration, project-layer loading, requirements
loading, precedence insertion, and macOS managed preference extraction are
tracked separately from this `layer_io` boundary.

## Evidence

- `managed_config_default_path()` mirrors Rust platform behavior: Unix uses
  `/etc/codex/managed_config.toml`; non-Unix uses
  `<codex_home>/managed_config.toml`.
- `read_config_from_path()` returns `None` for missing config files, parses
  TOML tables, and strict-validates through `ConfigToml` when requested.
- `read_managed_config_from_path()` preserves the Rust managed-layer read
  boundary while reusing the same Python TOML read helper.
- `ManagedConfigFromFile`, `ManagedConfigFromMdm`, and `LoadedConfigLayers`
  mirror the Rust loaded layer containers.
- `load_config_layers_internal()` honors `LoaderOverrides.managed_config_path`,
  reads the managed file layer, accepts optional managed preference TOML
  adapters, and returns both layers without expanding into broader loader
  stack construction.
- Python keeps macOS MDM extraction dependency-light through raw/base64 TOML
  injection helpers; concrete platform preference reading remains outside this
  module boundary and is tracked separately with the macOS loader module.

## Validation

Not run in this turn. The current automation instruction defers actual pytest
execution until `codex-config` functional code is complete.

