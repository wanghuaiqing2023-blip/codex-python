# codex-app-server/src/config/mod.rs alignment

Status: `complete`

Rust module: `codex/codex-rs/app-server/src/config/mod.rs`

Python module: `pycodex/app_server/config/__init__.py`

Python tests: `tests/test_app_server_config_mod_rs.py`

## Behavior contract

This parent module only declares one crate-private child module:

```rust
pub(crate) mod external_agent_config;
```

Python mirrors the namespace shape with `pycodex.app_server.config`, records the
child module name, target Python child path, and `pub(crate)` visibility. The
child module's migration/config behavior remains owned by
`src/config/external_agent_config.rs` and is intentionally outside this module
slice.

## Evidence

- Rust source: `codex/codex-rs/app-server/src/config/mod.rs`
- Python parity test: `tests/test_app_server_config_mod_rs.py`

- `python -m pytest tests/test_app_server_config_mod_rs.py -q` passed on
  2026-06-19 with 1 test.
- `python -m py_compile pycodex/app_server/config/__init__.py
  tests/test_app_server_config_mod_rs.py` passed on 2026-06-19.
