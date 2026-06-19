# codex-app-server-test-client test alignment

Rust crate: `codex-app-server-test-client`

Python package: `pycodex/app_server_test_client`

Status: `complete`

Certified modules:

- `codex/codex-rs/app-server-test-client/src/main.rs` -> `pycodex/app_server_test_client/__main__.py` (`complete`)
- `codex/codex-rs/app-server-test-client/src/lib.rs` -> `pycodex/app_server_test_client/__init__.py` (`complete`: public facade, pure helper/tracing slice, tracing provider compatibility boundary, stdio/background/websocket client construction through real interfaces, serve launcher helpers, full `CliCommand` runner dispatch, default live command runner wiring through `with_client`, message/approval/login/list/watch/elicitation orchestration over client interfaces, zsh multi-approval validation, protocol-shaped list/thread/turn params, in-memory JSON-RPC client core, account login helpers, stream-turn notification state tracking, stream-turn live output side effects, and live elicitation timeout harness)

Remaining Rust modules:

- None.

Rust tests and fixtures:

- No standalone Rust test functions are registered for this crate; current
  source contracts are derived from `src/main.rs` runtime setup and the
  covered `src/lib.rs` public facade/helper/tracing slice,
  stdio/background/websocket client construction, serve launcher helpers,
  `CliCommand` dispatch map, default live command runner wiring,
  model/thread list protocol params, thread/turn start protocol construction,
  message/approval/login/list/watch/elicitation orchestration over the client
  interface, zsh multi-approval validation, account login helper
  requests/completion wait, `TestClientTracing::initialize`, `with_client`,
  and `CodexClient::stream_turn` notification-state behavior.
  Additional source-derived coverage now checks `stream_turn` live output side
  effects for visible deltas and terminal/error notifications, plus live
  elicitation timeout harness validation and cleanup behavior.

Validation:

- Focused pytest passed:

```text
python -m pytest -q tests/test_app_server_test_client_lib_rs.py tests/test_app_server_test_client_main_rs.py
45 passed
```
