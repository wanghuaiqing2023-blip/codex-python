## Core startup prewarm abort consistency

Goal focus: preserve Rust prewarm semantics on the common runtime slice (`exec -> turn startup -> prewarm resolve`).

### Change
- Updated `pycodex/core/session_startup_prewarm.py` so `SessionStartupPrewarmHandle.resolve`
  awaits task cancellation when prewarm is aborted by timeout or cancellation token.
- Added an internal `_drain_cancelled_task` helper to ensure the task transitions
  to the cancelled state before `resolve()` returns in Python tests and callers
  that assert `task.cancelled()`.

### Validation
- `python -m pytest -q tests/test_core_session_startup_prewarm.py`
  - Result: 6 passed.
- Focused multi-core slice still appears blocked by missing async pytest plugin:
  `async def functions are not natively supported` across async-marked tests.

### Why this slice
- This is a minimal, core-path-only fix: it unblocks deterministic startup prewarm
  behavior and avoids extending MCP/plugin/marketplace parity work while the core
  agent flow remains incomplete.
