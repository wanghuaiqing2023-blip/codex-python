# 2026-06-01 Http Compact Header Parity

## Graph-selected slice

- Upstream graph nodes used as navigation:
  - `codex-rs/core/src/client.rs`
  - `codex-rs/core/src/session/turn.rs`
  - `codex-rs/core/src/compact_remote.rs`
- The slice advances `model request construction -> HTTP transport headers -> sampling` behavior on the core exec path.

## Rust source checked

- `codex/codex-rs/core/src/client.rs`

## Python changes

- Updated HTTP transport tests to match Rust compact/summarize request headers: `x-client-request-id` is inserted for websocket handshakes, not compact HTTP requests.
- Isolated the compact HTTP originator assertion from the desktop host environment by clearing `os.environ` for that specific assertion. Override behavior remains covered separately.

## Validation

- `python -m unittest tests.test_core_http_transport tests.test_core_turn_sampler tests.test_core_stream_events_utils tests.test_core_tool_router`
  - Passed: 168 tests.
- `python -m unittest tests.test_exec_run tests.test_exec_config_plan tests.test_exec_local_runtime tests.test_core_turn_runtime`
  - Passed: 198 tests.

## Follow-up debt

- `tests.test_core_client` uses pytest-style tests and is not runnable in this environment because `pytest` is not installed.
- `PORTING_STATUS.md` is currently deleted in the worktree; this turn intentionally did not recreate it.
