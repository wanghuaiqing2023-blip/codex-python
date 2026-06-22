# pycodex.codex_experimental_api_macros

Python alignment target for Rust crate `codex-experimental-api-macros`.

Rust coordinates:

- `codex/codex-rs/codex-experimental-api-macros/src/lib.rs`

Python mapping:

- `pycodex/codex_experimental_api_macros/__init__.py`

Current status: complete.

Implemented contract:

- `derive_experimental_api(...)` mirrors the generated `ExperimentalApi`
  behavior for enum variants and structs.
- Dataclass metadata mirrors `#[experimental("reason")]` and
  `#[experimental(nested)]` field attributes.
- Struct derive behavior preserves Rust field-order checks, registers
  experimental fields, and uses Rust-style snake_case to camelCase serialized
  field names.
- Presence rules mirror Rust branches for `Option`, vector/map-like values,
  `bool`, and always-present scalar fields.

Validation:

- Focused validation:
  `python -m pytest tests/test_codex_experimental_api_macros_lib_rs.py -q`
  -> `8 passed`.
- Syntax validation:
  `python -m py_compile pycodex/codex_experimental_api_macros/__init__.py tests/test_codex_experimental_api_macros_lib_rs.py`
