# codex-backend-openapi-models src/models/config_file_response.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/config_file_response.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/config_file_response.py`

Status: `complete_candidate`

## Scope

This generated model owns `ConfigFileResponse`: `contents`, `sha256`,
`updated_at`, and `updated_by_user_id`.

## Python Mapping

- `ConfigFileResponse` mirrors the Rust struct's four optional string fields.
- `ConfigFileResponse.new(...)` mirrors the Rust constructor.
- `to_json_dict()` preserves Rust serde field names and `skip_serializing_if =
  "Option::is_none"` omission behavior.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/config_file_response.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_config_file_response.py`.
  They are not run yet because the crate functional code is not complete.
