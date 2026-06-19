# codex-test-binary-support test alignment

Rust crate: `codex-test-binary-support`

Python package: `pycodex/test_binary_support`

Status: `complete`

Certified modules:

- `codex/codex-rs/test-binary-support/lib.rs` -> `pycodex/test_binary_support/__init__.py`

Source-contract coverage:

- `TestBinaryDispatchMode::DispatchArg0Only` delegates to `codex_arg0::arg0_dispatch` and returns no guard.
- `TestBinaryDispatchMode::Skip` returns no guard and does not invoke arg0 handlers.
- `TestBinaryDispatchMode::InstallAliases` creates a temporary `CODEX_HOME`, delegates alias creation to arg0 dispatch, restores the prior `CODEX_HOME`, and returns a guard.
- `TestBinaryDispatchGuard::paths` exposes the installed `Arg0DispatchPaths`.
- classifier input uses `argv0` file name and optional `argv1` string.

Validation:

- `python -m pytest tests/test_test_binary_support_lib_rs.py -q`
- `python -m py_compile pycodex/test_binary_support/__init__.py tests/test_test_binary_support_lib_rs.py`
