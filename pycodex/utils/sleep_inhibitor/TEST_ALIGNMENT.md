# codex-utils-sleep-inhibitor test alignment

Rust crate: `codex-utils-sleep-inhibitor`

Python package: `pycodex/utils/sleep_inhibitor`

Status: `complete`

Certified modules:

- `codex/codex-rs/utils/sleep-inhibitor/src/dummy.rs` -> `pycodex/utils/sleep_inhibitor/__init__.py`
- `codex/codex-rs/utils/sleep-inhibitor/src/iokit_bindings.rs` -> `pycodex/utils/sleep_inhibitor/__init__.py`
- `codex/codex-rs/utils/sleep-inhibitor/src/lib.rs` -> `pycodex/utils/sleep_inhibitor/__init__.py`
- `codex/codex-rs/utils/sleep-inhibitor/src/linux_inhibitor.rs` -> `pycodex/utils/sleep_inhibitor/__init__.py`
- `codex/codex-rs/utils/sleep-inhibitor/src/macos.rs` -> `pycodex/utils/sleep_inhibitor/__init__.py`
- `codex/codex-rs/utils/sleep-inhibitor/src/windows_inhibitor.rs` -> `pycodex/utils/sleep_inhibitor/__init__.py`

Remaining Rust modules:

- None.

Rust tests and fixtures:

- `codex/codex-rs/utils/sleep-inhibitor/src/lib.rs`
  - `sleep_inhibitor_toggles_without_panicking`
  - `sleep_inhibitor_disabled_does_not_panic`
  - `sleep_inhibitor_multiple_true_calls_are_idempotent`
  - `sleep_inhibitor_can_toggle_multiple_times`

Validation:

- `python -m pytest tests/test_utils_sleep_inhibitor.py -q` passed on 2026-06-18 with `8 passed`.
- `python -m py_compile pycodex/utils/sleep_inhibitor/__init__.py tests/test_utils_sleep_inhibitor.py` passed on 2026-06-18.
