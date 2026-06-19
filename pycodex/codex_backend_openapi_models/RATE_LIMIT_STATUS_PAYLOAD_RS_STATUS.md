# codex-backend-openapi-models src/models/rate_limit_status_payload.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_payload.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/rate_limit_status_payload.py`

Status: `complete_candidate`

## Scope

This generated module owns `RateLimitStatusPayload`, `RateLimitReachedType`,
`RateLimitReachedKind`, and `PlanType`.

## Python Mapping

- `PlanType` and `RateLimitReachedKind` mirror the Rust serde wire values and
  map unknown strings to `UNKNOWN`.
- `RateLimitReachedType` preserves the Rust field rename from `kind` to JSON
  key `type`.
- `RateLimitStatusPayload.new(plan_type)` mirrors the Rust constructor and
  leaves all double-option fields omitted.
- `UNSET` represents omitted outer options for `rate_limit`, `credits`,
  `additional_rate_limits`, and `rate_limit_reached_type`; Python `None`
  represents explicit JSON null.

## Intentional Python Adaptation

- `CreditStatusDetails` is not implemented in this module turn. The `credits`
  field accepts mapping/object values as a dependency interface constraint and
  will be tightened when `src/models/credit_status_details.rs` is ported.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_status_payload.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_rate_limit_status_payload.py`.
  They are not run yet because the crate functional code is not complete.
