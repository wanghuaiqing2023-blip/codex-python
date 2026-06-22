# src/request_processors/thread_processor.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/thread_processor.rs`

Python mapping:

- `pycodex/app_server/request_processors_thread_processor.py`
- `tests/test_app_server_request_processors_thread_processor_rs.py`

Behavior covered:

- `ThreadRequestProcessor.new(...)` preserves the Rust constructor dependency
  surface for auth, thread management, outgoing, config, thread store, unload,
  state/watch, goal, background task, and skills-watcher handles.
- Resume helper functions cover override mismatch reporting, model override
  detection, and persisted metadata merge into request/type-safe overrides.
- Thread list CWD filters normalize single or many CWD filters and map invalid
  values to JSON-RPC invalid-params errors.
- Dynamic tool validation mirrors local Rust checks for name/namespace
  trimming, identifier rules, length limits, reserved names/namespaces,
  duplicate detection, deferred-loading namespace requirements, and injected
  schema validator error wrapping.
- Thread turns pagination mirrors cursor serialization/parsing, page-size
  clamping, ascending/descending anchor inclusion, next/backwards cursor
  construction, and missing-anchor invalid-request errors.
- Turn reconstruction/status helpers interrupt stale in-progress turns unless
  the resolved thread status is active, and merge an active turn by id.
- Small local helpers cover unsupported thread-store operation errors, thread
  title-to-name updates, and project-trust permission override checks.

Intentional boundaries:

- Live thread creation/resume/fork/list/read/archive/unarchive execution,
  concrete thread-store persistence, rollout IO, config loading, listener task
  orchestration, goal continuation, telemetry, realtime thread lifecycle, and
  dynamic tool schema parsing internals remain injected runtime/dependency
  boundaries.
- This module is complete for its module-scoped helper/facade behavior
  contract; concrete sibling-owned runtime effects remain boundaries until
  broader crate-level validation/integration.

Validation status:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_thread_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_thread_processor.py tests/test_app_server_request_processors_thread_processor_rs.py`.
