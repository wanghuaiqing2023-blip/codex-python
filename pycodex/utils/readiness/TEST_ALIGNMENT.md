# codex-utils-readiness Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/utils/readiness/src/lib.rs`

Python module:

- `pycodex/utils/readiness/__init__.py`

Parity evidence:

- `tests/test_utils_readiness.py`

Rust-derived coverage:

- `subscribe_and_mark_ready_roundtrip`
- `subscribe_after_ready_returns_none`
- `mark_ready_rejects_unknown_token`
- `wait_ready_unblocks_after_mark_ready`
- `mark_ready_twice_uses_single_token`
- `is_ready_without_subscribers_marks_flag_ready`
- `subscribe_returns_error_when_lock_is_held`
- `subscribe_skips_zero_token`
- `subscribe_avoids_duplicate_tokens`

Additional Python boundary coverage:

- token id wraparound follows Rust `AtomicI32` semantics.

Validation:

- `python -m pytest tests\test_utils_readiness.py -q` -> `10 passed`
- `python -m py_compile pycodex\utils\readiness\__init__.py tests\test_utils_readiness.py` -> passed

Known adaptations:

- Rust uses Tokio `Mutex` and `watch`; Python uses `asyncio.Lock` and `asyncio.Event` with equivalent observable behavior for this module contract.

