# codex-thread-store src/types.rs

Rust crate: `codex-thread-store`
Rust module: `src/types.rs`
Python package: `pycodex.thread_store`

## Status

`complete_slice`

## Rust Anchors

- `optional_option::{serialize,deserialize}`
- `ClearableField<T> = Option<Option<T>>`
- `GitInfoPatch`
- `GitInfoPatch::merge`
- `ThreadMetadataPatch`
- `ThreadMetadataPatch::merge`
- `ThreadMetadataPatch::is_empty`

## Covered Contract

- Clearable `ThreadMetadataPatch` fields distinguish omitted/no-op from
  explicit clear requests.
- Explicit clear requests serialize as JSON `null` for `name`,
  `thread_source`, `agent_nickname`, `agent_role`, and `agent_path`.
- Nested `GitInfoPatch` omits absent fields, serializes present branch values,
  and preserves explicit `origin_url` clears.
- Missing fields deserialize to omitted/no-op patch values, and an empty mapping
  is an empty patch.
- Metadata merge semantics are field-presence based: omitted fields leave
  current values unchanged, explicit clear requests replace current values, and
  nested git patch fields merge independently.

## Python Tests

- `tests/test_thread_store_types_rs.py::test_thread_metadata_patch_round_trips_optional_clears`
- `tests/test_thread_store_types_rs.py::test_git_info_patch_round_trips_optional_clears`
- `tests/test_thread_store_types_rs.py::test_thread_metadata_patch_accepts_missing_fields`
- `tests/test_thread_store_types_rs.py::test_thread_metadata_patch_merge_uses_presence_semantics`

## Validation

2026-06-22:

- `python -m pytest tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `9 passed`
- `python -m pytest tests\test_external_crate_interfaces.py::test_thread_store_types_merge_and_in_memory_store_contract tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py -q --tb=short`
  - `10 passed`
- `python -m py_compile pycodex\thread_store\__init__.py tests\test_thread_store_types_rs.py tests\test_thread_store_in_memory_rs.py`
  - passed

## Remaining Outside This Slice

- Type behavior that is only meaningful through unported `src/local/*` or
  `src/live_thread.rs` runtime paths remains tracked with those modules.
