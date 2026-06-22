# codex-hooks src/engine/schema_loader.rs Status

Rust crate: `codex-hooks`

Rust module: `codex/codex-rs/hooks/src/engine/schema_loader.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Anchors

- `GeneratedHookSchemas`
- `generated_hook_schemas()`
- `parse_json_schema(...)`
- Runtime registration point: `ClaudeHooksEngine::new` calls
  `schema_loader::generated_hook_schemas()` before discovering handlers.

## Python Coverage

- `tests/test_hooks_engine_schema_loader_rs.py` mirrors the Rust
  `loads_generated_hook_schemas` test across all 20 generated schema fields.
- The same test file also covers the fixed Rust field inventory, OnceLock-like
  cached return value, and named invalid-schema error contract.

## Validation

- `python -m pytest tests/test_hooks_engine_schema_loader_rs.py -q --tb=short`
  passed on 2026-06-21 with `3 passed`.
- Hooks module validation including this file passed on 2026-06-21 with
  `125 passed`.
- Hooks plus core hooks regression validation including this file passed on
  2026-06-21 with `148 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_schema_loader_rs.py`
  passed on 2026-06-21.

## Remaining Debt

- None for this module-scoped behavior contract. Sibling `src/engine/*`
  command runner, discovery, dispatcher, and engine facade modules remain
  separate `codex-hooks` crate-level gaps.
