# codex-utils-sleep-inhibitor src/dummy.rs status

Rust coordinate: `codex/codex-rs/utils/sleep-inhibitor/src/dummy.rs`

Python coordinate: `pycodex/utils/sleep_inhibitor/__init__.py`

Status: `complete`

Behavior contract:

- expose a platform backend named `SleepInhibitor` for unsupported platforms.
- `new` returns an inert backend.
- `acquire` is a no-op.
- `release` is a no-op.

Evidence:

- `DummySleepInhibitor` in `pycodex/utils/sleep_inhibitor/__init__.py`
  provides the same inert acquire/release behavior.
- `default_platform_backend` selects `DummySleepInhibitor` for platforms that
  are not Linux, macOS, or Windows.

Validation:

- Deferred by project policy until all `codex-utils-sleep-inhibitor`
  functional modules are complete.
