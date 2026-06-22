# codex-v8-poc src/lib.rs status

Rust coordinate: `codex/codex-rs/v8-poc/src/lib.rs`

Python coordinate: `pycodex/v8_poc/__init__.py`

Status: `complete`

Behavior contract:

- expose the proof-of-concept Bazel target label.
- expose a non-empty embedded V8 version marker.
- expose whether the linked V8 sandbox feature is enabled.
- preserve the Rust smoke-test behavior for simple expression evaluation and
  CRDTP dispatchable-message parsing without introducing a Python V8
  dependency.

Validation:

- `python -m pytest tests/test_v8_poc_lib_rs.py -q` (`8 passed`)
- `python -m py_compile pycodex/v8_poc/__init__.py tests/test_v8_poc_lib_rs.py` (passed)
