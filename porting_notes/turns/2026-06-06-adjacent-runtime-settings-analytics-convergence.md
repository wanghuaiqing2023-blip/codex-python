# 2026-06-06 adjacent runtime convergence: settings snapshots and analytics

## Trigger

- Batch 18 moved the core tools public layer and then ran a wider adjacent validation set.
- The tools public layer passed, but `tests/test_core_session_runtime.py` and `tests/test_core_turn_runtime.py` exposed 6 adjacent failures.

## Rust anchors

- `codex/codex-rs/core/src/codex_thread.rs`
  - `ThreadConfigSnapshot`
  - `ThreadConfigSnapshot::sandbox_policy`
- `codex/codex-rs/core/src/session/mod.rs`
  - `update_settings`
  - `preview_settings`
- `codex/codex-rs/core/src/session/turn.rs`
  - `track_turn_resolved_config_analytics`
- `codex/codex-rs/core/src/session/turn_context.rs`
  - `permission_profile`
  - `file_system_sandbox_policy`
  - `network_sandbox_policy`
  - `sandbox_policy`

## Fixes

- `pycodex/core/codex_thread.py`
  - Changed `ThreadConfigSnapshot.sandbox_policy()` to use `permission_profile.to_legacy_sandbox_policy(cwd)`, matching Rust's compatibility-sandbox behavior.
  - Added `file_system_sandbox_policy` as an explicit Python snapshot field for the in-memory runtime's split policy projection.
- `pycodex/core/session_runtime.py`
  - Snapshot construction now derives `file_system_sandbox_policy` from the projected permission profile.
  - `update_settings` now reuses the snapshot's projected permission profile and file-system policy instead of recomputing a second equivalent object.
- `pycodex/core/turn_runtime.py`
  - Turn resolved-config analytics now falls back through turn context, config, and thread snapshot for reasoning/collaboration/personality fields.
- `tests/test_core_session_runtime.py`
  - Updated one assertion to call `preview.sandbox_policy()` because the Rust contract is a method, not a field.

## Validation

- Focused failing slice:
  - `python -m pytest tests/test_core_session_runtime.py tests/test_core_turn_runtime.py`
  - Result: `192 passed`
- Original adjacent validation set from batch 18:
  - includes core tool router/parallel/runtimes/spec plan, session runtime, turn runtime, stream event utils, shell/unified exec handlers, goal/plugin-install handlers, extension tools, and HTTP transport.
  - Result: `765 passed`, `2 skipped`
- Import smoke:
  - `pycodex.core.session_runtime`
  - `pycodex.core.turn_runtime`
  - `pycodex.core.codex_thread`
  - passed

## Notes

- The original issue was not caused by the core-tools coordinate migration. The migration simply exposed adjacent session/turn contract drift.
- The fix keeps the behavior localized to snapshot projection and analytics payload construction.
