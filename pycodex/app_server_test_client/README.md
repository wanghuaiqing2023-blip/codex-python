# codex-app-server-test-client

Python package for Rust crate `codex-app-server-test-client`.

## Module Map

| Rust module | Python module | Status | Notes |
|---|---|---|---|
| `src/main.rs` | `pycodex/app_server_test_client/__main__.py` | `complete` | Binary entrypoint creates an async runtime boundary and runs the crate `run()` coroutine. |
| `src/lib.rs` | `pycodex/app_server_test_client/__init__.py` | `complete` | Public facade, pure routing/helper/tracing slice, tracing provider compatibility boundary, stdio/background/websocket client construction through real interfaces, serve launcher helpers, full `CliCommand` runner dispatch, default live command runner wiring through `with_client`, message/approval/login/list/watch/elicitation orchestration over client interfaces, zsh multi-approval validation, protocol-shaped list/thread/turn params, in-memory `CodexClient` JSON-RPC core, account login helpers, stream-turn notification state tracking, stream-turn live output side effects, and live elicitation timeout harness are mapped. |

Focused validation passed:

```text
python -m pytest -q tests/test_app_server_test_client_lib_rs.py tests/test_app_server_test_client_main_rs.py
45 passed
```
