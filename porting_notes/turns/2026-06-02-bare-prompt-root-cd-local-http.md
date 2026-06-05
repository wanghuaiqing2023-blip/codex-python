# 2026-06-02 bare prompt root cd local HTTP

## Scope

Protected the common top-level prompt plus working-directory entrypoint:

`codex --cd project "task" -> exec config bootstrap -> local HTTP sampling -> human result`.

This continues the practical core runtime fallback for top-level prompts while the full Python TUI remains outside the active implementation target.

## Upstream anchors

- `codex/codex-rs/cli/src/main.rs`

Rust carries the shared root `cwd` into `ConfigOverrides` for interactive prompt handling. The Python fallback maps a top-level prompt to an `exec` invocation and relies on `_inherit_exec_root_options()` to carry root `cwd` into `ExecCli.cwd`.

## Python changes

- Added `TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_cd_to_local_http_exec`.
- Added the test to `tests/test_cli_local_http_smoke_suite.py`.

The test drives `codex --cd <project> "inspect cwd"` through the local HTTP fallback, verifies the run succeeds, and checks the human config summary reports the selected workdir.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_cd_to_local_http_exec`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The CLI local HTTP smoke suite now covers 30 tests; the combined local HTTP core smoke suite now covers 44 tests.
