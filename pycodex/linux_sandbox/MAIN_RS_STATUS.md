# codex-linux-sandbox src/main.rs status

Status: `complete_candidate`

Rust module: `codex/codex-rs/linux-sandbox/src/main.rs`

Python module: `pycodex/linux_sandbox/__main__.py`

Behavior covered:

- Binary entrypoint `main()` delegates directly to the crate-root `run_main()`.
- The entrypoint does not parse, normalize, or transform argv/cwd/env before
  delegation, matching Rust's tiny `main() -> !` wrapper.

Prepared tests:

- `tests/test_linux_sandbox_main_rs.py`

Validation:

- `python -m py_compile pycodex/linux_sandbox/__main__.py tests/test_linux_sandbox_main_rs.py`
  (passed)

Notes:

- Native sandbox setup and final `execv` behavior remain owned by sibling
  modules, especially `src/linux_run_main.rs`.
