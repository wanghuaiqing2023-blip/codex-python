# codex-async-utils Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/async-utils/src/lib.rs`

Python module:

- `pycodex/async_utils/__init__.py`

Parity evidence:

- `tests/test_async_utils_lib_rs.py`

Rust-derived coverage:

- `returns_ok_when_future_completes_first`
- `returns_err_when_token_cancelled_first`
- `returns_err_when_token_already_cancelled`

Validation:

- `python -m pytest tests\test_async_utils_lib_rs.py -q` -> `3 passed`
- `python -m py_compile pycodex\async_utils\__init__.py tests\test_async_utils_lib_rs.py` -> passed

Known adaptations:

- Rust exposes `or_cancel` as an extension trait on futures. Python exposes the equivalent as a standalone async helper because Python awaitables do not support Rust-style extension traits.

