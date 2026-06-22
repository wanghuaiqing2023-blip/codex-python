# codex-async-utils src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/async-utils/src/lib.rs`

Python target:

- `pycodex/async_utils/__init__.py`

Behavior contract covered:

- cancellation marker type
- cancellation token state and awaitable notification
- `or_cancel` success when the awaitable completes first
- cancellation when the token completes first
- immediate cancellation when the token is already cancelled

Tests:

- `tests/test_async_utils_lib_rs.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_async_utils_lib_rs.py -q` -> `3 passed`
- 2026-06-17: `python -m py_compile pycodex\async_utils\__init__.py tests\test_async_utils_lib_rs.py` -> passed

