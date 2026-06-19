# protocol/v2/mcp.rs Alignment Status

Rust module: `codex/codex-rs/app-server-protocol/src/protocol/v2/mcp.rs`

Python module: `pycodex/app_server_protocol/mcp.py`

Status: complete for the module-scoped app-server protocol contract.

## Covered

- `McpAuthStatus`, `McpServerStatusDetail`, `McpServerStartupState`, and `McpServerElicitationAction` wire values.
- MCP server status list params/responses, including pagination, detail, thread id, auth status, tools, resources, and resource templates.
- MCP resource read params/responses.
- MCP tool-call params, app-server response, result, and error payloads, preserving `structuredContent`, `isError`, and `_meta`.
- Empty refresh params/responses.
- OAuth login params/responses and login completion notifications.
- Tool-call progress and MCP server status update notifications.
- Elicitation request params, request variants, request response, and JSON-schema wrapper types needed by the protocol.

## Intentional Adaptations

- MCP runtime models (`Tool`, `Resource`, `ResourceTemplate`, `ResourceContent`, content blocks, structured content, and metadata) stay as JSON-shaped Python values. The Rust module also treats several MCP result payloads as `serde_json::Value` for schema/export friendliness.
- `McpServerElicitationAction.to_core()` returns the stable wire string because the Python core does not yet expose an equivalent strongly typed RMCP action.
- `pycodex/app_server_protocol/elicitation.py` remains as a compatibility module for older imports, while top-level package exports now come from `mcp.py`.

## Validation

- `python -m py_compile pycodex/app_server_protocol/mcp.py pycodex/app_server_protocol/__init__.py`
- Focused smoke covered camelCase parsing/serialization, `_meta` preservation, tool-call response conversion, elicitation form/url variants, elicitation response mapping, and top-level package exports.

Full crate tests remain deferred until the `codex-app-server-protocol` functional code surface is complete.
