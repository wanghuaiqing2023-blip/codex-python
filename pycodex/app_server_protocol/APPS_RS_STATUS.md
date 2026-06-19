# app-server-protocol `protocol/v2/apps.rs`

Rust source: `codex/codex-rs/app-server-protocol/src/protocol/v2/apps.rs`

Python target: `pycodex/app_server_protocol/apps.py`

Status: implemented module contract.

## Covered Rust items

- `AppsListParams`
- `AppBranding`
- `AppReview`
- `AppScreenshot`
- `AppMetadata`
- `AppInfo`
- `AppSummary`
- `From<AppInfo> for AppSummary` via `AppInfo.to_summary()` and
  `AppSummary.from_app_info()`
- `AppsListResponse`
- `AppListUpdatedNotification`

## Notes

- Python attributes stay snake_case for existing callers.
- `from_mapping()` accepts snake_case and Rust serde camelCase keys.
- `to_camel_mapping()` emits Rust wire names for protocol-shaped JSON.
- `AppInfo.is_enabled` mirrors Rust's `default_enabled` and defaults to
  `True`; `is_accessible`, `plugin_display_names`, and
  `AppsListParams.force_refetch` mirror Rust defaults.

## Validation

- Compile check only: `python -m py_compile
  pycodex/app_server_protocol/__init__.py
  pycodex/app_server_protocol/apps.py`.
- Per current project instruction, full tests are deferred until the
  crate's functional code is complete.
