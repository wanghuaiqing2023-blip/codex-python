# codex-app-server/src/bin/notify_capture.rs alignment

Status: `complete`

Rust module: `codex/codex-rs/app-server/src/bin/notify_capture.rs`

Python module: `pycodex/app_server/bin/notify_capture.py`

Python tests: `tests/test_app_server_bin_notify_capture_rs.py`

## Behavior Contract

This module owns the `codex-app-server-test-notify-capture` binary helper
registered in `codex-app-server/Cargo.toml`.

The Python projection mirrors the module-scoped behavior:

- Skip the program argument and require exactly two arguments:
  `output_path` and `payload`.
- Preserve Rust's error strings for missing output path, missing payload, and
  extra arguments.
- Convert the payload with lossy text semantics.
- Build the temp path as `"{output_path}.tmp"`, matching Rust
  `format!("{}.tmp", output_path.display())`.
- Write payload bytes to the temp file, flush and fsync it, then move the temp
  file into the output path.

## Boundaries

- Rust `anyhow::Context` error wrapping for concrete filesystem failures is
  represented by normal Python filesystem exceptions.
- Platform-specific `std::fs::rename` overwrite behavior is approximated with
  `os.replace`; the module contract here is the write-through-temp then move
  sequence.
- `src/bin/test_notify_capture.rs` is a separate Rust module and is not part of
  this alignment slice.

## Evidence

- Rust source: `codex/codex-rs/app-server/src/bin/notify_capture.rs`
- Cargo binary registration: `codex/codex-rs/app-server/Cargo.toml`
- Python parity tests: `tests/test_app_server_bin_notify_capture_rs.py`

- `python -m pytest tests/test_app_server_bin_notify_capture_rs.py -q`
  passed on 2026-06-19 with 7 tests.
- `python -m py_compile pycodex/app_server/bin/notify_capture.py
  tests/test_app_server_bin_notify_capture_rs.py` passed on 2026-06-19.
