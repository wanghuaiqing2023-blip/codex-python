# Tool dispatch view_image payload boundary

## Upstream graph and source slice

- Graph node: `function:codex-rs/core/src/tools/parallel.rs#handle_tool_call`
- Graph node: `class:codex-rs/core/src/tools/registry.rs#ToolRegistry`
- Graph node: `class:codex-rs/core/src/tools/handlers/view_image.rs#ViewImageHandler`
- Source: `codex/codex-rs/core/src/tools/parallel.rs`
- Source: `codex/codex-rs/core/src/tools/registry.rs`
- Source: `codex/codex-rs/core/src/tools/handlers/view_image.rs`

Rust checks a registered tool's `matches_kind` before invoking the handler. For
`view_image`, only function payloads match. A `tool_search` payload for
`view_image` should therefore fail at dispatch as an incompatible payload rather
than reaching the handler.

## Python changes

- Added router-level coverage proving `view_image` with a `tool_search` payload
  fails as `tool view_image invoked with incompatible payload`.
- Repaired core registry tests so the main dispatch regression group is runnable
  with the current protocol shapes:
  - imported `JsonToolOutput`;
  - used `input_image` content item type instead of the obsolete `image` name.

## Validation

- `python -m py_compile tests\test_core_tool_router.py`
- `python -m unittest tests.test_core_tool_router.ToolRouterTests.test_dispatch_tool_call_rejects_view_image_tool_search_payload tests.test_core_tool_router.ToolRouterTests.test_dispatch_tool_call_reports_missing_and_incompatible_tools_like_rust`
- `python -m unittest tests.test_core_tool_router`
- `python -m unittest tests.test_core_tool_registry tests.test_core_view_image_handler tests.test_core_unified_exec_handler`
- `python -m unittest tests.test_core_tool_router tests.test_core_tool_registry tests.test_core_view_image_handler tests.test_core_unified_exec_handler tests.test_core_turn_runtime tests.test_core_tool_events`
- `python -m unittest tests.test_exec_local_runtime`
