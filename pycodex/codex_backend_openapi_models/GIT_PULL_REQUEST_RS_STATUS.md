# codex-backend-openapi-models src/models/git_pull_request.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/git_pull_request.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/git_pull_request.py`

Status: `complete_candidate`

## Scope

This generated model owns `GitPullRequest`: required pull request metadata plus
optional pull request text, branch, SHA, comment, diff, and user JSON fields.

## Python Mapping

- `GitPullRequest` mirrors the Rust struct fields and derived default values.
- `GitPullRequest.new(number, url, state, merged, mergeable)` mirrors the Rust
  constructor and leaves optional fields as `None`.
- `to_json_dict()` preserves Rust serde field names and skips `None` optional
  fields.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/git_pull_request.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_git_pull_request.py`. They are not
  run yet because the crate functional code is not complete.
