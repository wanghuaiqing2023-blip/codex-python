# codex-utils-sleep-inhibitor src/macos.rs status

Rust coordinate: `codex/codex-rs/utils/sleep-inhibitor/src/macos.rs`

Python coordinate: `pycodex/utils/sleep_inhibitor/__init__.py`

Status: `complete`

Behavior contract:

- expose a macOS platform backend named `SleepInhibitor`.
- `new` starts with no active assertion.
- `acquire` is idempotent when an assertion already exists.
- `acquire` attempts to create an assertion named
  `Codex is running an active turn` using assertion type
  `PreventUserIdleSystemSleep` and level `kIOPMAssertionLevelOn`.
- assertion creation failures are logged/recorded rather than raised to the
  caller.
- `release` drops the active assertion, triggering exactly one native release
  in Rust; release failures are logged/recorded rather than raised.

Python adaptation:

- Python does not bind CoreFoundation/IOKit directly. `MacSleepInhibitor`
  mirrors Rust control-flow semantics and accepts an injectable assertion
  factory for tests or future native integration.
- The default `MacSleepAssertion.create` records the unsupported native binding
  as an `OSError`; `MacSleepInhibitor.acquire` stores that error and continues,
  matching Rust's warn-and-continue behavior.

Validation:

- Deferred by project policy until all `codex-utils-sleep-inhibitor`
  functional modules are complete.
