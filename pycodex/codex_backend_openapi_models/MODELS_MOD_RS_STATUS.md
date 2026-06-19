# codex-backend-openapi-models src/models/mod.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/models/mod.rs`

Python module:
`pycodex/codex_backend_openapi_models/models/__init__.py`

Status: `complete_candidate`

## Scope

This module owns the curated generated-model export surface for the crate. It
declares the internal model modules and publicly re-exports the model types used
by the workspace.

## Python Mapping

- `pycodex.codex_backend_openapi_models.models` mirrors the Rust curated public
  model exports through imports and `__all__`.
- Export order follows the Rust module grouping: config, cloud tasks, rate
  limits, then credit status.
- Python-only `UNSET` and `Unset` helpers remain exported for local
  double-option model support and are documented as implementation details.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/models/mod.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_models_mod.py`. They are not run yet
  because the crate functional code is not complete.
