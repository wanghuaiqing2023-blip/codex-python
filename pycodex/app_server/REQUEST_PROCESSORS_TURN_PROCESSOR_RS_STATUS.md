# src/request_processors/turn_processor.rs status

Status: `complete`

Rust source:

- `codex/codex-rs/app-server/src/request_processors/turn_processor.rs`

Python mapping:

- `pycodex/app_server/request_processors_turn_processor.py`
- `tests/test_app_server_request_processors_turn_processor_rs.py`

Behavior covered:

- `resolve_runtime_workspace_roots(...)` mirrors relative-to-base path
  resolution and first-occurrence deduplication.
- `map_additional_context(...)` mirrors Rust's `Option<HashMap<..>>` to
  sorted `BTreeMap` projection and maps API additional-context kinds into
  core `Untrusted`/`Application` variants.
- `TurnRequestProcessor.new(...)` preserves the Rust constructor dependency
  surface for auth, thread management, outgoing, analytics, config, unload,
  state/watch, and skills-watcher handles.
- Public wrapper methods parse already-ported protocol params where available
  and delegate to injected inner runtime hooks, preserving Rust's response
  shape for turn start, steering, interrupt, realtime start/append/stop, thread
  settings, injected items, and review start.
- `load_thread(...)` mirrors thread-id parsing and missing-thread
  invalid-request errors.
- `thread_realtime_list_voices(...)` returns `RealtimeVoicesList.builtin()`
  in a `ThreadRealtimeListVoicesResponse`.
- `xcode_26_4_mcp_elicitations_auto_deny(...)` mirrors the Xcode 26.4
  compatibility predicate exactly.

Intentional boundaries:

- Concrete turn startup, settings override construction, live thread
  execution, review request orchestration, realtime session control, listener
  task setup, and core event routing remain injected runtime boundaries owned
  by neighboring core/app-server modules.
- Thread inject/settings protocol dataclasses are not yet independently ported
  in `pycodex/app_server_protocol`, so this module treats those params as
  transparent runtime payloads rather than widening scope to protocol work.
- This module is complete for its module-scoped facade/helper behavior
  contract; concrete sibling-owned runtime effects remain boundaries until
  broader crate-level validation/integration.

Validation status:

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_request_processors_turn_processor_rs.py -q`
  -> 9 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/request_processors_turn_processor.py tests/test_app_server_request_processors_turn_processor_rs.py`.
