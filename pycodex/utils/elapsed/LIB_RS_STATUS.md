# codex-utils-elapsed src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/utils/elapsed/src/lib.rs`

Python target:

- `pycodex/utils/elapsed/__init__.py`

Behavior contract covered:

- durations below one second render as integer milliseconds
- durations from one second up to below one minute render seconds with two decimals
- durations of one minute or longer render minutes plus zero-padded seconds
- exactly one hour keeps the `60m 00s` spacing
- fractional milliseconds are truncated like Rust `Duration::as_millis`

Tests:

- `tests/test_utils_elapsed.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_utils_elapsed.py -q` -> `6 passed`
- 2026-06-17: `python -m py_compile pycodex\utils\elapsed\__init__.py tests\test_utils_elapsed.py` -> passed

