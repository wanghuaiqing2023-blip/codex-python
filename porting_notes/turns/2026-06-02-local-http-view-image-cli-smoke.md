# 2026-06-02 local HTTP view_image CLI smoke

## Scope

Protected the core local HTTP CLI path for the Rust `view_image` behavior slice:

`exec -> model request -> view_image function call -> local file read -> input_image tool output -> follow-up request -> final answer`.

This stays inside the current core runtime priority. It does not expand MCP, plugin, marketplace, or remote environment support.

## Upstream anchors

- `codex/codex-rs/core/src/tools/handlers/view_image.rs`
- `codex/codex-rs/core/src/tools/handlers/view_image_spec.rs`
- `codex/codex-rs/core/tests/suite/view_image.rs`

Rust only exposes the `detail` input override when the model can request original image detail. The smoke test therefore uses the default high-detail path and asserts the always-present output schema separately.

## Python changes

- Added `TopLevelCliParserTests.test_main_exec_local_http_view_image_smoke_returns_image_content`.
- Added that test to `tests/test_cli_local_http_smoke_suite.py`.

The test drives `codex exec` through local HTTP with shell tools enabled, returns a fake `view_image` call, writes a tiny local PNG under `--cd`, and verifies the second model request includes a successful `function_call_output` whose output is an `input_image` data URL with `detail: high`.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_view_image_smoke_returns_image_content`
- `python -m unittest tests.test_exec_local_http_runtime_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The combined local HTTP core smoke suite now covers 40 tests.
