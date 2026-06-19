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

Status: complete.

Certified modules:

- `src/mention_syntax.rs`
- `src/mcp_connector.rs`
- `src/plugin_namespace.rs`
- `src/lib.rs`

The Python package already contains local counterparts for the Rust utility
surface, including the crate-root re-export surface and `PluginSkillRoot`.

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
tests/test_utils_plugins_mcp_connector.py
tests/test_utils_plugins_plugin_namespace.py
tests/test_utils_plugins_lib.py
```

## Stop Rule

This crate is complete after `src/lib.rs` crate-root certification and focused
validation for the plugin utility package.
