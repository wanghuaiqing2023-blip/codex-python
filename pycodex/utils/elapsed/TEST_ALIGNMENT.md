# codex-utils-elapsed Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/utils/elapsed/src/lib.rs`

Python module:

- `pycodex/utils/elapsed/__init__.py`

Parity evidence:

- `tests/test_utils_elapsed.py`

Rust-derived coverage:

- `test_format_duration_subsecond`
- `test_format_duration_seconds`
- `test_format_duration_minutes`
- `test_format_duration_one_hour_has_space`

Additional Python boundary coverage:

- sub-millisecond truncation matching Rust `Duration::as_millis`
- invalid Python input rejection for non-`timedelta` and negative durations

Validation:

- `python -m pytest tests\test_utils_elapsed.py -q` -> `6 passed`
- `python -m py_compile pycodex\utils\elapsed\__init__.py tests\test_utils_elapsed.py` -> passed

Known adaptations:

- Rust accepts `std::time::Duration`; Python accepts `datetime.timedelta` and rejects negative values because Rust `Duration` is non-negative by construction.

