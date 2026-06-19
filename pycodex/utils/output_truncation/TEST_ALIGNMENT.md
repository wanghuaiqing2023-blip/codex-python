# codex-utils-output-truncation test alignment

Rust crate: `codex-utils-output-truncation`

Rust module: `codex/codex-rs/utils/output-truncation/src/lib.rs`

Rust test module: `codex/codex-rs/utils/output-truncation/src/truncate_tests.rs`

Python module: `pycodex/utils/output_truncation/__init__.py`

Status: `complete`

Validation:

- `python -m pytest tests/test_utils_output_truncation.py -q`
- `python -m py_compile pycodex/utils/output_truncation/__init__.py tests/test_utils_output_truncation.py`

Rust-derived coverage:

- `truncate_bytes_less_than_placeholder_returns_placeholder`
- `truncate_tokens_less_than_placeholder_returns_placeholder`
- `truncate_tokens_under_limit_returns_original`
- `truncate_bytes_under_limit_returns_original`
- `truncate_bytes_reports_original_line_count_when_truncated`
- `truncate_tokens_reports_original_line_count_when_truncated`
- `truncate_middle_bytes_handles_utf8_content`
- `truncates_across_multiple_under_limit_texts_and_reports_omitted`
- `formatted_truncate_text_content_items_with_policy_returns_original_under_limit`
- `formatted_truncate_text_content_items_with_policy_merges_text_and_appends_images`
- `formatted_truncate_text_content_items_with_policy_preserves_encrypted_content`
- `truncate_function_output_items_with_policy_preserves_encrypted_content`
- `formatted_truncate_text_content_items_with_policy_merges_all_text_for_token_budget`
- `byte_count_conversion_clamps_non_positive_values`

Additional source-contract coverage:

- no-text content item lists return the original items and no original token count.
- Python keeps the Rust module boundary pure; runtime-specific output shaping remains in core/tool modules.

Known gaps: none for `src/lib.rs`. The Python tests group a few closely related Rust examples where the shared behavior contract is identical.
