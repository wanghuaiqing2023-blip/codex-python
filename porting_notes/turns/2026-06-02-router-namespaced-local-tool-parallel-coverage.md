## Router namespaced local-tool parallel coverage

Slice:

- Upstream graph nodes:
  - `codex-rs/core/src/tools/router.rs#tool_supports_parallel`
  - `codex-rs/core/src/tools/router_tests.rs#parallel_support_does_not_match_namespaced_local_tool_names`
- Authoritative Rust behavior:
  - Parallel capability is resolved against the exact registered `ToolName`.
  - A namespaced tool whose leaf name matches a local parallel tool, such as `mcp__server__/exec_command`, must not inherit the local `exec_command` parallel setting.

Python changes:

- `tests/test_core_tool_router.py`
  - Added regression coverage that `ToolRouter.tool_supports_parallel` returns false for a namespaced `exec_command` when only the plain local `exec_command` is registered as parallel.

Validation:

- `python -m py_compile pycodex\core\tool_router.py pycodex\core\tool_registry.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_tool_router.py tests\test_core_tool_registry.py -q`
  - `78 passed`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_tool_router.py tests\test_core_tool_registry.py tests\test_core_tool_parallel.py tests\test_core_unified_exec_handler.py -q`
  - `245 passed, 2 skipped`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - `744 passed, 1 skipped, 98 subtests passed`

Known gaps:

- This was a parity coverage slice, not a production behavior change. Broader extension/MCP runtime parity remains outside the active core-path target unless required by common tool dispatch.
