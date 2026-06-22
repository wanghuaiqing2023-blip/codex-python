# codex-config src/strict_config.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/strict_config.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/strict_config.rs` |
| Rust tests | `codex/codex-rs/config/src/strict_config_tests.rs` |
| Python module | `pycodex/config/strict_config.py` |
| Python tests | `tests/test_config_strict_config.py` |
| Status | `complete_candidate` |

`src/strict_config.rs` owns strict config validation on top of TOML parsing,
ignored-field tracking, unknown feature detection, and diagnostic range
selection for unknown config fields.

## Covered Behavior Areas

- TOML parse failures are converted to config diagnostics.
- Type/validation errors take precedence over ignored-field errors.
- Unknown top-level fields report `unknown configuration field` with a
  key-span range.
- Unknown feature keys under `[features]` and
  `[profiles.<name>.features]` are reported as strict-config errors.
- Opaque desktop config keys are accepted.
- Non-file source names are preserved as diagnostic paths.
- Helper functions return the first ignored path or unknown feature path.
- Python exposes a custom allowed-field set to stand in for Rust's generic
  target type `T: DeserializeOwned`.

## Rust Test Inventory

Rust tests covered by `tests/test_config_strict_config.py`:

- `ignored_toml_field_errors_accept_non_file_source_names`
- `type_errors_take_precedence_over_ignored_fields`
- `strict_config_rejects_unknown_feature_key`
- `strict_config_rejects_unknown_profile_feature_key`
- `strict_config_accepts_opaque_desktop_keys`

Additional Python coverage records source-level contracts for
`ignored_toml_value_field`, `unknown_feature_toml_value_field`, and
custom allowed-field validation.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused strict-config tests
  and promote this module from `complete_candidate` to `complete`.
