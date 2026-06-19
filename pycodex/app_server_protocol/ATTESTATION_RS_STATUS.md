# app-server-protocol `protocol/v2/attestation.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/attestation.rs`

Python target: `pycodex/app_server_protocol/attestation.py`

Status: implemented module contract.

## Covered Rust items

- `AttestationGenerateParams`
- `AttestationGenerateResponse`

## Notes

- `AttestationGenerateParams` is an empty defaultable params object, matching
  Rust's empty `Default` struct.
- `AttestationGenerateResponse` preserves the required opaque `token` string.
- `to_mapping()` and `to_camel_mapping()` are identical because this module's
  only serialized field is already the same under Rust camelCase rules.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/attestation.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: constructed empty params and round-tripped a token response.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
