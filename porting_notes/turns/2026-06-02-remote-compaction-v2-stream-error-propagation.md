# Remote compaction v2 stream error propagation

## Upstream source

- `codex/codex-rs/core/src/compact_remote_v2.rs`

Rust consumes remote compaction v2 response streams with `event?` inside `collect_compaction_output`. If the stream yields a `CodexErr`, that error is returned immediately before later events are considered. This matters because retryable stream errors must flow into the remote-compaction retry decision path instead of becoming generic parsing failures.

## Python changes

- Updated `pycodex/core/compact_remote_v2.py` so `collect_compaction_output` raises an incoming `CodexErr` unchanged.
- Added a focused test in `tests/test_core_compact_remote_v2.py` proving a stream error is propagated by identity, even if a later `completed` event is present.

## Validation

- `python -m py_compile pycodex\core\compact_remote_v2.py tests\test_core_compact_remote_v2.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_compact_remote_v2.py -q -k "collect_compaction_output or retry_decision or request_outcome"`
  - 9 passed, 14 deselected
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_compact_remote_v2.py tests\test_core_turn_runtime.py -q`
  - 93 passed
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 744 passed, 1 skipped, 98 subtests passed

## Follow-up

Continue using remote compaction v2 only as a core-runtime support slice. The remaining async orchestration, tracing, and WebSocket-specific branches should stay scoped to pieces that directly unblock common `exec` behavior.
