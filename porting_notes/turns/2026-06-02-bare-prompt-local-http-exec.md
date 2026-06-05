# 2026-06-02 bare prompt local HTTP exec

## Scope

Connected the common top-level prompt entrypoint to the Python core local HTTP runtime when local HTTP exec is available:

`codex "task" -> exec run plan -> local HTTP sampling -> final assistant answer`.

This is a core entrypoint compatibility slice. It does not implement the full Rust TUI. A no-argument interactive invocation still falls through to the existing Python TUI placeholder.

## Upstream anchors

- `codex/codex-rs/cli/src/main.rs`

Rust treats a top-level prompt as interactive TUI input and normalizes CRLF/CR before passing it into the TUI session. Since the Python TUI remains a placeholder, the local HTTP path now provides a practical stdlib-compatible core runtime fallback for the same user-facing entrypoint when API-backed local exec is enabled.

## Python changes

- `pycodex/cli/parser.py`
  - If `ParsedCli.is_interactive` has a prompt and `local_http_exec_enabled()` is true, dispatch as a non-interactive `exec` invocation with that prompt.
  - Preserved the no-prompt interactive path as the TUI placeholder.
  - Fixed the explicit `PYCODEX_INTERACTIVE_TO_EXEC_FALLBACK` branch so it preserves the prompt instead of dropping it.
- `tests/test_cli_parser.py`
  - Added `test_main_prompt_without_subcommand_uses_local_http_exec_when_available`.
  - Isolated the existing TUI-placeholder test with `PYCODEX_EXEC_LOCAL_HTTP=0` so developer API-key environments do not change the branch under test.
- `tests/test_cli_local_http_smoke_suite.py`
  - Added the bare-prompt local HTTP smoke.

## Validation

- `python -m py_compile pycodex\cli\parser.py tests\test_cli_parser.py tests\test_cli_local_http_smoke_suite.py`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_uses_local_http_exec_when_available tests.test_cli_parser.TopLevelCliParserTests.test_main_prompt_without_subcommand_is_interactive_path`
- `python -m unittest tests.test_cli_local_http_smoke_suite`
- `python -m unittest tests.test_local_http_core_smoke_suite`

The CLI local HTTP smoke suite now covers 28 tests; the combined local HTTP core smoke suite now covers 42 tests.
