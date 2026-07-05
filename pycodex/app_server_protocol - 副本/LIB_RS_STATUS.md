# lib.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/lib.rs`

Python module: `pycodex/app_server_protocol/__init__.py`

Status: partial root-surface audit complete.

## Covered

- Crate-root exports for completed Python modules:
  - `experimental_api::*`
  - `export::{GenerateTsOptions, generate_*}`
  - `jsonrpc_lite::*`
  - selected `protocol/v2::*`
  - `schema_fixtures::{SchemaFixtureOptions, read/write helpers}`
- Package-root `__all__` integrity for all currently exported names.

## Remaining Dependencies

`lib.rs` also re-exports Rust modules whose own Python module contracts are not
yet complete in this package:

- `protocol::common::*`
- `protocol::event_mapping::*`
- `protocol::item_builders::*`
- `protocol::thread_history::*`
- selected `protocol::v1::*`

These are separate module boundaries. They should be handled in later turns
one module at a time rather than implemented under the crate-root module.

## Validation

- Light validation only: package import smoke and `__all__` integrity check.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
