# codex-hooks/src/declarations.rs status

Rust module: `codex/codex-rs/hooks/src/declarations.rs`

Python module: `pycodex/hooks/__init__.py`

Status: `complete`

Ported contract:

- `PluginHookDeclaration` public field shape.
- `plugin_hook_declarations(...)` projects plugin hook sources without runtime
  state.
- Plugin key sources use `plugin_id.as_key()` and the source-relative hook file
  path separated by `:`.
- Declarations preserve Rust `HookEventsToml::into_matcher_groups()` ordering,
  matcher-group order, and handler order.
- Persisted hook keys are generated through the crate-root
  `hook_key(key_source, event_name, group_index, handler_index)` shape.

Rust evidence:

- `src/declarations.rs`
- `src/declarations.rs::tests::lists_declared_plugin_handlers_with_persisted_hook_keys`

Python evidence:

- `tests/test_hooks_declarations_rs.py`

Validation:

- `python -m pytest tests/test_hooks_declarations_rs.py -q --tb=short`
  passed with `1 passed`.
- `python -m pytest tests/test_external_crate_interfaces.py -k hooks -q --tb=short`
  passed with `1 passed, 17 deselected`.
- Combined hooks validation passed with `27 passed, 17 deselected`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_declarations_rs.py tests\test_external_crate_interfaces.py`
  passed.
