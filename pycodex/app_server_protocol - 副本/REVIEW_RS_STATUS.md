# app-server-protocol `protocol/v2/review.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/review.rs`

Python target: `pycodex/app_server_protocol/review.py`

Status: implemented module contract.

## Covered Rust items

- `ReviewDelivery`
- `ReviewStartParams`
- `ReviewStartResponse`
- `ReviewTarget`

## Notes

- `ReviewDelivery` mirrors Rust `v2_enum_from_core!` camelCase serde values:
  `inline` and `detached`.
- `ReviewTarget` preserves Rust's tagged `type` enum shape for
  `uncommittedChanges`, `baseBranch`, `commit`, and `custom`.
- `ReviewStartResponse.turn` is treated as a Turn-compatible mapping/object.
  The owning `Turn` type lives in `protocol/v2/thread_data.rs` and remains a
  separate module boundary.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/review.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed all review target variants, delivery defaults/values,
  and start response turn mapping.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
