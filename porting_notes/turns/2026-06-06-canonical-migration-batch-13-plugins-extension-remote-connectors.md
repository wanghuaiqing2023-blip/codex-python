# Canonical migration batch 13: plugins, extension tools, remote skills, connectors split

## Summary

Moved several already-implemented helper areas into Python coordinates that match their upstream Rust tree positions. This batch also split `pycodex/core/connectors.py`, because the old file mixed Rust `core/src/connectors.rs` behavior with Rust `codex-rs/connectors/src/*` behavior.

## Rust anchors and Python coordinates

| Rust anchor | Python coordinate |
|---|---|
| `codex/codex-rs/core-skills/src/remote.rs` | `pycodex/core_skills/remote.py` |
| `codex/codex-rs/core/src/tools/handlers/extension_tools.rs` | `pycodex/core/tools/handlers/extension_tools.py` |
| `codex/codex-rs/core/src/plugins/mentions.rs` | `pycodex/core/plugins/mentions.py` |
| `codex/codex-rs/connectors/src/accessible.rs` | `pycodex/connectors/accessible.py` |
| `codex/codex-rs/connectors/src/merge.rs` | `pycodex/connectors/merge.py` |
| `codex/codex-rs/connectors/src/metadata.rs` | `pycodex/connectors/metadata.py` |
| `codex/codex-rs/core/src/connectors.rs` | `pycodex/core/connectors.py` |

## Deleted old coordinates

- `pycodex/core/remote_skills.py`
- `pycodex/core/extension_tools.py`
- `pycodex/core/plugin_mentions.py`

## Retained old-looking coordinate

- `pycodex/core/connectors.py`

This file intentionally remains because Rust also has `codex-rs/core/src/connectors.rs`. It no longer owns connector-crate helper behavior; it calls `pycodex.connectors` through private aliases where the Rust core module would call `codex_connectors`.

## Validation

- Focused validation after deletion: `180 passed`, `4 subtests passed`
- Import smoke: passed
- Old import residual check: no matches for `pycodex.core.remote_skills`, `pycodex.core.extension_tools`, or `pycodex.core.plugin_mentions`
- Connector-crate helper residual check: no public old-coordinate imports remain

## Notes

`AppsConfig.from_mapping` and `AppsRequirements.from_mapping` now treat non-mapping Python test doubles as absent config. This keeps the Python compatibility layer tolerant of lightweight `SimpleNamespace` fixtures while preserving the Rust-level behavior boundary: real app policy is still driven by parsed config-shaped mappings.
