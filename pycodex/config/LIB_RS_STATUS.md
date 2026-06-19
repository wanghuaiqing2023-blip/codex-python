# codex-config `src/lib.rs` alignment

Status: `complete_candidate`

## Scope

- Rust crate: `codex-config`
- Rust module: `codex/codex-rs/config/src/lib.rs`
- Python module: `pycodex/config/__init__.py`
- Python tests: package import coverage across `tests/test_config_*.py`

This status covers the crate root surface only: Rust module declarations,
public modules, the `CONFIG_TOML_FILE` constant, and `pub use` re-export
contract. Functional behavior remains owned by each implementation module and
is tracked in that module's status file.

## Evidence

- `pycodex.config` re-exports the public data shapes and helpers implemented
  across the config package, matching the Rust crate-root convenience surface
  where practical.
- `CONFIG_TOML_FILE` is re-exported from the loader surface as the Python
  counterpart to Rust's crate-root constant.
- Config requirements, constraint, diagnostics, hook config, host name,
  marketplace/plugin/MCP edit helpers, MCP types, merge, project root markers,
  requirements exec policy, schema, skills config, state, strict config,
  thread config, TUI keymap, and typed config TOML exports are surfaced through
  `pycodex.config`.
- Rust public modules `config_toml`, `loader`, `permissions_toml`,
  `profile_toml`, `schema`, and `types` correspond to importable Python
  modules in `pycodex/config/`.
- The Python root intentionally exposes a few additional stable helper
  aliases for local ergonomics and tests; ownership and parity evidence remain
  recorded against the underlying module status files.

## Validation

Not run in this turn. The current automation instruction defers actual pytest
execution until `codex-config` functional code is complete.

