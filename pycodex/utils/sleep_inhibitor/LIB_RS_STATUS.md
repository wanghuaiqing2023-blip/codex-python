# codex-utils-sleep-inhibitor src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/sleep-inhibitor/src/lib.rs`

Python coordinate: `pycodex/utils/sleep_inhibitor/__init__.py`

Status: `complete`

Behavior contract:

- expose the crate-level `SleepInhibitor` wrapper.
- `SleepInhibitor::new(enabled)` stores the enabled flag, initializes
  `turn_running=false`, and selects a platform backend.
- `set_turn_running(true)` records the latest requested turn state and, when
  enabled, delegates to `acquire`.
- `set_turn_running(false)` records the latest requested turn state and
  delegates to `release`.
- when disabled, `set_turn_running` still records the requested turn state but
  releases the platform backend instead of acquiring.
- `is_turn_running` returns the latest requested turn-running state.

Evidence:

- `pycodex/utils/sleep_inhibitor/__init__.py` implements `SleepInhibitor` with
  the same enabled/turn-running state machine and backend delegation points.
- The platform-specific backend modules are intentionally separate module
  contracts and are not certified by this file.

Validation:

- Deferred by project policy until all `codex-utils-sleep-inhibitor`
  functional modules are complete.
