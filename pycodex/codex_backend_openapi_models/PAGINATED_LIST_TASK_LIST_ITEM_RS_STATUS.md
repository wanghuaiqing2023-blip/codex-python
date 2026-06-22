# codex-backend-openapi-models src/models/paginated_list_task_list_item_.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/paginated_list_task_list_item_.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/paginated_list_task_list_item.py`

Status: `complete_candidate`

## Scope

This generated model owns `PaginatedListTaskListItem`: a required list of
`TaskListItem` values plus an optional pagination cursor.

## Python Mapping

- `PaginatedListTaskListItem` mirrors the Rust struct fields and derived default
  values.
- `PaginatedListTaskListItem.new(items)` mirrors the Rust constructor and leaves
  `cursor` as `None`.
- `from_mapping()` decodes `items` through the certified `TaskListItem` model.
- `to_json_dict()` preserves Rust serde field names and skips `cursor` when it
  is `None`.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/paginated_list_task_list_item_.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_paginated_list_task_list_item.py`.
  They are not run yet because the crate functional code is not complete.
