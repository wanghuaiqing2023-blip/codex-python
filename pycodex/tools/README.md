# pycodex.tools

Canonical Python package for selected helpers ported from the Rust workspace crate:

- Rust crate: `codex/codex-rs/tools`
- Python package: `pycodex/tools`

This package currently contains focused helper behavior needed by the common runtime path. It is not a full port of every Rust tools crate entrypoint.

## Module correspondence

| Rust module | Python module |
| --- | --- |
| `src/code_mode.rs` | `pycodex/tools/code_mode.py` |
| `src/dynamic_tool.rs` | `pycodex/tools/dynamic_tool.py` |
| `src/function_call_error.rs` | `pycodex/tools/function_call_error.py` |
| `src/image_detail.rs` | `pycodex/tools/original_image_detail.py` |
| `src/json_schema.rs` | `pycodex/tools/json_schema.py` |
| `src/lib.rs` | `pycodex/tools/__init__.py` |
| `src/mcp_tool.rs` | `pycodex/tools/mcp_tool.py` |
| `src/request_plugin_install.rs` | `pycodex/tools/request_plugin_install.py` |
| `src/response_history.rs` | `pycodex/tools/response_history.py` |
| `src/responses_api.rs` | `pycodex/tools/responses_api.py` |
| `src/tool_call.rs` | `pycodex/tools/tool_call.py` |
| `src/tool_config.rs` | `pycodex/tools/tool_config.py` |
| `src/tool_definition.rs` | `pycodex/tools/tool_definition.py` |
| `src/tool_discovery.rs` | `pycodex/tools/tool_discovery.py` |
| `src/tool_executor.rs` | `pycodex/tools/tool_executor.py` |
| `src/tool_output.rs` | `pycodex/tools/tool_output.py` |
| `src/tool_payload.rs` | `pycodex/tools/tool_payload.py` |
| `src/tool_spec.rs` | `pycodex/tools/tool_spec.py` |
