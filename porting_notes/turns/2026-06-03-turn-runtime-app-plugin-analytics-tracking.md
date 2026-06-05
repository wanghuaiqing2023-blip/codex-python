# 2026-06-03 Turn-runtime app/plugin analytics tracking parity

## Context
On user input preparation, upstream Rust sends analytics events for explicit app
mentions and explicit plugin mentions:
- `track_app_mentioned` receives `AppInvocation` entries (including explicit
  skill-derived app ids), with invocation type `Explicit`.
- `track_plugin_used` receives plugin telemetry metadata for plugins whose
  `telemetry_metadata()` is available.

Pycodex already had warning-event parity for `SkillInjections.warnings` but had
not yet mirrored these app/plugin tracking calls in the same core path.

## Change
- Added helper calls in `pycodex/core/turn_runtime.py::_prepare_user_turn_skill_plugin_items`
  to emit best-effort analytics events before returning injection items:
  - `track_app_mentioned` is called with invocation entries derived from explicit
    app ids and available connector metadata.
  - `track_plugin_used` is called for explicit plugin mentions that expose
    `telemetry_metadata()`.
- Added defensive guards around analytics dispatch so missing analytics service or
  missing methods do not alter core request flow.
- Added regression coverage in
  `tests/test_core_turn_runtime.py::TurnRuntimeTests::test_run_user_turn_sampling_tracks_explicit_app_and_plugin_mentions_for_analytics`.

## Rationale
- Keeps parity focus on the core runtime slice (`exec -> context -> model request
  -> stream handling -> tool dispatch -> final answer`) by matching Rust-side
  side effects that are user-visible in telemetry-sensitive workflows.
- Avoids additional dependencies; this is implemented with plain Python objects and
  optional callable checks, consistent with pycodex portability constraints.
