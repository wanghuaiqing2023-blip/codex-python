# codex-uds src/lib.rs status

Rust coordinate: `codex/codex-rs/uds/src/lib.rs`

Python coordinate: `pycodex/uds/__init__.py`

Status: complete.

Ported public API:

- `prepare_private_socket_directory`
- `is_stale_socket_path`
- `UnixListener.bind`
- `UnixListener.accept`
- `UnixStream.connect`
- async stream read/write helpers used by the Rust-derived behavior tests

Parity notes:

- Unix directory permission behavior mirrors Rust's exact `0700` owner-only normalization.
- Unix stale socket detection uses `lstat` plus socket-file-type detection, matching Rust `symlink_metadata(...).file_type().is_socket()`.
- Windows stale socket detection uses path existence, matching the Rust `uds_windows` rendezvous-path contract.
- Python's standard library has no `uds_windows` equivalent. Real listener/stream behavior is provided when `asyncio.start_unix_server` and `asyncio.open_unix_connection` are available; otherwise the socket round-trip tests are skipped as a platform capability boundary.

Rust-derived validation:

- `tests/test_uds_lib_rs.py`

Focused validation:

- `python -m pytest tests/test_uds_lib_rs.py -q`
- `python -m py_compile pycodex/uds/__init__.py tests/test_uds_lib_rs.py`
