# codex-utils-image src/error.rs alignment

Rust module:
`codex/codex-rs/utils/image/src/error.rs`

Python module:
`pycodex/utils/image/__init__.py`

Status: `complete_candidate`

## Scope

This module owns the image-processing error boundary: read/decode/encode
errors, unsupported-image errors, the `decode_error(...)` classifier, and
`is_invalid_image()`.

## Python Mapping

- `ReadImageError`, `DecodeImageError`, `EncodeImageError`, and
  `UnsupportedImageFormatError` mirror the Rust enum variants as structured
  exception classes.
- `ImageProcessingError.decode_error(path, source)` preserves existing decode
  errors and maps non-decoding sources to `UnsupportedImageFormatError` using a
  path-derived MIME type, falling back to `"unknown"`.
- `ImageProcessingError.is_invalid_image()` is true only for decode errors.

## Evidence

- Rust source:
  `codex/codex-rs/utils/image/src/error.rs`
- Rust crate has no standalone tests in this module.
- Python parity tests added in `tests/test_utils_image_error_rs.py`. They are
  not run yet because the crate functional code is not complete.
