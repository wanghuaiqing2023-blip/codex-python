# codex-utils-fuzzy-match Test Alignment

Status: complete

Rust module:

- `codex/codex-rs/utils/fuzzy-match/src/lib.rs`

Python module:

- `pycodex/utils/fuzzy_match/__init__.py`

Parity evidence:

- `tests/test_utils_fuzzy_match.py`

Rust-derived coverage:

- `ascii_basic_indices`
- `unicode_dotted_i_istanbul_highlighting`
- `unicode_german_sharp_s_casefold`
- `prefer_contiguous_match_over_spread`
- `start_of_string_bonus_applies`
- `empty_needle_matches_with_max_score_and_no_indices`
- `case_insensitive_matching_basic`
- `indices_are_deduped_for_multichar_lowercase_expansion`

Additional Python boundary coverage:

- missing subsequence returns `None`
- non-string input rejection

Validation:

- `python -m pytest tests\test_utils_fuzzy_match.py -q` -> `10 passed`
- `python -m py_compile pycodex\utils\fuzzy_match\__init__.py tests\test_utils_fuzzy_match.py` -> passed

Known adaptations:

- Rust returns `Option<(Vec<usize>, i32)>`; Python returns `tuple[list[int], int] | None`.

