## 2026-06-03 Turn Runtime Resolved Config Analytics

### Scope

- Added Python-side parity for Rust's `track_turn_resolved_config` analytics event on the user-turn preparation path.
- Kept the implementation in the core slice: one analytics payload emitted from
  `pycodex/core/turn_runtime.py` during `_prepare_user_turn_request_from_session`.

### Upstream Slice

- `codex/codex-rs/core/src/session/turn.rs`
- `run_turn(...)` calls `track_turn_resolved_config_analytics(&sess, &turn_context, &input).await`
  after skill/plugin injection and before model sampling.
- `track_turn_resolved_config_analytics(...)` populates resolved config facts (images,
  policy/capability fields, model/provider metadata, approval and sandbox flags, personality,
  collaboration mode, and first-turn marker).

### Python Changes

- `pycodex/core/turn_runtime.py`
  - Added `_track_turn_resolved_config(...)` and helper functions to:
    - read the thread config snapshot (or fall back safely),
    - count image inputs in the user input tuple,
    - coalesce resolved values across snapshot/session/turn-context sources,
    - compute the `sandbox_network_access` flag from sandbox policy objects, and
    - read the first-turn marker when available.
  - Wired this call from `_prepare_user_turn_request_from_session` after explicit mention injection collection.
  - Wrapped tracking in a broad guard so any exception in analytics collection only affects telemetry and does not break turn execution.

### Test Coverage

- `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_turn_resolved_config_for_analytics`
  - Verifies count, IDs, resolved-model config fields, and resilience to normal path inputs (`text` + `image` + `local_image`).
