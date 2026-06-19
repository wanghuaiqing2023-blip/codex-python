# codex-app-server src/analytics_utils.rs alignment

Rust module:

`codex/codex-rs/app-server/src/analytics_utils.rs`

Python target:

`pycodex/app_server/analytics_utils.py`

Status: `complete`

## Covered

- `analytics_events_client_from_config_projection(...)` mirrors the
  app-server-owned constructor argument shaping for
  `AnalyticsEventsClient::new(...)`: pass through the auth manager, trim all
  trailing `/` characters from `config.chatgpt_base_url`, and pass
  `config.analytics_enabled`.
- The projection accepts object- and mapping-shaped configs so the current
  runtime projections can share this module without depending on a concrete
  `codex-core::Config` port.

## Deferred dependency/runtime boundaries

- `AnalyticsEventsClient` queueing, event encoding, and transport behavior are
  owned by the sibling `codex-analytics` crate and are not implemented here.
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

- 2026-06-19: `python -m pytest tests/test_app_server_analytics_utils_rs.py -q`
  -> `2 passed`.
- 2026-06-19: `python -m py_compile
  pycodex/app_server/analytics_utils.py
  tests/test_app_server_analytics_utils_rs.py`.
