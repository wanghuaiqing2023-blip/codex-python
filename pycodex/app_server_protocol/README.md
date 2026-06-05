# pycodex.app_server_protocol

Canonical Python package for selected protocol types ported from:

- Rust crate: `codex/codex-rs/app-server-protocol`
- Current module: `pycodex/app_server_protocol/apps.py`

This package currently contains the `AppInfo` shape used by connector and tool-discovery paths.

## Module correspondence

| Rust module | Python module |
| --- | --- |
| `protocol/v2/apps.rs` | `pycodex/app_server_protocol/apps.py` |
| MCP elicitation protocol structs used by tools | `pycodex/app_server_protocol/elicitation.py` |
