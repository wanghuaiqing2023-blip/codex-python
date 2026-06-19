# codex-app-server src/skills_watcher.rs status

Rust module: `codex/codex-rs/app-server/src/skills_watcher.rs`

Python module: `pycodex/app_server/skills_watcher.py`

Status: `complete`

## Covered

- `skills_watcher_new_projection(...)` mirrors `SkillsWatcher::new` setup:
  file watcher creation, noop fallback on initialization error, subscriber
  registration, shutdown token/drop guard creation, and listener spawn gate.
- `register_thread_config(...)` mirrors the module-local environment branch:
  no selected environment, unknown environment warning, remote environment
  skip, local `SkillsLoadInput` construction, plugin skill root forwarding,
  filesystem forwarding, and recursive watch path registration.
- `event_loop_iteration_projection(...)` mirrors one listener iteration:
  `None` breaks the loop; a watch event clears the skills cache and sends a
  `SkillsChanged` server notification.
- `shutdown_projection(...)` records the Rust shutdown-token cancellation.
- Watcher throttle constants are represented for normal and cfg(test) builds.

## Deferred

- Real `codex_file_watcher` integration, throttled receiver timing, Tokio task
  spawning, cancellation token mechanics, and concrete outgoing async delivery
  remain runtime dependencies.

## Python parity tests

- `tests/test_app_server_skills_watcher_rs.py`

- Focused parity validation passed on 2026-06-19:
  `python -m pytest tests/test_app_server_skills_watcher_rs.py -q` -> 11 passed.
- Syntax validation passed on 2026-06-19:
  `python -m py_compile pycodex/app_server/skills_watcher.py tests/test_app_server_skills_watcher_rs.py`.
