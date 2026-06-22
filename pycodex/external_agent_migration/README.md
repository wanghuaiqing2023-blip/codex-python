# codex-external-agent-migration

Rust crate: `codex-external-agent-migration`

Rust anchor: `codex/codex-rs/external-agent-migration`

Current certified modules:

- `external-agent-migration/src/lib.rs`

Python maps the crate's single module to
`pycodex/external_agent_migration/__init__.py`. The implementation covers the
Rust public migration helpers for MCP server config projection, hook migration
description/import, subagent import/counting, command skill import/counting,
and external-agent term rewriting.

The Rust crate's private helpers remain Python-internal. TOML-shaped Rust
`TomlValue` returns are represented as plain Python dictionaries so callers can
merge or serialize them with their existing config layer.

Remaining Rust modules: none.
