# request_processors/feedback_processor.rs Status

Rust module: `codex-app-server/src/request_processors/feedback_processor.rs`

Python module: `pycodex/app_server/request_processors_feedback_processor.py`

Status: `complete`

## Covered Contract

- Processor construction preserves Rust's injected auth/thread/config/feedback,
  log DB, and state DB dependency boundaries.
- `feedback_upload`/`upload_feedback_response` preserve feedback-enabled
  gating, request parsing, thread-id validation, snapshot selection, upload
  option construction, session-source propagation, and JSON-RPC error mapping.
- Include-log uploads preserve log DB flush, subtree thread ID lookup, state DB
  descendant fallback, sqlite feedback log override lookup, rollout attachment
  discovery, guardian trunk filename override, Windows sandbox log attachment
  projection, explicit extra log-file dedupe, and doctor-report
  attachment/tag merging.
- `resolve_rollout_path`, `auto_review_rollout_filename`, and
  `windows_sandbox_log_attachment` mirror the Rust helper behavior with
  platform/runtime dependencies injectable for Python tests.

## Evidence

- Source: `codex/codex-rs/app-server/src/request_processors/feedback_processor.rs`
- Python parity tests in
  `tests/test_app_server_request_processors_feedback_processor_rs.py`.
- Rust local test covered by platform-neutral adaptation:
  `windows_sandbox_log_attachment_uses_current_log`.
- Focused validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_feedback_processor_rs.py -q`
  -> 8 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_feedback_processor.py tests/test_app_server_request_processors_feedback_processor_rs.py`.

## Known Gaps

- Concrete feedback backend upload, live thread manager runtime, auth trace
  logging internals, Tokio blocking upload scheduling, and platform Windows
  sandbox log-path discovery remain dependency/runtime boundaries.
