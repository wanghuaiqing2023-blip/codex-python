# pycodex.tools

Canonical Python package for selected helpers ported from the Rust workspace crate:

- Rust crate: `codex/codex-rs/tools`
- Python package: `pycodex/tools`

This package currently contains focused helper behavior needed by the common runtime path. It is not a full port of every Rust tools crate entrypoint.

## Module correspondence

| Rust module | Python module |
| --- | --- |
| `src/image_detail.rs` | `pycodex/tools/original_image_detail.py` |
| `src/tool_discovery.rs` | `pycodex/tools/tool_discovery.py` |

| `src/request_plugin_install.rs` | `pycodex/tools/request_plugin_install.py` |
