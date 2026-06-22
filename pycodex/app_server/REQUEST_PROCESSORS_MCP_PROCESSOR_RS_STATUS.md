# request_processors/mcp_processor.rs alignment status

Rust source: `codex/codex-rs/app-server/src/request_processors/mcp_processor.rs`

Python module: `pycodex/app_server/request_processors_mcp_processor.py`

Python tests: `tests/test_app_server_request_processors_mcp_processor_rs.py`

Status: `complete`

## Covered behavior

- `McpRequestProcessor::new` dependency storage and wrapper method response
  shapes for refresh, status list, resource read, tool call, and OAuth login.
- `mcp_server_refresh_response` queue delegation and internal-error text.
- `load_latest_config` and `load_thread` error mapping for reload, invalid
  thread id, and missing thread.
- OAuth login request validation for missing server and non-streamable-HTTP
  transports, plus request/server/discovered scope resolution and injected
  login boundary response projection.
- MCP status-list snapshot projection: detail default, server-name union,
  sorted/deduped order, cursor parsing, cursor-past-total errors, pagination,
  and unsupported auth default.
- Resource read routing for thread-bound and threadless paths through injected
  runtime boundaries, with response deserialization/internal-error mapping.
- Tool-call routing through loaded threads, `threadId` metadata injection, core
  result conversion, and internal-error forwarding.
- Already-mapped JSON-RPC error forwarding for resource-read responses.

## Intentional boundaries

- Real MCP status collection, resource reading without a thread, OAuth browser
  login, async task spawning, and concrete MCP server/tool execution are
  injected runtime dependencies.
- Tokio task scheduling is represented as deterministic awaited calls in
  Python tests; the observable request/response and notification contracts are
  preserved at this module boundary.
- Full plugin/MCP runtime implementation remains outside this module-scoped
  acceptance unit.

## Validation

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_mcp_processor_rs.py -q`
  -> 10 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_mcp_processor.py tests/test_app_server_request_processors_mcp_processor_rs.py`.
