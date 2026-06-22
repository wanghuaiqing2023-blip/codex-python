# codex-config `src/mcp_edit.rs` alignment

Status: `complete_candidate`

Rust owner: `codex-config`

Rust module: `codex/codex-rs/config/src/mcp_edit.rs`

Rust tests: `codex/codex-rs/config/src/mcp_edit_tests.rs`

Python module: `pycodex/config/mcp_edit.py`

Python tests: `tests/test_config_mcp_edit.py`

## Behavior Contract

`src/mcp_edit.rs` owns global MCP server config loading and persistence edits
for `$CODEX_HOME/config.toml`.

The Python port mirrors the module-scoped contract:

- Missing config files and configs without `mcp_servers` load as an empty map.
- Invalid TOML and invalid MCP server shapes fail before returning config.
- Inline `bearer_token` entries are rejected with the Rust guidance to use
  `bearer_token_env_var`.
- `ConfigEditsBuilder` supports replacing the complete `mcp_servers` table and
  creating the config home directory before writing.
- Empty replacement removes the `mcp_servers` table while preserving other
  config fields.
- Stdio server serialization preserves command, args, sorted env table,
  env var names/config entries, cwd, enabled/required flags, timeouts, and
  tool filters.
- Streamable HTTP serialization preserves URL, bearer token env var, sorted
  header tables, OAuth client id, OAuth resource, and scopes.
- Per-server and per-tool approval modes serialize using Rust wire values.
- Server and nested tool entries are emitted in deterministic sorted order.

## Notes

The Python implementation uses the local dependency-light TOML compatibility
layer and a small serializer instead of `toml_edit::DocumentMut`. The module
contract is preserved for the config shapes and stable snapshots currently
covered by Rust tests; exact whitespace preservation for arbitrary existing
documents is an intentional adaptation.

## Validation

Not run in this turn. Current automation defers actual pytest execution until
`codex-config` functional code is complete.
