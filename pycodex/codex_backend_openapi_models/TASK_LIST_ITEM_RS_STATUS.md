# codex-backend-openapi-models src/models/task_list_item.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/task_list_item.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/task_list_item.py`

Status: `complete_candidate`

## Scope

This generated model owns `TaskListItem`: task list identity and title fields,
optional generated-title and timestamp metadata, optional display metadata,
archive and unread state, and optional external pull request responses.

## Python Mapping

- `TaskListItem` mirrors the Rust struct fields and derived default values.
- `TaskListItem.new(id, title, has_generated_title, archived, has_unread_turn)`
  mirrors the Rust constructor and leaves the remaining optional fields as
  `None`.
- `from_mapping()` decodes `pull_requests` through the certified
  `ExternalPullRequestResponse` model and validates status metadata as a
  string-keyed object.
- `to_json_dict()` preserves Rust serde field names and skips `None` optional
  fields.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/task_list_item.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_task_list_item.py`. They are not run
  yet because the crate functional code is not complete.
