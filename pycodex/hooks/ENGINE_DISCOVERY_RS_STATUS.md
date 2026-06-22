# codex-hooks src/engine/discovery.rs Status

Rust crate: `codex-hooks`

Rust module: `codex/codex-rs/hooks/src/engine/discovery.rs`

Python target: `pycodex/hooks/__init__.py`

Status: `complete`

## Anchors

- `DiscoveryResult`
- `discover_handlers(...)`
- `append_matcher_groups(...)`
- `load_hooks_json(...)`
- `load_toml_hooks_from_layer(...)`
- `command_hook_hash(...)`
- `hook_trust_status(...)`
- `hook_enabled(...)`

## Python Coverage

- `tests/test_hooks_engine_discovery_rs.py` covers matcher normalization and
  validation, invalid matcher ignoring for events without matchers, persisted
  enabled state, trust bypass gating, commandWindows selection, star
  match-all matcher handling, list-entry trust state, and TOML hook parsing
  while malformed `hooks.state` entries are ignored.

## Validation

- `python -m pytest tests/test_hooks_engine_discovery_rs.py -q --tb=short`
  passed on 2026-06-21 with `8 passed`.
- Hooks module validation including discovery passed on 2026-06-21 with
  `146 passed`.
- Hooks plus core-hooks regression validation including discovery passed on
  2026-06-21 with `169 passed`.
- `python -m py_compile pycodex\hooks\__init__.py tests\test_hooks_engine_discovery_rs.py`
  passed.

## Remaining Debt

- None for this module-scoped behavior contract. Sibling `src/engine/mod.rs`
  remains a separate `codex-hooks` crate-level gap.
