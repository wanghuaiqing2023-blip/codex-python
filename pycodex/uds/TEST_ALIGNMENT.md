# codex-uds test alignment

Rust crate: `codex-uds`

Python module: `pycodex/uds/__init__.py`

Status: `complete`

Certified module:

- `codex/codex-rs/uds/src/lib.rs`

Rust test source:

- `codex/codex-rs/uds/src/lib_tests.rs`

Rust-derived coverage:

- `prepare_private_socket_directory_creates_directory`
- `prepare_private_socket_directory_sets_existing_permissions_to_owner_only`
- `regular_file_path_is_not_stale_socket_path`
- `bound_listener_path_is_stale_socket_path`
- `stream_round_trips_data_between_listener_and_client`

Additional source-contract coverage:

- Existing non-directory socket directory path raises `FileExistsError`.
- Windows stale socket path detection uses existence as the signal.

Platform notes:

- The Rust crate implements Windows stream/listener behavior with the `uds_windows` crate. The Python port remains standard-library-only, so real stream/listener tests run only when Python exposes asyncio Unix socket APIs. On platforms without those APIs, tests skip the round-trip behavior while preserving the explicit unsupported-operation surface.

Validation:

- `python -m pytest tests/test_uds_lib_rs.py -q`
- `python -m py_compile pycodex/uds/__init__.py tests/test_uds_lib_rs.py`
