# 2026-06-02 bare prompt root model local HTTP

## Scope

Protected the common top-level prompt plus model override entrypoint:

`codex --model gpt-test "task" -> exec config bootstrap -> local HTTP sampling request`.

This continues the practical core runtime fallback for top-level prompts while the full Python TUI remains outside the active implementation target.

## Upstream anchors

- `codex/codex-rs/cli/src/main.rs`

Rust carries the shared root `model` into `ConfigOverrides` for interactive prompt handling. The Python fallback maps a top-level prompt to an `exec` invocation and relies on `_inherit_exec_root_options()` to carry root `model` into `ExecCli.model`.

## Python changes

- Added `TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_model_to_local_http_exec`.
- Added the test to `tests/test_cli_local_http_smoke_suite.py`.

The test drives `codex --model gpt-test-root "inspect model"` through the local HTTP fallback and verifies the prepared Responses request uses `model: gpt-test-root`; it also checks the human config summary reports that selected model.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_model_to_local_http_exec`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The CLI local HTTP smoke suite now covers 31 tests; the combined local HTTP core smoke suite now covers 45 tests.
