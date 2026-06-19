# request_processors/marketplace_processor.rs alignment status

Rust source: `codex/codex-rs/app-server/src/request_processors/marketplace_processor.rs`

Python module: `pycodex/app_server/request_processors_marketplace_processor.py`

Python tests: `tests/test_app_server_request_processors_marketplace_processor_rs.py`

Status: `complete`

## Covered behavior

- `MarketplaceRequestProcessor::new` dependency storage.
- `marketplace_add`, `marketplace_remove`, and `marketplace_upgrade`
  wrapper parameter parsing and response return shape.
- `marketplace_add_inner` request projection, including
  `sparse_paths.unwrap_or_default()`, and add-outcome response mapping.
- `marketplace_remove_inner` request projection and
  `removed_installed_root` to `installed_root` response mapping.
- add/remove `InvalidRequest` versus `Internal` JSON-RPC error mapping.
- `marketplace_upgrade_response_inner` latest-config load, plugins-manager
  lookup, `plugins_config_input()` call, selected marketplace forwarding, and
  selected/upgraded/error response projection.
- default `PluginsManager::upgrade_configured_marketplaces_for_config` call
  path and upgrade failure mapping through `invalid_request`.
- `load_latest_config` reload failure mapping to app-server internal error.

## Intentional boundaries

- Concrete `add_marketplace_to_codex_home`, `remove_marketplace`, repository
  IO, and git/network behavior remain injected runtime dependencies.
- Concrete `PluginsManager::upgrade_configured_marketplaces_for_config`
  implementation belongs to the plugin runtime boundary, not this request
  processor module.
- Tokio `spawn_blocking` scheduling and join-error behavior are represented by
  the injected callable boundary; real executor scheduling is not implemented
  here.

## Validation

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_marketplace_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_marketplace_processor.py tests/test_app_server_request_processors_marketplace_processor_rs.py`.
