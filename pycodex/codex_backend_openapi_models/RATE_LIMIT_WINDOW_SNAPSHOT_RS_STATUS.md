# codex-backend-openapi-models src/models/rate_limit_window_snapshot.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_window_snapshot.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/rate_limit_window_snapshot.py`

Status: `complete_candidate`

## Scope

This generated model owns the `RateLimitWindowSnapshot` data shape:
`used_percent`, `limit_window_seconds`, `reset_after_seconds`, and `reset_at`.

## Python Mapping

- `RateLimitWindowSnapshot` mirrors the Rust struct fields and derived default
  zero values.
- `RateLimitWindowSnapshot.new(...)` mirrors the Rust constructor.
- `from_mapping()` and `to_json_dict()` preserve the serde field names used by
  the generated Rust model.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/rate_limit_window_snapshot.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_rate_limit_window_snapshot.py`.
  They are not run yet because the crate functional code is not complete.
