# codex-tools test alignment

This ledger records Rust module-scoped behavior contracts for `codex-tools`
as they are reconciled against Python modules and focused tests.

## complete_candidate

### `src/lib.rs` crate-root public surface

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/lib.rs`
- Rust tests: none directly; child module tests cover exported behavior
- Python module: `pycodex/tools/__init__.py`
- Python behavior implementation: child modules under `pycodex/tools`
- Python tests: deferred; crate-root import validation should run with final
  `codex-tools` crate validation
- Python status file: `pycodex/tools/LIB_RS_STATUS.md`
- Status: `complete`
- Evidence: Python package root now exposes Rust crate-root helpers and types,
  including `ToolName`, code-mode adapters, dynamic/MCP parsers, shared tool
  errors, image-detail helpers, JSON Schema helpers, request-plugin-install
  helpers, response-history helpers, Responses API primitives, and tool
  call/config/definition/discovery/executor/output/payload/spec exports.
- Focused validation: passed on 2026-06-17 with
  `313 passed, 2 skipped, 5 subtests passed` across the focused tools/core
  helper suite.

### `src/mcp_tool.rs` MCP tool definition parser

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/mcp_tool.rs`
- Rust tests: `codex/codex-rs/tools/src/mcp_tool_tests.rs`
- Python module: `pycodex/tools/mcp_tool.py`
- Python behavior implementation: `pycodex/tools/json_schema.py`,
  `pycodex/tools/tool_definition.py`
- Python tests: deferred; Rust-derived coverage should mirror
  `codex/codex-rs/tools/src/mcp_tool_tests.rs`
- Python status file: `pycodex/tools/MCP_TOOL_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust MCP tool parsing by inserting empty
  `properties` for missing/null input schemas, preserving tool name and
  description, parsing the input schema through the shared tools JSON Schema
  parser, wrapping output schema with the MCP call-tool result output schema,
  and keeping `defer_loading = false`.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/responses_api.rs` Responses API loadable tool primitives

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/responses_api.rs`
- Rust tests: `codex/codex-rs/tools/src/responses_api_tests.rs`
- Python module: `pycodex/tools/responses_api.py`
- Python behavior implementation: `pycodex/tools/dynamic_tool.py`,
  `pycodex/tools/tool_definition.py`,
  `pycodex/core/tools/tool_search_entry.py`,
  `pycodex/core/tools/handlers/dynamic.py`
- Python tests: deferred; Rust-derived coverage should mirror
  `codex/codex-rs/tools/src/responses_api_tests.rs`
- Python status file: `pycodex/tools/RESPONSES_API_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust Responses API tool dataclasses and wire
  mapping, tool-definition conversion, dynamic-tool conversion through the
  shared parser, false `defer_loading` omission, namespace child serialization,
  namespace coalescing by matching name, and lightweight MCP mapping adapters
  for direct and deferred tools.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_config.rs` tool configuration gates

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_config.rs`
- Rust tests: `codex/codex-rs/tools/src/tool_config_tests.rs`
- Python module: `pycodex/tools/tool_config.py`
- Python behavior implementation: `pycodex/core/tools/handlers/request_user_input.py`,
  `pycodex/core/tools/handlers/shell.py`,
  `pycodex/core/tools/handlers/unified_exec.py`,
  `pycodex/features/__init__.py`
- Python tests: deferred; Rust-derived coverage should mirror
  `codex/codex-rs/tools/src/tool_config_tests.rs`
- Python status file: `pycodex/tools/TOOL_CONFIG_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust feature-gated request-user-input mode
  selection, shell backend selection, model shell type normalization and
  unified-exec fallback, Unix-only zsh-fork shell-mode selection, and
  environment-count classification while reusing existing core runtime
  dataclasses/enums.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_executor.rs` shared tool runtime contract

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_executor.rs`
- Rust tests: none in `codex-tools`
- Python module: `pycodex/tools/tool_executor.py`
- Python behavior implementation: `pycodex/core/tools/registry.py`
- Python tests: `tests/test_core_tool_registry.py`,
  `tests/test_core_spec_plan.py`
- Python status file: `pycodex/tools/TOOL_EXECUTOR_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python exposes the canonical tools package path for
  `ToolExposure` and `ToolExecutor`, reusing the core enum whose variants,
  `is_direct`, default exposure, overrides, direct/deferred/hidden planning,
  and parallel-call gating are already covered by registry/spec-plan tests.
  The Python `ToolExecutor` protocol mirrors Rust's required `tool_name`,
  `spec`, and async `handle` methods plus default `exposure` and
  `supports_parallel_tool_calls`.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/dynamic_tool.rs` dynamic tool parser

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/dynamic_tool.rs`
- Rust tests: `codex/codex-rs/tools/src/dynamic_tool_tests.rs`
- Python module: `pycodex/tools/dynamic_tool.py`
- Python tests: deferred; Rust-derived coverage should mirror
  `codex/codex-rs/tools/src/dynamic_tool_tests.rs`
