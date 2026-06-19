# codex-utils-sleep-inhibitor src/linux_inhibitor.rs status

Rust coordinate: `codex/codex-rs/utils/sleep-inhibitor/src/linux_inhibitor.rs`

Python coordinate: `pycodex/utils/sleep_inhibitor/__init__.py`

Status: `complete`

Behavior contract:

- expose Linux backend `SleepInhibitor` as `LinuxSleepInhibitor`.
- keep inactive/active state with the active backend and child process.
- `acquire` is idempotent while the child process is still running.
- if no active child is running, try backends in preferred order:
  `systemd-inhibit` first by default, then `gnome-session-inhibit`; after a
  successful backend, prefer it for later attempts.
- spawn helpers with null stdin/stdout/stderr and long-running `sleep
  2147483647`.
- set `missing_backend_logged` after all backend attempts fail and clear it on
  a successful backend.
- `release` terminates and waits for the active child when present.
- dropping the backend releases the active child.

Evidence:

- `LinuxSleepInhibitor` in `pycodex/utils/sleep_inhibitor/__init__.py` mirrors
  backend ordering, process lifetime, preferred backend, missing-backend state,
  release behavior, and destructor cleanup.
- `_linux_backend_command` mirrors Rust `spawn_backend` command construction.

Validation:

- Deferred by project policy until all `codex-utils-sleep-inhibitor`
  functional modules are complete.
