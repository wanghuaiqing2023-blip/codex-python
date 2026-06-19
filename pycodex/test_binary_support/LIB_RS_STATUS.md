# codex-test-binary-support lib.rs status

Rust coordinate: `codex/codex-rs/test-binary-support/lib.rs`

Python coordinate: `pycodex/test_binary_support/__init__.py`

Status: `complete`

Behavior contract:

- expose `TestBinaryDispatchGuard`, `TestBinaryDispatchMode`, and `configure_test_binary_dispatch`.
- derive classifier inputs from `argv0` file name and optional `argv1`.
- support dispatch-arg0-only, skip, and install-aliases modes.
- install aliases through the arg0 crate and restore the previous `CODEX_HOME`.
- keep the temporary home and arg0 guard alive until the returned guard is closed.

Evidence:

- `tests/test_test_binary_support_lib_rs.py` covers all mode branches, classifier input shape, guard path access, and env restoration.
