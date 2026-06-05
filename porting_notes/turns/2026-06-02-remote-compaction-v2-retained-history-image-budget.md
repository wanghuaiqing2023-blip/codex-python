# Remote compaction v2 retained-history image budget

## Upstream source

- `codex/codex-rs/core/src/compact_remote_v2.rs`

Rust retained-history truncation walks retained messages from newest to oldest. Image-only messages still consume the minimum one-token accounting through `message_text_token_count(item).max(1)`. If the budget has already been spent by newer retained messages, older image-only messages are dropped.

## Python changes

`pycodex/core/compact_remote_v2.py` already matched this behavior. This turn added the missing Rust boundary coverage in `tests/test_core_compact_remote_v2.py`:

- when the budget is only enough for the newest message, an older image-only retained message is not kept.

## Validation

- `python -m py_compile tests\test_core_compact_remote_v2.py`
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_compact_remote_v2.py -q -k "retained_history or build_v2_compacted_history"`
  - 6 passed, 18 deselected
- `PYTHONPATH=. uvx --with pytest pytest tests\test_core_compact_remote_v2.py tests\test_core_compact_remote.py tests\test_core_compact.py -q`
  - 59 passed
- `PYTHONPATH=. uvx --with pytest pytest tests\test_cli_local_http_smoke_suite.py tests\test_exec_local_http_runtime_smoke_suite.py tests\test_local_http_core_smoke_suite.py --maxfail=1 -q`
  - 744 passed, 1 skipped, 98 subtests passed

## Follow-up

Continue along compaction only when it protects the common `exec` runtime path. Avoid expanding into unrelated tracing or cloud-specific behavior unless it becomes a direct runtime dependency.