- Python status file: `pycodex/tools/DYNAMIC_TOOL_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust `parse_dynamic_tool` by accepting protocol
  `DynamicToolSpec` records, copying name/description, sanitizing and parsing
  `input_schema` through the `codex-tools` JSON Schema parser, setting
  `output_schema` to `None`, and preserving `defer_loading`.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/response_history.rs` response history mutation helpers

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/response_history.rs`
- Rust tests: inline `#[cfg(test)]` tests in
  `codex/codex-rs/tools/src/response_history.rs`
- Python module: `pycodex/tools/response_history.py`
- Python tests: deferred; Rust-derived coverage should mirror the inline Rust
  tests for tail retention and assistant output token-budget truncation.
- Python status file: `pycodex/tools/RESPONSE_HISTORY_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust in-place retention from the earliest retained
  user message through the latest user message, clears histories with no
  retained user boundary, applies one shared approximate token budget across
  assistant `output_text` content items, truncates the first over-budget text,
  drops later over-budget assistant text, and removes empty assistant messages.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/json_schema.rs` tool JSON Schema normalization

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/json_schema.rs`
- Rust tests: `codex/codex-rs/tools/src/json_schema_tests.rs`
- Python module: `pycodex/tools/json_schema.py`
- Python tests: deferred; Rust-derived tests should mirror
  `codex/codex-rs/tools/src/json_schema_tests.rs`
- Python status file: `pycodex/tools/JSON_SCHEMA_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust schema dataclasses, parse helpers,
  boolean-schema lowering, type inference, `const` to `enum` rewriting,
  default object/array children, nullable unions, `anyOf`, schema-valued
  `additionalProperties`, malformed definition-table dropping, local
  `$defs`/`definitions` reachability pruning, singleton-null rejection, and
  best-effort large-schema compaction.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/code_mode.rs` code-mode tool-spec adapter

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/code_mode.rs`
- Rust tests: `codex/codex-rs/tools/src/code_mode_tests.rs`
- Python module: `pycodex/tools/code_mode.py`
- Python behavior implementation: `pycodex/core/tools/code_mode/__init__.py`
- Python tests: `tests/test_core_code_mode.py`
- Python status file: `pycodex/tools/CODE_MODE_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust function/freeform/namespace conversion into
  code-mode tool definitions, code-mode description augmentation, unsupported
  hosted-tool skips, sorted de-duplication, exec/wait nested-tool filtering,
  and namespace name joining. The lower-level `codex-code-mode` runtime remains
  owned by the existing code-mode packages; this module records only the
  `codex-tools/src/code_mode.rs` adapter layer.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_spec.rs` Responses API top-level tool specs

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_spec.rs`
- Rust tests: `codex/codex-rs/tools/src/tool_spec_tests.rs`
- Python module: `pycodex/tools/tool_spec.py`
- Python tests: `tests/test_core_hosted_spec.py`, `tests/test_core_client.py`
- Python status file: `pycodex/tools/TOOL_SPEC_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust top-level tool-spec variants, variant name
  resolution, Responses API JSON serialization, web-search filter/location
  adapters, and hosted/freeform/tool-search wire shapes. Responses API function
  and namespace payloads are accepted as dependency mappings because their
  strong typed ownership belongs to `src/responses_api.rs`.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_output.rs` model-facing tool outputs

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_output.rs`
- Rust tests: none in `codex-tools`
- Python module: `pycodex/tools/tool_output.py`
- Python behavior implementation: `pycodex/core/tools/context.py`
- Python tests: `tests/test_core_tool_context.py`,
  `tests/test_core_tool_registry.py`, `tests/test_core_tool_router.py`
