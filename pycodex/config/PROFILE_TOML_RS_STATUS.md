# codex-config src/profile_toml.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/profile_toml.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/profile_toml.rs` |
| Python module | `pycodex/config/profile_toml.py` |
| Python tests | `tests/test_config_profile_toml.py` |
| Status | `complete_candidate` |

`src/profile_toml.rs` owns named profile TOML shapes for reusable config
options and profile-scoped TUI settings.

## Covered Behavior Areas

- `ConfigProfile` accepts the source-confirmed profile field set for model,
  provider, approval, sandbox, reasoning, path, instruction-inclusion, tools,
  web search, analytics, TUI, Windows, feature, and OSS provider settings.
- Path-like profile fields are normalized to `Path` values in Python.
- Deprecated JavaScript REPL fields are retained as accepted, skipped-schema
  compatibility inputs.
- `ProfileTui` exposes `session_picker_view`.
- `ConfigProfile` and `ProfileTui` reject unknown fields.
- Profile-scoped `session_picker_view` accepts only the known wire values.
- Basic scalar and mapping fields reject invalid Python shapes.
- `to_mapping` round-trips populated profile fields into TOML-like mappings.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from source-level struct fields, `deny_unknown_fields` annotations, and enum
wire values.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused profile TOML tests
  and promote this module from `complete_candidate` to `complete`.
