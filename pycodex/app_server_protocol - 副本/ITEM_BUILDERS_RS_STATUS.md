# `protocol/item_builders.rs` Port Status

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/item_builders.rs`

Python module: `pycodex/app_server_protocol/item_builders.py`

## Status

Complete for the module-scoped behavior contract.

## Ported anchors

- `build_file_change_approval_request_item`
- `build_file_change_begin_item`
- `build_file_change_end_item`
- `build_command_execution_approval_request_item`
- `build_command_execution_begin_item`
- `build_command_execution_end_item`
- `build_item_from_guardian_event`
- `guardian_auto_approval_review_notification`
- `convert_patch_changes`
- patch change kind and diff formatting helpers

## Notes

- Python mirrors Rust's presentation projection into v2 `ThreadItem` tagged
  payloads, including sorted file changes, shell-style command display strings,
  parsed command actions, status/source enum mapping, aggregated output elision,
  and duration milliseconds.
- The module accepts core event dataclasses, mappings, or duck-typed payloads so
  dependency modules remain interface constraints instead of being pulled into
  this module's acceptance unit.
- `protocol/common.rs::ServerNotification` is not yet ported. A small local
  facade covers the two guardian auto-review notification variants emitted by
  this module; it should be replaced or aliased when `common.rs` is aligned.
- Full crate tests remain deferred until the crate's functional code is
  complete.

## Validation

- Light validation only: `py_compile` and focused import/builder smoke.
