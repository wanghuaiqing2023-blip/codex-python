# codex-v8-poc test alignment

Rust crate: `codex-v8-poc`

Python package: `pycodex/v8_poc`

Status: `complete`

Certified modules:

- `codex/codex-rs/v8-poc/src/lib.rs` -> `pycodex/v8_poc/__init__.py`

Rust behavior covered by `tests/test_v8_poc_lib_rs.py`:

- `bazel_target()` returns `//codex-rs/v8-poc:v8-poc`.
- `embedded_v8_version()` returns a non-empty version marker.
- `linked_v8_has_sandbox()` defaults to false and can be enabled with the
  Python facade environment flag.
- the Rust smoke-test expressions `1 + 2` and `'hello ' + 'world'` evaluate to
  the same string results through the dependency-light facade.
- CRDTP dispatchable smoke data exposes `ok`, call id, and method bytes.

Validation:

- `python -m pytest tests/test_v8_poc_lib_rs.py -q` (`8 passed`)
- `python -m py_compile pycodex/v8_poc/__init__.py tests/test_v8_poc_lib_rs.py` (passed)
