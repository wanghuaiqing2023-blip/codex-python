# codex-core-api test alignment

Rust crate: `codex-core-api`

Python package: `pycodex/core_api`

Status: `complete`

Certified modules:

- `codex/codex-rs/core-api/src/lib.rs` -> `pycodex/core_api/__init__.py`

Source-contract coverage:

- all Rust `pub use` names from `src/lib.rs` are importable from the Python facade.
- existing Python counterparts are re-exported by identity where available.
- neighboring not-yet-concrete types are represented by explicit facade placeholders instead of silently missing names.

Validation:

- `python -m pytest tests/test_core_api_lib_rs.py -q`
- `python -m py_compile pycodex/core_api/__init__.py tests/test_core_api_lib_rs.py`
