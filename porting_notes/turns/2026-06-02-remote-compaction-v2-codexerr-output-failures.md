# Remote compaction v2 CodexErr output failures

## Upstream source

- `codex/codex-rs/core/src/compact_remote_v2.rs`

Rust `collect_compaction_output` returns protocol errors for terminal stream-shape failures:

- Missing `response.completed` returns `CodexErr::Stream(...)`, which is retryable.
- A compaction output count other than one returns `CodexErr::Fatal(...)`, which is not retryable.

This distinction matters because `run_remote_compaction_request_v2` feeds the error into the same retry decision path used by model streams.

## Python changes

- Updated `pycodex/core/compact_remote_v2.py` so `collect_compaction_output` raises:
  - `CodexErr.stream(...)` when the stream closes before `completed`;
  - `CodexErr.fatal(...)` when the compaction output count is invalid.
- Updated `tests/test_core_compact_remote_v2.py` to assert the Rust-shaped error kinds and retryability.

The older local exception classes remain exported for now to avoid import churn, but the core collection path now returns the protocol errors that the runtime expects.

## Validation

- `python -m py_compile pycodex\core\compact_remote_v2.py tests\test_core_compact_remote_v2.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_compact_remote_v2.py -q -k "collect_compaction_output or request_outcome or retry_decision"`
  - 9 passed, 14 deselected
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_compact_remote_v2.py tests\test_core_turn_runtime.py -q`
  - 93 passed
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 744 passed, 1 skipped, 98 subtests passed

## Follow-up

Continue tightening remote compaction only where it supports the common runtime path. The next useful slice is likely request orchestration or history installation behavior, not unrelated extension-system parity.
