# request_processors/thread_summary.rs Status

Rust module: `codex/codex-rs/app-server/src/request_processors/thread_summary.rs`

Python module: `pycodex/app_server/request_processors_thread_summary.py`

Status: `complete`

## Scope

- Thread-spawn agent metadata overlay for rollout session sources.
- Core-to-app-server active permission profile and sandbox policy projection.
- Thread settings projection from `ThreadConfigSnapshot` and
  `ThreadSettingsSnapshot`.
- Thread-started notification sanitization by clearing `thread.turns`.
- Test-helper conversation summary extraction, git-info mapping, and
  summary-to-thread materialization.

## Evidence

- Rust local test:
  `extract_conversation_summary_prefers_plain_user_messages`.
- Python parity entry:
  `tests/test_app_server_request_processors_thread_summary_rs.py`.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_summary_rs.py -q`
  -> 7 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_summary.py tests/test_app_server_request_processors_thread_summary_rs.py`.

## Deferred Boundaries

- Full rollout file IO, async metadata reads, and thread-processor JSON-RPC
  dispatch remain neighboring runtime boundaries.
