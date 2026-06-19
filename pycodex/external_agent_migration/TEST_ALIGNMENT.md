# codex-external-agent-migration test alignment

Rust crate: `codex-external-agent-migration`

Python package: `pycodex/external_agent_migration`

Status: `complete`

Certified modules:

- `codex/codex-rs/external-agent-migration/src/lib.rs` -> `pycodex/external_agent_migration/__init__.py`
- Rust `#[cfg(test)] mod tests` in `src/lib.rs` -> `tests/test_external_agent_migration_lib_rs.py`

Rust behavior covered by `tests/test_external_agent_migration_lib_rs.py`:

- MCP server migration skips placeholder args, unsupported transports, and
  disabled servers.
- Project-local and home-level `.claude.json` project entries are merged with
  repo-local server precedence.
- Hook migration filters unsupported hook groups/handlers, honors
  `disableAllHooks` and `settings.local.json` override semantics, rewrites
  static `.claude/hooks` paths, writes `hooks.json`, and copies hook scripts
  without overwriting existing target scripts.
- Subagent import validates required frontmatter/body fields, accepts CRLF
  delimiters, preserves dotted source stems, maps effort/permission metadata,
  and rewrites Claude terminology.
- Command import preserves nested command paths in skill names, skips runtime
  expansion and slug collisions, writes `SKILL.md`, and rewrites migrated
  command descriptions/templates.
- External-agent term rewriting follows case-insensitive word-boundary
  replacement behavior.

Validation:

- `python -m pytest tests/test_external_agent_migration_lib_rs.py -q` (`11 passed`)
- `python -m py_compile pycodex/external_agent_migration/__init__.py tests/test_external_agent_migration_lib_rs.py` (passed)
