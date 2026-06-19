# codex-config `src/state.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/state.rs`

Rust tests: `codex/codex-rs/config/src/state_tests.rs`

Python module: `pycodex/config/state.py`

Python tests: `tests/test_config_state.py`

## Behavior Contract

`src/state.rs` owns config loading options, loader override helpers, config
layer entries, config-layer stack ordering, active user-layer selection, merged
config views, origin metadata, disabled-layer filtering, startup warnings, and
user-layer replacement helpers.

The Python port mirrors the module-scoped contract:

- `LoaderOverrides` and `ConfigLoadOptions` preserve Rust default and
  test-override construction behavior.
- `ConfigLayerEntry` computes deterministic versions, preserves optional raw
  TOML, disabled reasons, metadata, API layer conversion, config folders, and
  hook folder overrides.
- `ConfigLayerStack` verifies precedence ordering, validates project layer
  root-to-cwd ordering, tracks the highest-precedence active user layer, and
  returns user layers in either precedence order.
- Enabled layers merge from low to high precedence while disabled layers are
  skipped unless explicitly requested.
- Effective user config merges base and profile user layers.
- Origin recording canonicalizes legacy key aliases before storing metadata.
- User-layer replacement and copying preserve non-user layers and profile
  metadata according to Rust behavior.

## Notes

This module treats neighboring config modules as interface constraints:
fingerprint/version hashing, key alias normalization, TOML-like merging, and
requirements objects are consumed through existing Python helpers. Actual
filesystem loading, managed config discovery, thread config, and typed
`ConfigToml` loading remain owned by sibling modules.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
