# codex-hooks/src/config_rules.rs

Status: `complete`

Rust source:

- `codex/codex-rs/hooks/src/config_rules.rs`

Python target:

- `pycodex/hooks/__init__.py`

Behavior contract:

- `hook_states_from_stack(...)` returns the effective persisted hook state from
  config layers that are allowed to write user hook preferences.
- Only user config layers and session flag layers are read.
- Disabled layers are included, matching Rust's
  `get_layers(LowestPrecedenceFirst, include_disabled = true)`.
- Layers are applied lowest precedence to highest precedence, and later layers
  win field-by-field rather than replacing an entire hook state entry.
- Empty keys, malformed `hooks.state` maps, and malformed individual
  `HookStateToml` entries are ignored.

Rust tests:

- `tests::hook_states_from_stack_respects_layer_precedence`
- `tests::hook_states_from_stack_merges_fields_across_layers`
- `tests::hook_states_from_stack_ignores_malformed_hook_events`
- `tests::hook_states_from_stack_ignores_malformed_state_entries`

Python tests:

- `tests/test_hooks_config_rules_rs.py`

Validation:

- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py -q --tb=short`
  passed with `8 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_config_rules_rs.py`
  passed.
- `python -m pytest tests/test_hooks_config_rules_rs.py tests/test_hooks_types_rs.py tests/test_hooks_declarations_rs.py tests/test_core_suite_hooks.py tests/test_core_suite_hooks_mcp.py -q --tb=short`
  passed with `31 passed`.