- Python status file: `pycodex/tools/TOOL_OUTPUT_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python preserves Rust `ToolOutput` runtime boundary validation,
  `JsonToolOutput::new`, `JsonToolOutput::with_success`, function versus custom
  response conversion, success logging, post-tool-use raw JSON response,
  code-mode raw JSON result, and telemetry preview truncation behavior. The
  tools package now exposes the canonical `codex-tools` path while reusing the
  existing core runtime implementation.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_call.rs` tool invocation snapshot

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_call.rs`
- Rust tests: none in `codex-tools`
- Python module: `pycodex/tools/tool_call.py`
- Python behavior implementation: `pycodex/core/tools/router.py`
- Python tests: `tests/test_core_tool_router.py`
- Python status file: `pycodex/tools/TOOL_CALL_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python preserves Rust `ConversationHistory` and `ToolCall`
  boundaries, function argument preservation, incompatible payload fatal error
  formatting, and extension context fields. The tools package now exposes the
  canonical `codex-tools` path while reusing the existing core router
  implementation.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_payload.rs` model-visible tool payloads

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_payload.rs`
- Rust tests: none in `codex-tools`
- Python module: `pycodex/tools/tool_payload.py`
- Python behavior implementation: `pycodex/core/tools/context.py`
- Python tests: `tests/test_core_tool_context.py`,
  `tests/test_core_tool_router.py`
- Python status file: `pycodex/tools/TOOL_PAYLOAD_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python preserves Rust `Function`, `ToolSearch`, and `Custom`
  payload variants, validates variant-specific fields, and mirrors
  `log_payload()` by returning function arguments, search query text, or custom
  input. The tools package now exposes the canonical `codex-tools` path while
  reusing the existing core runtime implementation.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/function_call_error.rs` shared tool error type

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/function_call_error.rs`
- Rust tests: none in `codex-tools`
- Python module: `pycodex/tools/function_call_error.py`
- Python behavior implementation: `pycodex/core/function_tool.py`
- Python tests: `tests/test_core_function_tool.py`,
  `tests/test_core_tool_router.py`, `tests/test_core_stream_events_utils.py`
- Python status file: `pycodex/tools/FUNCTION_CALL_ERROR_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python preserves Rust `RespondToModel` and `Fatal` formatting and
  shared runtime identity. The tools package now exposes the canonical
  `codex-tools` path while reusing the existing core implementation, matching
  Rust's core re-export behavior.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_discovery.rs` discoverable tool metadata

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_discovery.rs`
- Rust tests: `codex/codex-rs/tools/src/tool_discovery_tests.rs`
- Python module: `pycodex/tools/tool_discovery.py`
- Python tests: `tests/test_core_tool_discovery.py`
- Python status file: `pycodex/tools/TOOL_DISCOVERY_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust tool-name constants, discoverable tool type and
  action wire names, connector/plugin wrappers, connector-only install URL
  access, TUI plugin filtering, request plugin install entry collection, and
  list-result serialization.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/request_plugin_install.rs` request plugin install helpers

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/request_plugin_install.rs`
- Rust tests: `codex/codex-rs/tools/src/request_plugin_install_tests.rs`
- Python module: `pycodex/tools/request_plugin_install.py`
- Python tests: `tests/test_core_request_plugin_install.py`
- Python status file: `pycodex/tools/REQUEST_PLUGIN_INSTALL_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust request-plugin-install args/result records,
  approval metadata constants, elicitation request/meta construction, connector
  install URL handling, plugin install URL omission, and connector accessibility
  completion helpers.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/image_detail.rs` original image detail helpers

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/image_detail.rs`
- Rust tests: `codex/codex-rs/tools/src/image_detail_tests.rs`
- Python module: `pycodex/tools/original_image_detail.py`
- Python tests: `tests/test_core_original_image_detail.py`
- Python status file: `pycodex/tools/IMAGE_DETAIL_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust `can_request_original_image_detail`,
  `normalize_output_image_detail`, and `sanitize_original_image_detail`
  behavior, including unsupported `original` fallback to `DEFAULT_IMAGE_DETAIL`
  and preservation of non-original detail values.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.

### `src/tool_definition.rs` tool metadata record

- Rust owner: `codex-tools`
- Rust module: `codex/codex-rs/tools/src/tool_definition.rs`
- Rust tests: `codex/codex-rs/tools/src/tool_definition_tests.rs`
- Python module: `pycodex/tools/tool_definition.py`
- Python tests: `tests/test_core_tool_definition.py`
- Python status file: `pycodex/tools/TOOL_DEFINITION_RS_STATUS.md`
- Status: `complete_candidate`
- Evidence: Python mirrors Rust `ToolDefinition`, `renamed(...)`, and
  `into_deferred()` behavior. The Python tests cover both Rust tests directly
  and additional local safety around mapping round-trips and schema copying.
- Focused validation: deferred by current crate automation rule until
  `codex-tools` functional module code is complete.
