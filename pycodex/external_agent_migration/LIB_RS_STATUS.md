# external-agent-migration/src/lib.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/external-agent-migration/src/lib.rs`

Python target:

- `pycodex/external_agent_migration/__init__.py`

Implemented public API:

- `build_mcp_config_from_external`
- `hooks_migration_description`
- `hook_migration_event_names`
- `import_hooks`
- `count_missing_subagents`
- `missing_subagent_names`
- `import_subagents`
- `count_missing_commands`
- `missing_command_names`
- `import_commands`
- `rewrite_external_agent_terms`

Notes:

- Rust `TomlValue` outputs are represented as Python dictionaries.
- Private Rust parsing/rendering/path helpers are intentionally kept as Python
  internal helpers.
- The module depends only on standard library behavior plus the already ported
  `pycodex.hooks` event-name constants.

Validation:

- `python -m pytest tests/test_external_agent_migration_lib_rs.py -q`
- `python -m py_compile pycodex/external_agent_migration/__init__.py tests/test_external_agent_migration_lib_rs.py`
