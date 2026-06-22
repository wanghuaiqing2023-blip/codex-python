# codex-backend-openapi-models src/models/code_task_details_response.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/code_task_details_response.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/code_task_details_response.py`

Status: `complete_candidate`

## Scope

This generated model owns `CodeTaskDetailsResponse`: a required `TaskResponse`
plus optional JSON-object maps for the current user, assistant, and diff task
turns.

## Python Mapping

- `CodeTaskDetailsResponse` mirrors the Rust struct fields and derived default
  values.
- `CodeTaskDetailsResponse.new(task)` mirrors the Rust constructor and leaves
  optional turn maps as `None`.
- `from_mapping()` decodes `task` through the certified `TaskResponse` model and
  validates optional turn maps as string-keyed objects.
- `to_json_dict()` preserves Rust serde field names and skips `None` optional
  turn maps.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/code_task_details_response.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_code_task_details_response.py`.
  They are not run yet because the crate functional code is not complete.
