# codex-utils-readiness src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/utils/readiness/src/lib.rs`

Python target:

- `pycodex/utils/readiness/__init__.py`

Behavior contract covered:

- token-based readiness authorization
- one-shot readiness transition
- rejected unknown and zero tokens
- waiters unblock after readiness is marked
- no-subscriber `is_ready` auto-ready behavior
- token lock timeout error
- duplicate and wrapped token id avoidance

Tests:

- `tests/test_utils_readiness.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_utils_readiness.py -q` -> `10 passed`
- 2026-06-17: `python -m py_compile pycodex\utils\readiness\__init__.py tests\test_utils_readiness.py` -> passed

