# codex-config src/tui_keymap.rs status

Updated: 2026-06-17

This file tracks only the Rust module `codex/codex-rs/config/src/tui_keymap.rs`.

## Module Boundary

| Field | Value |
|---|---|
| Rust crate | `codex-config` |
| Rust module | `codex/codex-rs/config/src/tui_keymap.rs` |
| Python module | `pycodex/config/tui_keymap.py` |
| Python tests | `tests/test_config_tui_keymap.py` |
| Status | `complete_candidate` |

`src/tui_keymap.rs` owns the on-disk `[tui.keymap]` config contract: context/action shape validation, single-or-many keybinding values, empty-list unbinding, and canonical key-spec normalization. Runtime key dispatch, precedence/conflict validation, and input event matching remain outside this module.

## Covered Behavior Areas

- Known context/action structs reject unknown fields.
- Actions directly under root `[tui.keymap]` are rejected.
- Removed backtrack actions are rejected.
- A global action binding is accepted and round-trips.
- `minus` and `alt-minus` bindings are accepted.
- `KeybindingsSpec` preserves single string, list, and empty-list unbind shapes.
- Key aliases and modifier aliases normalize to Rust canonical spelling.
- Modifiers are ordered `ctrl-alt-shift`.
- Duplicate/misplaced modifiers, missing keys, unknown keys, and `f13` are rejected.
- `Tui.keymap` integrates the typed keymap child schema.

## Rust Test Inventory

- `misplaced_action_at_keymap_root_is_rejected`
- `misspelled_action_under_context_is_rejected`
- `misspelled_vim_text_object_action_is_rejected`
- `removed_backtrack_actions_are_rejected`
- `action_under_global_context_is_accepted`
- `minus_bindings_under_global_context_are_accepted`

Additional Python coverage records alias normalization, malformed key specs, empty-list unbinding, and `Tui` integration.

## Remaining Closeout

- Defer pytest until `codex-config` functional code is complete.
