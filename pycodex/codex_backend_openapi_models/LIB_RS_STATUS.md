# codex-backend-openapi-models src/lib.rs alignment

Rust module:
`codex/codex-rs/codex-backend-openapi-models/src/lib.rs`

Python module:
`pycodex/codex_backend_openapi_models/__init__.py`

Status: `complete_candidate`

## Scope

This crate root re-exports the generated OpenAPI `models` namespace and
intentionally contains no hand-written model types.

## Python Mapping

- `pycodex.codex_backend_openapi_models` exposes the `models` namespace through
  an import and `__all__`.
- The root package does not duplicate generated model symbols; model exports are
  owned by `pycodex.codex_backend_openapi_models.models`, matching Rust's
  `pub mod models`.

## Evidence

- Rust source:
  `codex/codex-rs/codex-backend-openapi-models/src/lib.rs`
- Rust crate has no standalone tests for this module.
- Python parity tests added in
  `tests/test_codex_backend_openapi_models_lib.py`.
- Focused crate validation passed on 2026-06-18 with `55 passed` across
  `tests/test_codex_backend_openapi_models*.py`.
