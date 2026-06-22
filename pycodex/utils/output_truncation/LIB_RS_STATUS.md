# codex-utils-output-truncation src/lib.rs status

Rust coordinate: `codex/codex-rs/utils/output-truncation/src/lib.rs`

Python coordinate: `pycodex/utils/output_truncation/__init__.py`

Status: `complete`

Behavior contract:

- `formatted_truncate_text` returns original content under budget and prefixes original line count when truncated.
- `truncate_text` dispatches bytes and token policies to the Rust-aligned string truncation helpers.
- `formatted_truncate_text_content_items_with_policy` merges text items for one combined formatted truncation while preserving image and encrypted content items.
- `truncate_function_output_items_with_policy` budgets text items sequentially, preserves non-text items, and appends omitted-text summaries.
- `approx_tokens_from_byte_count_i64` clamps non-positive values to zero.

Evidence:

- `tests/test_utils_output_truncation.py` maps the Rust `truncate_tests.rs` behavior to Python.
- `python -m pytest tests/test_utils_output_truncation.py -q` passed.
- `python -m py_compile pycodex/utils/output_truncation/__init__.py tests/test_utils_output_truncation.py` passed.
