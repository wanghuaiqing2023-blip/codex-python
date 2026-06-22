# codex-app-server-protocol test alignment

This ledger records module-scoped Rust behavior contracts for
`codex-app-server-protocol` that have Python parity evidence.

Focused crate validation after functional modules were recorded:

`python -m compileall -q pycodex/app_server_protocol`

passed on 2026-06-17.

`python -m pytest tests/test_app_server_protocol_common.py -q`

passed on 2026-06-17 with `5 passed`.

## complete_slice

### `protocol/common.rs` JSON-RPC method and serialization-scope layer

- Rust owner: `codex-app-server-protocol`
- Rust module: `codex/codex-rs/app-server-protocol/src/protocol/common.rs`
- Python module: `pycodex/app_server_protocol/common.py`
- Python tests: `tests/test_app_server_protocol_common.py`
- Python status file: `pycodex/app_server_protocol/COMMON_RS_STATUS.md`
- Status: `complete_slice`
- Evidence: Rust local tests for keyed/unkeyed `ClientRequest::serialization_scope()`,
  serde method renames, `ServerNotification` method tags, and fuzzy-file-search
  payload shapes are mirrored by Python tests derived from
  `client_request_serialization_scope_covers_keyed_families`,
  `client_request_serialization_scope_covers_unkeyed_representatives`, and the
  Rust common enum/payload definitions.
- Focused validation: `python -m pytest tests/test_app_server_protocol_common.py -q`
  passed on 2026-06-17 with `5 passed`.

### Module status inventory

- Rust owner: `codex-app-server-protocol`
- Python package: `pycodex/app_server_protocol`
- Status: `complete_slice`
- Evidence: Every currently ported Rust module in this crate has a package
  README mapping and a module status file: `protocol/v2/*`, `protocol/v1.rs`,
  `protocol/common.rs`, `protocol/item_builders.rs`,
  `protocol/event_mapping.rs`, `protocol/thread_history.rs`,
  `jsonrpc_lite.rs`, `experimental_api.rs`, `schema_fixtures.rs`,
  `export.rs`, and crate-root `lib.rs`.
- Focused validation: package compile check
  `python -m compileall -q pycodex/app_server_protocol` passed on 2026-06-17.

## Known remaining gaps

- No known module-scoped functional gaps remain for the active
  `codex-app-server-protocol` protocol target.
- Runtime app-server transport, daemon, client, and server orchestration remain
  owned by separate crates and are not claimed by this protocol crate closeout.
