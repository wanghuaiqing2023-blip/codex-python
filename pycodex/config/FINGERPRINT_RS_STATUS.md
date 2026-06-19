# codex-config src/fingerprint.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/fingerprint.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/fingerprint.rs` |
| Python module | `pycodex/config/fingerprint.py` |
| Python exports | `pycodex.config.record_origins`, `pycodex.config.version_for_toml` |
| Python tests | `tests/test_config_fingerprint.py` |
| Status | `complete_candidate` |

`src/fingerprint.rs` owns config-layer origin path recording and deterministic
version fingerprints for TOML-like config values.

## Covered Behavior Areas

- `record_origins` recursively walks tables and arrays.
- Scalar leaves are recorded with dot-joined paths.
- Array indexes are included as path components.
- Empty root scalar values are ignored, matching Rust's empty-path guard.
- Empty tables do not create origin entries.
- `version_for_toml` converts TOML-like data into JSON, recursively sorts
  object keys, preserves array order, serializes canonical JSON, and prefixes
  the SHA-256 digest with `sha256:`.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from the module's public helper behavior and source-level contracts.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused fingerprint tests
  and promote this module from `complete_candidate` to `complete`.
