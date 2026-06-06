# pycodex.utils.plugins

Canonical Python package for helpers ported from the Rust utility crate:

- Rust crate path: `codex/codex-rs/utils/plugins`
- Python package path: `pycodex/utils/plugins`

## Module correspondence

| Rust module | Python module |
| --- | --- |
| `src/lib.rs` | `pycodex/utils/plugins/__init__.py` |
| `src/mcp_connector.rs` | `pycodex/utils/plugins/mcp_connector.py` |
| `src/mention_syntax.rs` | `pycodex/utils/plugins/mention_syntax.py` |
| `src/plugin_namespace.rs` | `pycodex/utils/plugins/plugin_namespace.py` |

## Alignment Unit

The acceptance unit is the crate public utility surface:

```text
utils.plugins.mention_syntax_sigils
utils.plugins.mcp_connector_sanitize_name
utils.plugins.mcp_connector_allowed_ids
utils.plugins.plugin_namespace_manifest_discovery
utils.plugins.plugin_namespace_alternate_manifest
utils.plugins.plugin_skill_root_shape
```

## Current Status

Status: module_completed_with_focused_validation.

The Python package covers the Rust public exports from `src/lib.rs`:
plaintext mention sigils, MCP connector name/ID helpers, plugin manifest
discovery, plugin namespace resolution from skill paths, and `PluginSkillRoot`.
Rust's namespace helper is async over `ExecutorFileSystem`; Python provides the
standard-library local filesystem counterpart because the active port target
does not implement the full plugin/MCP filesystem runtime.

`pycodex.connectors.metadata.sanitize_name` remains an existing connector-crate
compatibility export with the same slugging semantics. Callers do not need to
move, but new `codex-utils-plugins`-coordinate work should import from this
package.

## Test Sources

Rust source and tests:

```text
codex/codex-rs/utils/plugins/src/lib.rs
codex/codex-rs/utils/plugins/src/mcp_connector.rs
codex/codex-rs/utils/plugins/src/mention_syntax.rs
codex/codex-rs/utils/plugins/src/plugin_namespace.rs
```

Python parity tests:

```text
tests/test_core_mention_syntax.py
```

## Stop Rule

This module contract is complete once `tests/test_core_mention_syntax.py` and
the connector metadata focused tests pass. Do not rescan this slice unless a
related test fails, Rust source changes, or a future task explicitly targets
plugin utility behavior.
