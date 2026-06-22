# `codex-state/src/runtime/logs.rs` Python alignment

Status: `complete`

Rust owner:

- Crate: `codex-state`
- Module: `codex/codex-rs/state/src/runtime/logs.rs`

Python owner:

- Module: `pycodex/state/runtime/logs.py`
- Package exports: `pycodex.state.runtime`, `pycodex.state`

## Behavior contract

This module mirrors the Rust runtime log-store contract over an existing logs
SQLite schema:

- `insert_log` and `insert_logs` persist `LogEntry` values, writing
  `feedback_log_body` with `message` as the write-time fallback.
- `estimated_bytes` is computed from persisted feedback body, level, target,
  module path, and file using UTF-8 byte length.
- Post-insert pruning enforces the Rust per-partition budgets:
  - thread rows partitioned by `thread_id`
  - threadless rows partitioned by non-null `process_uuid`
  - threadless rows with null `process_uuid` as their own partition
  - newest rows are retained first by `ts DESC, ts_nanos DESC, id DESC`
  - rows over the byte cap or row cap are deleted.
- `delete_logs_before` and `run_logs_startup_maintenance` mirror retention
  cleanup and the passive WAL checkpoint call.
- `query_logs` mirrors Rust filters for levels, timestamp bounds, module/file
  substring filters, thread/threadless selection, `after_id`, search over
  `feedback_log_body`, order, and limit.
- `query_feedback_logs_for_threads` and `query_feedback_logs` merge requested
  thread rows with threadless rows from each requested thread's latest process,
  apply the partition byte cap, and return chronological formatted log bytes.
- `max_log_id` returns `0` when no matching row exists.
- `format_feedback_log_line` mirrors Rust's RFC3339-micros timestamp, padded
  level, body, and trailing-newline behavior.

## Scope notes

Schema creation and migration remain owned by `src/migrations.rs` and
`src/runtime.rs`. This module assumes the migrated logs table exists, matching
the Rust runtime module boundary after `StateRuntime::init`.

## Validation

Formal parity validation:

```powershell
python -m pytest tests\test_state_runtime_logs_rs.py -q
# 7 passed

python -m py_compile pycodex\state\runtime\logs.py pycodex\state\runtime\__init__.py pycodex\state\__init__.py tests\test_state_runtime_logs_rs.py
```

Coverage includes insert/query/search/max id, level filtering without stored
level rewrite, feedback line formatting, feedback export merged with latest
process threadless rows, empty thread-list export, startup retention cleanup,
thread partition row-limit pruning, and threadless process partition pruning.
