# 2026-06-06 canonical migration batch 11: tools/request_plugin_install split

## Scope

Split request-plugin-install protocol/data helpers out of `pycodex.core.request_plugin_install` into canonical Rust crate coordinates.

## Rust source coordinates

- `codex/codex-rs/tools/src/request_plugin_install.rs`
- `codex/codex-rs/app-server-protocol` MCP elicitation structs used by that helper
- `codex/codex-rs/core/src/tools/handlers/request_plugin_install*.rs` remains represented by `pycodex/core/request_plugin_install.py`

## Python target coordinates

- `pycodex/tools/request_plugin_install.py`
- `pycodex/app_server_protocol/elicitation.py`
- `pycodex/core/request_plugin_install.py` remains for core handler/spec/persistence behavior only

## Migration policy

This is a split, not a full file deletion: the old core file now maps to Rust core handler behavior, while protocol helpers live under `pycodex.tools` and app-server protocol shapes under `pycodex.app_server_protocol`.

## Validation

- Focused tests: 94 passed.
- Import smoke for `pycodex.tools.request_plugin_install`, `pycodex.app_server_protocol.elicitation`, and dependent core modules: passed.
- Exact residual import check: no moved request-plugin-install protocol symbols are imported from `pycodex.core` or `pycodex.core.request_plugin_install`.

## Deletion decision

No file deletion in this batch: `pycodex/core/request_plugin_install.py` remains because it now maps to Rust core handler/spec/persistence behavior, not the `codex-tools` protocol helper module.
