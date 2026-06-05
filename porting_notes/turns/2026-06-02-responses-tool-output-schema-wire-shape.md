# Responses tool output_schema wire shape

## Rust sources checked

- `codex/codex-rs/core/src/client.rs`
- `codex/codex-rs/tools/src/tool_spec.rs`
- `codex/codex-rs/tools/src/responses_api.rs`
- `codex/codex-rs/tools/src/tool_spec_tests.rs`
- `codex/codex-rs/tools/src/responses_api_tests.rs`

## Behavior confirmed

- `ModelClient::build_responses_request` sends `create_tools_json_for_responses_api(&prompt.tools)` into the Responses API request.
- `ToolSpec::Function` and namespace child function tools serialize through `ResponsesApiTool`.
- `ResponsesApiTool.output_schema` is retained internally for tool metadata/code-mode behavior, but is marked `#[serde(skip)]`, so it is never sent in the Responses API `tools` JSON.
- Function parameters that happen to use `output_schema` as a property name are ordinary JSON schema data and should remain intact.

## Python changes

- Updated `pycodex/core/client.py` so `create_tools_json_for_responses_api` uses tool-aware serialization and skips `output_schema` only on function tool objects.
- Added client tests for top-level function tools and namespace child tools that carry internal `output_schema` metadata.
- Updated the local HTTP view-image smoke expectation to assert the request wire shape omits `output_schema`; the internal view-image output schema remains covered by `tests/test_core_view_image_handler.py`.

## Validation

- `python -m py_compile pycodex/core/client.py tests/test_core_client.py tests/test_cli_parser.py`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_client.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_client_common.py tests/test_core_turn_request.py tests/test_core_turn_runtime.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_tool_registry.py tests/test_core_tool_router.py tests/test_core_tool_parallel.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_parser.py::TopLevelCliParserTests::test_main_exec_local_http_view_image_smoke_returns_image_content -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_core_client.py tests/test_core_view_image_handler.py -q`
- `PYTHONPATH=. uvx --with pytest pytest tests/test_cli_local_http_smoke_suite.py tests/test_exec_local_http_runtime_smoke_suite.py tests/test_local_http_core_smoke_suite.py --maxfail=1 -q`

Final smoke result: `744 passed, 1 skipped, 98 subtests passed`.

## Known gaps

- This only aligns Responses API tool wire serialization. Internal MCP/plugin/marketplace behavior remains limited to compatibility shims unless it becomes necessary for the core exec path.
