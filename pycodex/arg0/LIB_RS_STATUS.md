# codex-arg0 src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/arg0/src/lib.rs`

Python target:

- `pycodex/arg0/__init__.py`

Behavior contract covered:

- dispatch path and guard structures
- Linux sandbox alias fallback order
- dotenv parsing and `CODEX_` filtering
- helper alias temp directory creation and PATH update
- stale helper directory janitor cleanup
- special argv0/argv1 dispatch hooks for neighboring process modes

Tests:

- `tests/test_arg0_lib_rs.py` mirrors the Rust local tests and covers Python-specific handler injection for process dispatch boundaries.

Last validation:

- 2026-06-17: `python -m pytest tests\test_arg0_lib_rs.py -q` -> `8 passed`
- 2026-06-17: `python -m py_compile pycodex\arg0\__init__.py tests\test_arg0_lib_rs.py` -> passed

