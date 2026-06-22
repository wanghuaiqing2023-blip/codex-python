# codex-backend-openapi-models src/models/credit_status_details.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/credit_status_details.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/credit_status_details.py`

Status: `complete_candidate`

## Scope

This generated model owns `CreditStatusDetails`: `has_credits`, `unlimited`,
`balance`, `approx_local_messages`, and `approx_cloud_messages`.

## Python Mapping

- `CreditStatusDetails` mirrors the Rust struct fields and derived default
  values.
- `CreditStatusDetails.new(has_credits, unlimited)` mirrors the Rust
  constructor and leaves all double-option fields omitted.
- `UNSET` represents omitted outer options for `balance`,
  `approx_local_messages`, and `approx_cloud_messages`; Python `None`
  represents explicit JSON null.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/credit_status_details.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_credit_status_details.py`.
  They are not run yet because the crate functional code is not complete.
