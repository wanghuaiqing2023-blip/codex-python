# windows_inhibitor.rs alignment

Rust crate: `codex-utils-sleep-inhibitor`

Rust module: `codex/codex-rs/utils/sleep-inhibitor/src/windows_inhibitor.rs`

Python module: `pycodex/utils/sleep_inhibitor/__init__.py`

Status: `complete`

Aligned behavior:

- `ASSERTION_REASON` is shared with the crate root and platform backends.
- `WindowsSleepInhibitor.acquire()` is idempotent when a request is already held.
- `WindowsSleepInhibitor.acquire()` records request creation failures without
  raising, matching Rust's warning-only failure path.
- `WindowsSleepInhibitor.release()` clears the active request and invokes the
  request cleanup hook, while recording cleanup failures without raising.
- `PowerRequest.new_system_required()` is kept as a dependency-free shim for the
  Rust `PowerCreateRequest`/`PowerSetRequest` path.

Validation:

- `python -m pytest tests/test_utils_sleep_inhibitor.py -q` passed on 2026-06-18 with `8 passed`.
- `python -m py_compile pycodex/utils/sleep_inhibitor/__init__.py tests/test_utils_sleep_inhibitor.py` passed on 2026-06-18.
