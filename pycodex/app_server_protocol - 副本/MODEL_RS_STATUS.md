# app-server-protocol `protocol/v2/model.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/model.rs`

Python target: `pycodex/app_server_protocol/model.py`

Status: implemented module contract.

## Covered Rust items

- `ModelRerouteReason`
- `ModelVerification`
- `ModelProviderCapabilitiesReadParams`
- `ModelProviderCapabilitiesReadResponse`
- `ModelListParams`
- `ModelAvailabilityNux`
- `ModelServiceTier`
- `Model`
- `ModelUpgradeInfo`
- `ReasoningEffortOption`
- `ModelListResponse`
- `ModelReroutedNotification`
- `ModelVerificationNotification`

## Notes

- Reroute and verification enums mirror the Rust `v2_enum_from_core!` wire
  values.
- Model list and response types accept Rust serde camelCase keys and emit Rust
  wire names through `to_camel_mapping()`.
- Model defaults mirror Rust serde defaults for input modalities, personality
  support, additional speed tiers, service tiers, default service tier, and
  default-model state.
- `ModelAvailabilityNux.from_core()` mirrors Rust's conversion from the core
  availability NUX shape by reading the `message` field.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/model.py pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed provider capabilities, model list params, default input
  modalities, model list response, reroute notification, and verification
  notification wire mappings.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
