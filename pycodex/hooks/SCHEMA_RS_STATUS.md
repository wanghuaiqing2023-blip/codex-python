# codex-hooks src/schema.rs Status

Rust crate: `codex-hooks`

Rust module: `src/schema.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Rust Anchors

- Hook command input/output fixture constants
- `NullableString`
- `SubagentCommandInputFields`
- `HookUniversalOutputWire`
- Hook command input/output wire structs
- `write_schema_fixtures`
- `schema_json`
- `canonicalize_json`
- Hook-event const schema helpers
- Permission mode, session-start source, and compaction-trigger enum schema
  helpers

## Behavior Covered

- Python exposes the full Rust fixture-name inventory and writes all hook schema
  fixture files under a fresh `generated/` directory.
- Schema JSON is canonicalized recursively and emitted as stable pretty JSON.
- Turn-scoped hook input schemas include the Codex `turn_id` extension and mark
  it as required, matching Rust's schema tests.
- Hooks that may run inside subagents expose optional `agent_id` and
  `agent_type` schema fields without requiring them.
- `SubagentCommandInputFields` projects subagent context as flat optional fields
  and omits them for root-agent hook inputs.
- Nullable string helpers preserve Rust's `Option<String>` / path-to-display
  command-input semantics.

## Python Tests

- `tests/test_hooks_schema_rs.py`

## Validation

- `python -m pytest tests/test_hooks_schema_rs.py -q --tb=short`
  passed on 2026-06-21 with `5 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_schema_rs.py`
  passed on 2026-06-21.
- Hooks module validation passed on 2026-06-21 with `116 passed`.
- Hooks plus core hooks regression validation passed on 2026-06-21 with
  `139 passed`.

## Adaptation Notes

The Python port does not pull in a third-party JSON Schema generator equivalent
to Rust `schemars`. It carries a dependency-light schema surface that preserves
the Rust-owned fixture inventory, stable JSON ordering, write semantics, field
requiredness, enum/const values, nullable string shape, and subagent projection
contracts that are exercised by the Rust module tests.

## Remaining Debt

No module-local debt remains for `src/schema.rs`. `codex-hooks` remains
`module_progress` while `src/engine/*` remains open.
