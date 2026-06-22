# codex-utils-fuzzy-match src/lib.rs Status

Status: complete

Rust source:

- `codex/codex-rs/utils/fuzzy-match/src/lib.rs`

Python target:

- `pycodex/utils/fuzzy_match/__init__.py`

Behavior contract covered:

- case-insensitive subsequence matching
- original haystack character indices for highlighting
- Unicode lowercase expansion mapping back to original character indices
- deduped indices for multi-character lowercase expansion
- lower-is-better score based on match window
- prefix bonus
- empty needle returns no indices and `i32::MAX`

Tests:

- `tests/test_utils_fuzzy_match.py`

Last validation:

- 2026-06-17: `python -m pytest tests\test_utils_fuzzy_match.py -q` -> `10 passed`
- 2026-06-17: `python -m py_compile pycodex\utils\fuzzy_match\__init__.py tests\test_utils_fuzzy_match.py` -> passed

