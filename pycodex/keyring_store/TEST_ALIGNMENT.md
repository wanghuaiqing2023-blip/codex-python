# codex-keyring-store test alignment

Rust crate: `codex-keyring-store`

Python package: `pycodex/keyring_store`

Status: `complete`

Certified modules:

- `codex/codex-rs/keyring-store/src/lib.rs` -> `pycodex/keyring_store/__init__.py`

Remaining Rust modules: none.

Rust tests and fixtures:

- No standalone Rust test functions are registered for this crate; source
  contract is derived from `src/lib.rs`, including the public `tests` helper
  module.

Validation:

- `python -m pytest tests/test_keyring_store_lib_rs.py -q` (`5 passed`)
- `python -m py_compile pycodex/keyring_store/__init__.py tests/test_keyring_store_lib_rs.py` (passed)
