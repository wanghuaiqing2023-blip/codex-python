# codex-linux-sandbox src/bazel_bwrap.rs status

Rust module: `codex/codex-rs/linux-sandbox/src/bazel_bwrap.rs`

Python module: `pycodex/linux_sandbox/bazel_bwrap.py`

Status: `complete_candidate`

Implemented behavior:

- Debug/Bazel/runfiles gating for `candidate()`.
- Absolute `CARGO_BIN_EXE_bwrap` path return.
- Relative runfile lookup under `RUNFILES_DIR` and `TEST_SRCDIR`.
- `TEST_WORKSPACE` logical path fallback.
- `RUNFILES_MANIFEST_FILE` key/value lookup.

Adaptation note:

- Rust uses compile-time `option_env!("BAZEL_PACKAGE")`; Python exposes
  `bazel_package_present` and falls back to an environment-key shim for tests.

Validation:

- `python -m py_compile pycodex/linux_sandbox/bazel_bwrap.py tests/test_linux_sandbox_bazel_bwrap_rs.py`
  (passed)

Focused pytest remains deferred until the remaining linux-sandbox functional
modules are complete.
