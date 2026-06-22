# app-server-protocol `protocol/v2/shared.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/shared.rs`

Python target: `pycodex/app_server_protocol/shared.py`

Status: implemented module contract.

## Covered Rust items

- `default_enabled`
- `NonSteerableTurnKind`
- `CodexErrorInfo`
- `AskForApproval`
- `ApprovalsReviewer`
- `SandboxMode`

## Notes

- `CodexErrorInfo` preserves Rust's external enum JSON shape, including
  camelCase unit variants and object variants with `httpStatusCode` and
  `turnKind`.
- `GranularAskForApproval` models the Rust `AskForApproval::Granular` variant
  and defaults missing `skill_approval` and `request_permissions` fields to
  `False`, matching serde defaults.
- `ApprovalsReviewer.AUTO_REVIEW` serializes as `guardian_subagent` and accepts
  the `auto_review` alias during parsing.
- Core conversion helpers remain intentionally out of scope for this module
  pass; callers can bridge by reading the stable wire values.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/shared.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: reviewer serialization and alias parsing, granular approval
  defaults, error info camelCase serialization for HTTP and active-turn
  variants, and sandbox mode wire values.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
