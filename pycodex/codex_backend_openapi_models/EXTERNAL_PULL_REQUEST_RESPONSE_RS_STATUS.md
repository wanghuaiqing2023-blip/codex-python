# codex-backend-openapi-models src/models/external_pull_request_response.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/external_pull_request_response.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/external_pull_request_response.py`

Status: `complete_candidate`

## Scope

This generated model owns `ExternalPullRequestResponse`: a backend response
identifier, assistant turn identifier, nested `GitPullRequest`, and optional
Codex-updated SHA.

## Python Mapping

- `ExternalPullRequestResponse` mirrors the Rust struct fields and derived
  default values.
- `ExternalPullRequestResponse.new(id, assistant_turn_id, pull_request)` mirrors
  the Rust constructor and leaves `codex_updated_sha` as `None`.
- `from_mapping()` decodes the nested `pull_request` via the certified
  `GitPullRequest` model.
- `to_json_dict()` preserves Rust serde field names and skips
  `codex_updated_sha` when it is `None`.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/external_pull_request_response.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_external_pull_request_response.py`.
  They are not run yet because the crate functional code is not complete.
