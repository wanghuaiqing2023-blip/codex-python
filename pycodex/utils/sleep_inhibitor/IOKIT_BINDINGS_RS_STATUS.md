# codex-utils-sleep-inhibitor src/iokit_bindings.rs status

Rust coordinate: `codex/codex-rs/utils/sleep-inhibitor/src/iokit_bindings.rs`

Python coordinate: `pycodex/utils/sleep_inhibitor/__init__.py`

Status: `complete`

Behavior contract:

- expose generated IOKit constants used by the macOS backend:
  `kIOReturnSuccess`, `kIOPMAssertionLevelOff`, and
  `kIOPMAssertionLevelOn`.
- expose type aliases for IOKit assertion ids, levels, and return codes.
- declare the native IOKit entrypoints
  `IOPMAssertionCreateWithName` and `IOPMAssertionRelease`.

Python adaptation:

- Python does not bind IOKit directly. The port keeps a dependency-light
  compatibility boundary and exposes the stable constants as
  `K_IO_RETURN_SUCCESS`, `K_IOPM_ASSERTION_LEVEL_OFF`, and
  `K_IOPM_ASSERTION_LEVEL_ON`.
- Native function signatures are documented here and consumed by the macOS
  module contract rather than exposed as live Python FFI calls.

Validation:

- Deferred by project policy until all `codex-utils-sleep-inhibitor`
  functional modules are complete.
