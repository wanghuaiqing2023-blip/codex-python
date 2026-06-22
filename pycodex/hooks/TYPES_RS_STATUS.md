# codex-hooks/src/types.rs status

Rust module: `codex/codex-rs/hooks/src/types.rs`

Python module: `pycodex/hooks/__init__.py`

Status: `complete`

Ported contract:

- `HookResult` variants and `should_abort_operation()` behavior.
- `HookResponse` field shape.
- `Hook::default` name and success function behavior.
- `Hook::execute` response naming and hook-function result behavior.
- `HookEventAfterAgent` and `HookEvent::AfterAgent` wire shape.
- `HookPayload` serialization contract, including snake-case fields,
  second-precision UTC `triggered_at`, skipped absent `client`, and nested
  internally tagged `hook_event`.

Rust evidence:

- `src/types.rs`
- `src/types.rs::tests::hook_payload_serializes_stable_wire_shape`

Python evidence:

- `tests/test_hooks_types_rs.py`

Validation:

- `python -m pytest tests/test_hooks_types_rs.py -q --tb=short`
  passed with `2 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_types_rs.py`
  passed.
