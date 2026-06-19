# codex-tools `src/responses_api.rs` alignment

Status: `complete_candidate`

Rust owner:

- Crate: `codex-tools`
- Module: `codex/codex-rs/tools/src/responses_api.rs`

Python owner:

- Module: `pycodex/tools/responses_api.py`

Behavior covered:

- `FreeformTool`, `FreeformToolFormat`, `ResponsesApiTool`,
  `LoadableToolSpec`, `ResponsesApiNamespace`, and
  `ResponsesApiNamespaceTool` are represented as Python dataclasses with
  `to_mapping()` wire serialization.
- `tool_definition_to_responses_api_tool(...)` preserves name, description,
  schema, output schema, `strict = false`, and omits false `defer_loading`.
- `dynamic_tool_to_responses_api_tool(...)` delegates through the
  `codex-tools` dynamic tool parser so input schema normalization and
  `defer_loading` parity stay shared.
- `coalesce_loadable_tool_specs(...)` preserves functions and appends tools for
  repeated namespace names in input order.
- MCP conversion helpers provide a lightweight mapping/to_mapping compatibility
  path that renames to the model-facing `ToolName.name` and sets deferred
  loading for the deferred variant without implementing MCP runtime behavior.

Rust tests:

- `codex/codex-rs/tools/src/responses_api_tests.rs`

Python tests:

- Deferred by current crate automation rule until `codex-tools` functional
  module code is complete.
- Existing adjacent behavior coverage remains in:
  - `tests/test_core_dynamic_tool_handler.py`
  - `tests/test_core_tool_search_entry.py`
  - `tests/test_core_hosted_spec.py`

Notes:

- The MCP helpers intentionally stay as compatibility adapters. Full MCP
  runtime behavior remains outside the current core-first implementation
  priority.
