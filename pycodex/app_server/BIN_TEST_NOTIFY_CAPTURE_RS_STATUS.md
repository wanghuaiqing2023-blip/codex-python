# codex-app-server/src/bin/test_notify_capture.rs alignment

Status: `complete`

Rust module: `codex/codex-rs/app-server/src/bin/test_notify_capture.rs`

Python module: `pycodex/app_server/bin/test_notify_capture.py`

Python tests: `tests/test_app_server_bin_test_notify_capture_rs.py`

## Behavior Contract

This module owns the standalone Rust helper at
`src/bin/test_notify_capture.rs`.

The Python projection mirrors the module-scoped behavior:

- Skip the program argument and require `output_path` and `payload`.
- Preserve Rust's missing-argument error strings.
- Convert payload with strict UTF-8 semantics, including the
  `payload must be valid UTF-8` error.
- Build the temp path with `output_path.with_extension("json.tmp")`.
- Write payload text to the temp path, then move the temp file into the output
  path.
- Ignore extra arguments after payload, matching the Rust helper's first-two
  argument reads.

## Boundaries

- Rust `anyhow` filesystem error propagation is represented by normal Python
  filesystem exceptions.
- Platform-specific `std::fs::rename` overwrite behavior is approximated with
  `os.replace`; the local contract is the temp-write then move sequence.
- `src/bin/notify_capture.rs` is covered separately by
  `BIN_NOTIFY_CAPTURE_RS_STATUS.md`.

## Evidence

- Rust source: `codex/codex-rs/app-server/src/bin/test_notify_capture.rs`
- Python parity tests: `tests/test_app_server_bin_test_notify_capture_rs.py`

- `python -m pytest tests/test_app_server_bin_test_notify_capture_rs.py -q`
  passed on 2026-06-19 with 6 tests.
- `python -m py_compile pycodex/app_server/bin/test_notify_capture.py
  tests/test_app_server_bin_test_notify_capture_rs.py` passed on 2026-06-19.
