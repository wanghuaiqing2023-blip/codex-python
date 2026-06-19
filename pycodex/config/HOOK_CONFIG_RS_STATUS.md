# codex-config src/hook_config.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/config/src/hook_config.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/hook_config.rs` |
| Python module | `pycodex/config/hook_config.py` |
| Python tests | `tests/test_config_hook_config.py` |
| Status | `complete_candidate` |

`src/hook_config.rs` owns the serialized hooks configuration shapes: hooks files, inline hooks TOML, hook state entries, event-group containers, handler config variants, and managed hooks requirements. Runtime hook dispatch, trust prompts, hash computation, and handler execution remain outside this module boundary.

## Covered Behavior Areas

- `HooksFile` reads the existing JSON shape with a top-level `hooks` table.
- `HooksToml` flattens event arrays and preserves a `state` map keyed by hook identity.
- `HookEventsToml` supports all ten Rust hook event fields and preserves `into_matcher_groups` ordering.
- `HookEventsToml.is_empty` and `handler_count` account for every event group.
- `MatcherGroup` preserves optional matchers and ordered handler lists.
- `HookHandlerConfig` supports `command`, `prompt`, and `agent` variants.
- Command handlers parse `command`, `timeout`, `async`, `statusMessage`, and both `commandWindows` and `command_windows`.
- `ManagedHooksRequirementsToml` flattens hook events alongside `managed_dir` and `windows_managed_dir`.
- Managed hooks expose `is_empty`, `handler_count`, and platform-specific managed directory selection.

## Rust Test Inventory

- `hooks_file_deserializes_existing_json_shape`
- `hook_events_deserialize_from_toml_arrays_of_tables`
- `hooks_toml_deserializes_inline_events_and_state_map`
- `managed_hooks_requirements_flatten_hook_events`
- `hook_events_deserialize_windows_override_from_toml`
- `hook_events_deserialize_camel_case_windows_override_from_toml`

Additional Python coverage records helper behavior for handler counts, empty checks, event ordering, and platform managed-directory selection.

## Remaining Closeout

- Defer pytest until `codex-config` functional code is complete.
