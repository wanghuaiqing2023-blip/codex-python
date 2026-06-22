# pycodex.uds

Python alignment target for Rust crate `codex-uds`.

Rust coordinates:

- `codex/codex-rs/uds/src/lib.rs`
- `codex/codex-rs/uds/src/lib_tests.rs`

Python mapping:

- `pycodex/uds/__init__.py`

Current status: complete.

Certified behavior:

- `prepare_private_socket_directory` creates the rendezvous directory and, on Unix, normalizes existing directory permissions to exact owner-only `0700`.
- `is_stale_socket_path` mirrors Rust platform behavior: Unix checks for socket file type, while Windows uses path existence because `uds_windows` uses a regular rendezvous path.
- `UnixListener` and `UnixStream` expose the async bind/accept/connect/read/write surface when Python's standard library exposes asyncio Unix socket APIs.

Focused validation:

- `python -m pytest tests/test_uds_lib_rs.py -q`
- `python -m py_compile pycodex/uds/__init__.py tests/test_uds_lib_rs.py`
