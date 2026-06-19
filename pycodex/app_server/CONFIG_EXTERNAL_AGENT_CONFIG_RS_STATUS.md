# codex-app-server/src/config/external_agent_config.rs alignment

Status: `complete`

Rust module: `codex/codex-rs/app-server/src/config/external_agent_config.rs`

Python module: `pycodex/app_server/config/external_agent_config.py`

Python tests: `tests/test_app_server_config_external_agent_config_rs.py`

## Behavior contract

This slice maps the dependency-light behavior owned by the external-agent
config migration module:

- migration constants and core data shapes;
- default external-agent home selection;
- recursive settings merge semantics;
- enabled plugin and marketplace-source collection, including official
  marketplace fallback and relative local source resolution;
- case-insensitive term rewriting with ASCII word-boundary checks;
- supported external settings projection into Codex config tables;
- environment JSON value stringification;
- missing-only TOML table merge behavior;
- migrated MCP server name extraction, named migration construction, empty-table
  detection, and metric tag construction;
- external session source path canonicalization for existing `.jsonl` files
  under the external agent `projects` root.

Full filesystem migration, real session detection, MCP/hook/subagent/command
imports, marketplace install policy, and async plugin import execution remain
runtime boundaries for later crate-level validation.

## Evidence

- Rust source: `codex/codex-rs/app-server/src/config/external_agent_config.rs`
- Rust tests: `codex/codex-rs/app-server/src/config/external_agent_config_tests.rs`
- Python parity tests: `tests/test_app_server_config_external_agent_config_rs.py`

- `python -m pytest tests/test_app_server_config_external_agent_config_rs.py -q`
  passed on 2026-06-19 with 14 tests.
- `python -m py_compile pycodex/app_server/config/external_agent_config.py
  tests/test_app_server_config_external_agent_config_rs.py` passed on
  2026-06-19.
