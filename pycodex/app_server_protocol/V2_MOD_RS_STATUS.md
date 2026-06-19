# protocol/v2/mod.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/mod.rs`

Python module: `pycodex/app_server_protocol/__init__.py`

Status: complete for the module-scoped v2 protocol aggregation contract.

## Covered

- Rust v2 submodule declaration boundary for account, apps, attestation,
  collaboration mode, command exec, config, environment, experimental feature,
  feedback, filesystem, hook, item, MCP, model, notification, permissions,
  plugin, process, realtime, remote control, review, shared, thread,
  thread-data, turn, and Windows sandbox modules.
- Rust `pub use ...::*` behavior is mirrored by importing each completed Python
  protocol module into `pycodex.app_server_protocol`.
- `__all__` is maintained as the package-level public surface corresponding to
  Rust's v2 re-export surface.

## Intentional Adaptations

- Python uses a package `__init__.py` instead of a separate `mod.py` file.
- Rust's `#[cfg(test)] mod tests` declaration is not part of the aggregation
  implementation contract; v2 tests remain crate validation work.
- Crate-level JSON schema/export modules are outside `protocol/v2/mod.rs`.

## Validation

- `python -m py_compile pycodex/app_server_protocol/__init__.py`
- Focused smoke imported representative names from every completed v2 protocol
  module and verified every `__all__` entry is present on the package.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
