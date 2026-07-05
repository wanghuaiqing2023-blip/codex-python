# app-server-protocol `protocol/v2/experimental_feature.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/experimental_feature.rs`

Python target: `pycodex/app_server_protocol/experimental_feature.py`

Status: implemented module contract.

## Covered Rust items

- `ExperimentalFeatureListParams`
- `ExperimentalFeatureStage`
- `ExperimentalFeature`
- `ExperimentalFeatureListResponse`
- `ExperimentalFeatureEnablementSetParams`
- `ExperimentalFeatureEnablementSetResponse`

## Notes

- `ExperimentalFeatureStage` values mirror Rust `serde(rename_all =
  "camelCase")`, including `underDevelopment`.
- List params support Rust camelCase `threadId` and Python snake_case
  `thread_id`.
- Enablement maps preserve the Rust `BTreeMap<String, bool>` shape as a
  string-to-bool dict; params default to an empty map.

## Validation

- Compile check: `python -m py_compile
  pycodex/app_server_protocol/experimental_feature.py
  pycodex/app_server_protocol/__init__.py`.
- Smoke check: parsed stage values, list params/response pagination, default
  empty enablement params, and enablement response mapping.
- Full tests deferred per instruction until this crate's functional protocol
  surface is complete.
