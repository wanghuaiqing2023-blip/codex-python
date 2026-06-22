# codex-stdio-to-uds test alignment

Rust crate: `codex-stdio-to-uds`

Python package: `pycodex/stdio_to_uds`

Status: `complete`

Certified modules:

- `codex/codex-rs/stdio-to-uds/src/lib.rs` -> `pycodex/stdio_to_uds/__init__.py`
- `codex/codex-rs/stdio-to-uds/src/main.rs` -> `pycodex/stdio_to_uds/__init__.py`

Remaining Rust modules: none.

Rust tests and fixtures:

- `codex/codex-rs/stdio-to-uds/tests/stdio_to_uds.rs`
  - `pipes_stdin_and_stdout_through_socket`

Validation:

- `python -m pytest tests/test_stdio_to_uds_crate.py -q` (`3 passed, 1 skipped`)
- `python -m py_compile pycodex/stdio_to_uds/__init__.py tests/test_stdio_to_uds_crate.py` (passed)
