# codex-config `src/loader/macos.rs` alignment

Status: `complete_candidate`

## Scope

- Rust crate: `codex-config`
- Rust module: `codex/codex-rs/config/src/loader/macos.rs`
- Python module: `pycodex/config/loader.py`
- Python tests: `tests/test_config_loader.py`

This status covers only the macOS managed-preferences loader contract:
managed preference key constants, MDM requirement source construction, base64
TOML decoding for managed config and requirements, strict config validation
for injected managed config, and merging managed requirements into sourced
requirements.

Python intentionally does not call CoreFoundation `CFPreferencesCopyAppValue`.
Instead, it exposes dependency-light raw/base64 injection helpers that preserve
the parsing, validation, source labeling, and merge semantics. Concrete OS
preference access is recorded as an implementation adapter outside the
module-scoped behavior contract used by the Python port.

## Evidence

- `MANAGED_PREFERENCES_APPLICATION_ID`, `MANAGED_PREFERENCES_CONFIG_KEY`, and
  `MANAGED_PREFERENCES_REQUIREMENTS_KEY` mirror the Rust constants.
- `managed_preferences_requirements_source()` returns the MDM
  `RequirementSource` with Rust's domain/key pair.
- `managed_config_from_mdm_base64()` decodes base64 UTF-8 TOML, rejects invalid
  base64/UTF-8, preserves raw TOML, and strict-validates through `ConfigToml`
  when requested.
- `managed_requirements_from_mdm_base64()` decodes base64 UTF-8 TOML into
  `ConfigRequirementsToml` and treats missing/blank override values as absent.
- `load_managed_admin_requirements_toml()` mirrors Rust override handling by
  merging parsed requirements with the managed-preferences source and applying
  remote sandbox config before the source merge.

## Validation

Not run in this turn. The current automation instruction defers actual pytest
execution until `codex-config` functional code is complete.

