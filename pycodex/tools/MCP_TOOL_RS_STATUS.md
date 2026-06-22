# codex-tools `src/mcp_tool.rs` alignment

Status: `complete_candidate`

Rust owner:

- Crate: `codex-tools`
- Module: `codex/codex-rs/tools/src/mcp_tool.rs`

Python owner:

- Module: `pycodex/tools/mcp_tool.py`

Behavior covered:

- `parse_mcp_tool(...)` accepts lightweight MCP tool mappings or MCP-like
  objects, preserves tool name and optional description, normalizes missing or
  null input-schema `properties` to `{}`, parses the input schema through the
  shared `codex-tools` JSON Schema parser, wraps output schema as the MCP
  call-tool result schema, and keeps `defer_loading = false`.
- `mcp_call_tool_result_output_schema(...)` mirrors Rust's object schema with
  `content`, `structuredContent`, `isError`, and `_meta`, with `content`
  required and `additionalProperties = false`.

Rust tests:

- `codex/codex-rs/tools/src/mcp_tool_tests.rs`

Python tests:

- Deferred by current crate automation rule until `codex-tools` functional
  module code is complete.
- Adjacent MCP result payload behavior is already exercised outside this module
  in `tests/test_core_tool_context.py` and `tests/test_protocol_mcp_dynamic_tools.py`.

Notes:

- This module intentionally stays dependency-light and does not implement MCP
  runtime behavior. It only mirrors the Rust tool-definition conversion helper.
