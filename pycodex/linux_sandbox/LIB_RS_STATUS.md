# codex-linux-sandbox src/lib.rs status

Status: `complete_candidate`

Rust module: `codex/codex-rs/linux-sandbox/src/lib.rs`

Python module: `pycodex/linux_sandbox/__init__.py`

Behavior covered:

- Crate-root `run_main()` is exported from the Python package.
- Non-Linux targets raise `RuntimeError("codex-linux-sandbox is only supported on Linux")`,
  matching Rust's non-Linux panic message.
- Linux targets perform the same crate-root delegation shape as Rust by loading
  sibling module `linux_run_main` and calling its `run_main()`.

Prepared tests:

- `tests/test_linux_sandbox_lib_rs.py`

Validation:

- `python -m py_compile pycodex/linux_sandbox/__init__.py tests/test_linux_sandbox_lib_rs.py`
  (passed)

Notes:

- This module is a crate-root facade. Native Linux sandbox execution remains
  owned by sibling modules such as `src/linux_run_main.rs`, `src/bwrap.rs`, and
  `src/landlock.rs`; those modules are not part of this turn.
