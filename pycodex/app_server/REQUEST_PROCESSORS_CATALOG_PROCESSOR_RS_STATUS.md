# request_processors/catalog_processor.rs Status

Rust module: `codex-app-server/src/request_processors/catalog_processor.rs`

Python module: `pycodex/app_server/request_processors_catalog_processor.py`

Status: `complete`

## Covered Contract

- Catalog processor construction keeps Rust's injected auth manager, thread
  manager, config, config manager, and workspace-settings cache boundaries.
- Model and collaboration-mode list helpers preserve Rust's thread-manager
  delegation and list response projection.
- Shared pagination mirrors Rust cursor parsing, `limit` clamping, empty-list
  handling, next-cursor calculation, and invalid cursor error messages for
  models, feature flags, and permission profiles.
- Permission-profile listing prepends Rust's three built-in profiles, reads
  configured profiles from effective config, sorts configured ids, and returns
  paged `PermissionProfileListResponse` data.
- Experimental-feature listing maps feature specs to protocol stage/display
  fields, applies config enablement, gates app/plugin feature enablement behind
  workspace settings, and falls back to enabled workspace plugins when the
  workspace-settings lookup fails.
- Skill, hook, skill-error, and hook-error projection helpers preserve the
  metadata fields owned by the Rust module without implementing plugin or hook
  runtime discovery.
- `skills/config/write` validates exactly one selector (`path` or non-empty
  `name`), applies an injected config edit, clears injected caches, and returns
  the effective enabled value.
- `mock/experimentalMethod` echoes the request value like the Rust helper.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/catalog_processor.rs`
- Python parity tests staged in
  `tests/test_app_server_request_processors_catalog_processor_rs.py`.
- Focused validation completed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_catalog_processor_rs.py -q`
  -> 10 passed.
- Syntax validation completed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_catalog_processor.py tests/test_app_server_request_processors_catalog_processor_rs.py`.

## Known Gaps

- Real skill discovery, hook discovery, plugin-root loading, and config edit
  persistence remain injected runtime boundaries owned by neighboring app-server
  modules and extension areas.
- Thread-id parsing is represented through the injected thread manager boundary;
  the concrete Rust `ThreadId` parser is not duplicated here.
