# experimental_api.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/experimental_api.rs`

Python module: `pycodex/app_server_protocol/experimental_api.py`

Status: complete for the module-scoped experimental API helper contract.

## Covered

- `ExperimentalApi` protocol for values that can report an experimental reason.
- `ExperimentalField` metadata and camelCase/snake_case mapping helpers.
- `experimental_fields()` registry access and
  `experimental_required_message(reason)` formatting.
- Option-like `None`, list/tuple, and map value traversal through
  `experimental_reason(value)`.
- Small `ExperimentalReason` value helper for shims and focused smoke checks.

## Intentional Adaptations

- Rust derives `ExperimentalApi` and collects fields through `inventory`;
  Python uses explicit `register_experimental_field()` and
  `clear_experimental_fields()` helpers.
- This module does not implement Rust procedural macro behavior. It preserves
  the runtime helper contract available to protocol code.

## Validation

- `python -m py_compile pycodex/app_server_protocol/experimental_api.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered field registration/listing, required-message
  formatting, nested option/list/map traversal, stable values, and package
  exports.

Full crate tests remain deferred until the `codex-app-server-protocol`
functional code surface is complete.
