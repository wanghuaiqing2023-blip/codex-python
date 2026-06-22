# codex-utils-sleep-inhibitor

Rust crate: `codex-utils-sleep-inhibitor`

Rust anchor: `codex/codex-rs/utils/sleep-inhibitor`

Current certified modules:

- `utils/sleep-inhibitor/src/dummy.rs`
- `utils/sleep-inhibitor/src/iokit_bindings.rs`
- `utils/sleep-inhibitor/src/lib.rs`
- `utils/sleep-inhibitor/src/linux_inhibitor.rs`
- `utils/sleep-inhibitor/src/macos.rs`
- `utils/sleep-inhibitor/src/windows_inhibitor.rs`

The crate root helper is represented by `SleepInhibitor` in
`pycodex/utils/sleep_inhibitor/__init__.py`: it stores the enabled flag, tracks
the latest caller-provided turn-running state, and delegates acquire/release to
the selected platform backend.

The Windows backend is represented by `WindowsSleepInhibitor` and `PowerRequest`.
It preserves the Rust module's idempotent acquire contract, non-panicking error
handling, and release-time cleanup hook while keeping the actual Win32 power
request binding as a dependency-free compatibility seam.
