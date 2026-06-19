# codex-app-server src/mcp_refresh.rs Status

Rust source:

- `codex/codex-rs/app-server/src/mcp_refresh.rs`

Python target:

- `pycodex/app_server/mcp_refresh.py`

Status: `complete`

Covered behavior:

- `queue_strict_refresh(...)` loads the latest global config first.
- Strict refresh loads every thread, builds every per-thread refresh config, and
  only queues refresh ops after planning succeeds for all threads.
- Strict refresh wraps thread-load failures as
  `failed to load thread {thread_id}: {err}`.
- `queue_best_effort_refresh(...)` iterates every thread id and skips
  thread-load, config-build, and queue-submit failures independently.
- `build_refresh_config(...)` loads the latest config for the current thread,
  asks the thread manager's MCP manager for configured servers, and serializes
  both configured servers and `mcp_oauth_credentials_store_mode` into
  `McpServerRefreshConfig`.
- `queue_refresh(...)` submits `Op.refresh_mcp_servers(...)` and wraps submit
  failures as `failed to queue MCP refresh for thread {thread_id}: {err}`.

Deferred runtime boundaries:

- Concrete `ConfigManager`, `ThreadManager`, `CodexThread`, and MCP manager
  implementations remain owned by their crates/modules.
- Tracing warnings, Rust `io::Error::other` identity, and exact Tokio scheduling
  are represented by deterministic Python control flow and `McpRefreshError`.

Validation:

- `python -m pytest tests/test_app_server_mcp_refresh_rs.py -q` passed on
  2026-06-19 with 6 tests.
- `python -m py_compile pycodex/app_server/mcp_refresh.py
  tests/test_app_server_mcp_refresh_rs.py` passed on 2026-06-19.
