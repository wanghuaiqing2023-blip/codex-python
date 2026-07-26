# codex-app-server src/analytics_utils.rs alignment

Rust module:

`codex/codex-rs/app-server/src/analytics_utils.rs`

Python target:

`pycodex/app_server/analytics_utils.py`

Status: `complete`

## Covered

- `analytics_events_client_from_config(...)` returns the production
  `AnalyticsEventsClient` and mirrors the app-server-owned construction of
  `AnalyticsEventsClient::new(...)`: pass through the auth manager, trim all
  trailing `/` characters from `config.chatgpt_base_url`, and pass
  `config.analytics_enabled`.
- Object- and mapping-shaped configs are accepted at the existing Python
  `codex-core::Config` compatibility boundary.

## Deferred dependency/runtime boundaries

- `AnalyticsEventsClient` queueing, event encoding, and transport behavior are
  owned by the sibling `codex-analytics` crate.
- Auth manager behavior and config loading remain owned by their respective
  crates/modules.

## Evidence

- Rust source:
  `codex/codex-rs/app-server/src/analytics_utils.rs`
- Rust consumers:
  `codex/codex-rs/app-server/src/lib.rs`
- Python tests:
  `tests/test_app_server_analytics_utils_rs.py`

## Validation

- 2026-07-23: `python -B -m pytest -q
  tests/test_app_server_analytics_utils_rs.py` -> `2 passed`.
