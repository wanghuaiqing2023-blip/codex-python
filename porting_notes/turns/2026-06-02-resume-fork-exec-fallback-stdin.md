# 2026-06-02: resume/fork exec fallback stdio forwarding

## Upstream slice

- Graph-guided inspection for the exec/session path pointed to `codex/codex-rs/cli/src/main.rs` and `codex/codex-rs/exec/src/lib.rs`.
- Rust exposes `codex resume` and `codex fork` as runtime commands alongside `codex exec`; the exec runtime path resolves prompt/stdin before starting or resuming a turn.

## Python slice

- `_run_resume_or_fork_command` now accepts `stdin` and `stdin_is_terminal` from `main`.
- The `PYCODEX_RESUME_EXEC_FALLBACK` and `PYCODEX_FORK_EXEC_FALLBACK` paths both forward stdout plus stdin state into `_run_noninteractive_exec`.
- This fixes the fork fallback `NameError`, preserves stdin prompt behavior, and keeps fallback final-answer/JSON output on the caller-provided stream.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_resume_with_exec_fallback_uses_noninteractive_resume_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_fork_with_exec_fallback_uses_noninteractive_fork_exec`
- `python -m unittest tests.test_exec_run tests.test_cli_parser.TopLevelCliParserTests.test_main_resume_without_fallback_uses_tui_path tests.test_cli_parser.TopLevelCliParserTests.test_main_resume_with_exec_fallback_uses_noninteractive_resume_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_fork_with_tui_fallback_runs_as_noop tests.test_cli_parser.TopLevelCliParserTests.test_main_fork_with_exec_fallback_uses_noninteractive_fork_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_enforces_trusted_directory_gate_before_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_prepares_noninteractive_plan tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_missing_prints_start_hint`
- `python -m unittest tests.test_exec_run tests.test_cli_parser.TopLevelCliParserTests.test_main_resume_with_exec_fallback_uses_noninteractive_resume_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_fork_with_exec_fallback_uses_noninteractive_fork_exec tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_prepares_noninteractive_plan tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_enforces_trusted_directory_gate_before_runtime tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_when_local_app_server_missing_prints_start_hint tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_shell_tool_loop_returns_followup_answer`

All targeted runs pass.

## Known gaps

- Full interactive TUI resume/fork behavior remains outside the current Python core target.
- The fallback paths still map fork through the non-interactive resume-shaped execution shim until a fuller fork runtime exists.
