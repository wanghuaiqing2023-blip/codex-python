# codex-backend-openapi-models src/models/additional_rate_limit_details.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/additional_rate_limit_details.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/additional_rate_limit_details.py`

Status: `complete_candidate`

## Scope

This generated model owns the `AdditionalRateLimitDetails` data shape:
`limit_name`, `metered_feature`, and optional nested `rate_limit`.

## Python Mapping

- `AdditionalRateLimitDetails` mirrors the Rust struct fields.
- `AdditionalRateLimitDetails.new(limit_name, metered_feature)` mirrors the
  Rust constructor and leaves the outer `rate_limit` option omitted.
- `UNSET` represents the outer `Option::None` state so JSON serialization can
  omit `rate_limit`, while Python `None` represents explicit JSON `null`
  (`Some(None)` in Rust's `serde_with::rust::double_option` encoding).

## Evidence

- Rust source: `codex/codex-rs/codex-backend-openapi-models/src/models/additional_rate_limit_details.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_additional_rate_limit_details.py`.
  They are not run yet because the crate functional code is not complete.
