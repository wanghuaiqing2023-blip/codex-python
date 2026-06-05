# CLI context window error smoke

## Upstream slice

- Used `codex/codex-rs/exec/src/exec_events.rs` to confirm the public `codex exec --json` error event shape.
- `ThreadErrorEvent` exposes only a user-facing `message`; the richer `codex_error_info` remains an internal protocol/runtime detail rather than part of the exec JSONL event.

## Python slice

- Added/kept CLI-level local HTTP smokes for a Responses failure payload with `context_length_exceeded`.
- Human output verifies the user sees a single `ERROR:` context-window message and no final assistant text.
- JSON output verifies the Rust-shaped event sequence:
  `thread.started`, `turn.started`, `error`, `turn.completed`.
- Runtime coverage still verifies the internal session events include `context_window_exceeded` and full context-window token accounting.

## Validation

- `python -m unittest tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_context_window_error_prints_human_error tests.test_cli_parser.TopLevelCliParserTests.test_main_exec_local_http_context_window_error_prints_json_error_event tests.test_exec_local_runtime.ExecLocalRuntimeTests.test_local_http_context_window_error_attaches_session_events`
- `python -m py_compile tests\test_cli_parser.py`

## Follow-up

- Continue expanding core CLI error-path coverage around provider errors, interrupted turns, and multi-tool failures before widening into MCP/plugin/app-server behavior.
