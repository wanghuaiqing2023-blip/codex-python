# 2026-06-02 bare prompt root image local HTTP

## Scope

Protected the common top-level prompt plus image entrypoint:

`codex --image image.png "task" -> exec run plan -> local image expansion -> local HTTP sampling request`.

This continues the bare-prompt local HTTP compatibility slice. It does not implement the full interactive TUI; it verifies that the practical core runtime fallback preserves root image input.

## Upstream anchors

- `codex/codex-rs/cli/src/main.rs`

Rust combines shared root images with command images and prompt text before building prompt input. The Python `ParsedCli` root options already collect `--image/-i`, and `_inherit_exec_root_options()` folds them into `ExecCli.images`.

## Python changes

- Added `TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_image_to_local_http_exec`.
- Added the test to `tests/test_cli_local_http_smoke_suite.py`.

The test drives `codex --image <png> "inspect the provided image"` through the local HTTP path and verifies the prepared Responses input contains both a PNG `input_image` data URL and the prompt text.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_image_to_local_http_exec`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The CLI local HTTP smoke suite now covers 29 tests; the combined local HTTP core smoke suite now covers 43 tests.
