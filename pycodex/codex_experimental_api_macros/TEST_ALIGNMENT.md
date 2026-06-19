# codex-experimental-api-macros test alignment

Rust crate: `codex-experimental-api-macros`

Python package: `pycodex/codex_experimental_api_macros`

Status: `complete`

Module mapping:

- `codex/codex-rs/codex-experimental-api-macros/src/lib.rs` ->
  `pycodex/codex_experimental_api_macros/__init__.py` (`complete`)

Rust-derived/source-contract coverage:

- Derive behavior supports unit, tuple, named, and stable enum variants.
- Nested experimental fields recurse through option-like values.
- Nested collections and maps return the first nested experimental reason.
- Optional experimental fields are considered used when present, even if the
  contained collection is empty.
- Experimental field registration uses the Rust `ExperimentalField` shape and
  snake_case to camelCase field-name conversion.
- Presence rules mirror Rust's Option, Vec/map-like, bool, and default scalar
  branches.
- Field-order checks preserve Rust macro expansion order.

Validation:

- Focused validation:
  `python -m pytest tests/test_codex_experimental_api_macros_lib_rs.py -q`
  -> `8 passed`.
- Syntax validation:
  `python -m py_compile pycodex/codex_experimental_api_macros/__init__.py tests/test_codex_experimental_api_macros_lib_rs.py`
