# codex-bwrap test alignment

Rust crate: `codex-bwrap`

Python package: `pycodex/bwrap`

Status: `complete`

Certified modules:

- `codex/codex-rs/bwrap/src/main.rs` -> `pycodex/bwrap/__init__.py`

Rust-test/source-contract coverage:

- non-Linux branch panics with `bwrap is only supported on Linux`.
- Linux without `bwrap_available` panics with the Rust build-unavailable message.
- Linux with `bwrap_available` validates argv as CString-compatible and forwards argv to a runner.
- embedded NUL bytes in argv fail before runner invocation, matching Rust `CString::new(...).unwrap_or_else(...)`.

Validation:

- `python -m pytest tests/test_bwrap_main_rs.py -q`
- `python -m py_compile pycodex/bwrap/__init__.py tests/test_bwrap_main_rs.py`
