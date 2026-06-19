# codex-tools src/image_detail.rs status

Status: complete_candidate

Rust crate: `codex-tools`
Rust module: `codex/codex-rs/tools/src/image_detail.rs`
Rust tests: `codex/codex-rs/tools/src/image_detail_tests.rs`
Python module: `pycodex/tools/original_image_detail.py`
Python tests: `tests/test_core_original_image_detail.py`

## Behavior contract

Rust `src/image_detail.rs` owns original-image-detail capability handling for
tool output images:

- `can_request_original_image_detail(...)` follows the model capability flag;
- `normalize_output_image_detail(...)` preserves `original` only when the model
  supports it, drops unsupported `original`/missing detail, and preserves
  `auto`, `low`, and `high`;
- `sanitize_original_image_detail(...)` rewrites unsupported `original` image
  detail to `DEFAULT_IMAGE_DETAIL` while leaving non-image and non-original
  content untouched.

## Python alignment

`pycodex.tools.original_image_detail` mirrors the Rust helpers and returns an
immutable tuple of normalized `FunctionCallOutputContentItem` values. Python
adds type checks around the Rust-shaped inputs for clearer downstream errors.

## Evidence

- Rust source inspected: `codex/codex-rs/tools/src/image_detail.rs`.
- Rust tests inspected: `codex/codex-rs/tools/src/image_detail_tests.rs`.
- Python implementation inspected: `pycodex/tools/original_image_detail.py`.
- Python tests inspected: `tests/test_core_original_image_detail.py`.
- Validation deferred by current crate automation rule until `codex-tools`
  functional module code is complete.
