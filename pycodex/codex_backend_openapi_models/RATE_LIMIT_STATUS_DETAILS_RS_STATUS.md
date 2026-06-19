# codex-backend-openapi-models src/models/rate_limit_status_details.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_details.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/rate_limit_status_details.py`

Status: `complete_candidate`

## Scope

This generated model owns the `RateLimitStatusDetails` data shape: `allowed`,
`limit_reached`, `primary_window`, and `secondary_window`.

## Python Mapping

- `RateLimitStatusDetails` mirrors the Rust struct fields and derived default
  values.
- `RateLimitStatusDetails.new(allowed, limit_reached)` mirrors the Rust
  constructor and leaves both window fields omitted.
- `UNSET` represents the outer `Option::None` state for the two
  `serde_with::rust::double_option` window fields. Python `None` represents
  explicit JSON `null`, and mapping objects are decoded as
  `RateLimitWindowSnapshot`.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_details.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_rate_limit_status_details.py`.
  They are not run yet because the crate functional code is not complete.
