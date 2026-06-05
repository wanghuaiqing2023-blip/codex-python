# 2026-06-02 - CLI write_stdin smoke coverage

## Upstream slice

- Used the graph-selected unified exec path:
  - `codex-rs/core/src/tools/handlers/unified_exec.rs`
  - `codex-rs/core/src/tools/handlers/unified_exec/write_stdin.rs`
- Confirmed Rust behavior:
  - `write_stdin` parses `session_id`, optional `chars`, default `yield_time_ms`, and optional `max_output_tokens`.
  - Non-empty stdin is a real terminal interaction.
  - Empty stdin is a background poll.
  - Completed `write_stdin` output can produce the post-tool payload for the original exec command.

## Python progress

- Added a CLI-level local HTTP smoke test for the real shell tools loop:
  - first model turn calls `exec_command` to start a Python child waiting on stdin;
  - the local helper starts a live session and returns a real `session_id`;
  - the fake model reads that output and calls `write_stdin`;
  - the helper writes `hello\n`, observes `got:hello`, and sends the result back to the model;
  - final assistant output is printed by `codex exec`.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_write_stdin_smoke_continues_session_and_followup`
- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tools_smoke_runs_command_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_write_stdin_smoke_continues_session_and_followup tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_shell_tool_on_request_requires_approval tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_smoke_reads_history_and_appends_rollout tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_resume_local_http_shell_tools_smoke_runs_command_and_appends_rollout tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_exec_command_session_accepts_write_stdin tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_write_stdin_exit_clears_session`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up debt

- Extend the same CLI smoke shape to resume + `write_stdin` if a later slice needs interactive resumed sessions.
- Keep deeper PTY parity and app-server transport behavior out of scope until the core CLI runtime path needs them.
