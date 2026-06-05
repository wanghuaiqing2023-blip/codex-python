# 2026-06-02 bare prompt root approval local HTTP

## Scope

Protected the common top-level prompt plus approval-policy entrypoint:

`codex --ask-for-approval on-request --cd project "task" -> exec config bootstrap -> shell tool approval gate`.

This continues the practical core runtime fallback for top-level prompts while the full Python TUI remains outside the active implementation target.

## Upstream anchors

- `codex/codex-rs/cli/src/main.rs`

Rust carries shared root approval and sandbox controls into `ConfigOverrides` for interactive prompt handling. The Python fallback maps a top-level prompt to an `exec` invocation and relies on `_inherit_exec_root_options()` to carry root `approval_policy`, `sandbox`, and dangerous-bypass settings into `ExecCli`.

## Python changes

- Added `TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_approval_to_local_http_exec`.
- Added the test to `tests/test_cli_local_http_smoke_suite.py`.

The test drives `codex --ask-for-approval on-request --cd <project> "run a shell command"` through the local HTTP fallback. The fake model asks for an `exec_command` that would write a file. The local HTTP shell bridge returns `approval_required`, the file is not written, and the follow-up request carries the blocked tool output.

## Validation

- `python -m py_compile tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_forwards_root_approval_to_local_http_exec`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The CLI local HTTP smoke suite now covers 32 tests; the combined local HTTP core smoke suite now covers 46 tests.
