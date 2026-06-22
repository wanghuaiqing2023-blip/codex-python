# codex-config src/merge.rs status

Updated: 2026-06-17

This file tracks only the Rust module
`codex/codex-rs/config/src/merge.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/merge.rs` |
| Rust tests | `codex/codex-rs/config/src/merge_tests.rs` |
| Python module | `pycodex/config/merge.py` |
| Python tests | `tests/test_config_merge.py` |
| Status | `complete_candidate` |

`src/merge.rs` owns TOML-like config layer merging, including overlay
precedence, key-alias normalization, and managed permission network domain key
normalization during merges.

## Covered Behavior Areas

- Overlay values take precedence over base values.
- Nested tables merge recursively.
- Non-table or mixed table/non-table values are replaced by the normalized
  overlay value.
- Legacy `memories.no_memories_if_mcp_or_web_search` keys are normalized in
  base layers.
- Legacy memory keys are normalized in overlay layers.
- Canonical memory keys win when one layer contains both canonical and legacy
  names.
- `permissions.<profile>.network.domains` keys are normalized before overlaying
  so host-case variants collide correctly.

## Rust Test Inventory

Rust tests covered by `tests/test_config_merge.py`:

- `merge_toml_values_normalizes_legacy_key_from_base_layer`
- `merge_toml_values_normalizes_legacy_key_from_overlay_layer`
- `merge_toml_values_prefers_canonical_key_when_one_layer_has_both_names`
- `merge_toml_values_normalizes_permission_network_domains_before_overlaying`

Additional Python coverage records source-level behavior for replacing a
non-table base value with a normalized overlay table.

## Remaining Closeout

- Defer actual pytest execution until `codex-config` functional code is
  complete, per the current crate automation instruction.
- After crate-level validation is allowed, run the focused merge tests and
  promote this module from `complete_candidate` to `complete`.
