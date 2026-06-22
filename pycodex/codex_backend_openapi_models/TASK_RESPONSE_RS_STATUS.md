# codex-backend-openapi-models src/models/task_response.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/task_response.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/task_response.py`

Status: `complete_candidate`

## Scope

This generated model owns `TaskResponse`: task identity, display title,
optional turn and metadata fields, archive state, and the required list of
external pull request responses.

## Python Mapping

- `TaskResponse` mirrors the Rust struct fields and derived default values.
- `TaskResponse.new(id, title, archived, external_pull_requests)` mirrors the
  Rust constructor and leaves optional fields as `None`.
- `from_mapping()` decodes the nested `external_pull_requests` list through the
  certified `ExternalPullRequestResponse` model.
- `to_json_dict()` preserves Rust serde field names, skips `None` optional
  fields, and always emits `external_pull_requests`.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/task_response.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_task_response.py`. They are not run
  yet because the crate functional code is not complete.
