# codex-config src/key_aliases.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/key_aliases.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/key_aliases.rs` |
| Python module | `pycodex/config/key_aliases.py` |
| Python exports | `pycodex.config.normalize_key_aliases`, `pycodex.config.normalized_with_key_aliases` |
| Python tests | `tests/test_config_key_aliases.py` |
| Status | `complete_candidate` |

`src/key_aliases.rs` owns TOML config key alias normalization before typed
config loading. The current Rust alias maps
`memories.no_memories_if_mcp_or_web_search` to
`memories.disable_on_external_context`.

## Covered Behavior Areas

- The alias table contains the memories legacy-to-canonical key mapping.
- `normalize_key_aliases` applies aliases only when the full table path matches
  `["memories"]`.
- The legacy key is removed and inserted at the canonical key when no
  canonical value already exists.
- When both legacy and canonical keys are present, the canonical value wins,
  matching Rust's `entry(...).or_insert(value)` behavior.
- `normalized_with_key_aliases` recursively normalizes nested tables without
  mutating the input value.
- Array items are normalized using the same table path, matching Rust's array
  branch that does not append an index to the path.

## Rust Test Inventory

This Rust module has no local `#[cfg(test)]` block. Python tests are derived
from the module's public helper behavior and the current alias table.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused key-alias tests and
  promote this module from `complete_candidate` to `complete`.
