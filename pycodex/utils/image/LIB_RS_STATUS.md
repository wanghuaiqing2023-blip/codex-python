# codex-utils-image src/lib.rs alignment

Rust module:
`codex/codex-rs/utils/image/src/lib.rs`

Python module:
`pycodex/utils/image/__init__.py`

Status: `complete`

## Scope

This module owns the public image prompt-processing API: maximum upload
dimension, encoded image data URL conversion, prompt image mode selection,
source image loading, MIME selection, source-byte preservation, resizing, and
re-encoding.

## Python Mapping

- `MAX_DIMENSION`, `EncodedImage`, `EncodedImage.into_data_url()`, and
  `PromptImageMode` are mapped to Python equivalents.
- `load_for_prompt_bytes(path, file_bytes, mode)` preserves source bytes for
  supported PNG/JPEG/WebP inputs when the image is within bounds or when
  `PromptImageMode.ORIGINAL` is used.
- Header parsers identify PNG, JPEG, WebP, and GIF dimensions without adding a
  third-party codec dependency.
- Successful prompt-image processing is cached by SHA-1 digest plus
  `PromptImageMode`, matching Rust's cache key semantics.
- Resize/re-encode behavior is implemented through a lazy optional Pillow codec
  bridge, preserving source bytes for PNG/JPEG/WebP pass-through paths while
  supporting Rust's large-image resize behavior and GIF-to-PNG conversion.

## Known Gaps

None for this module's tracked public behavior contract.

## Evidence

- Rust source:
  `codex/codex-rs/utils/image/src/lib.rs`
- Rust tests in this module cover source-byte preservation, resize behavior,
  original-mode preservation, invalid image errors, and cache-key behavior.
- Python parity tests in `tests/test_utils_image_lib_rs.py` passed together with
  the error module tests on 2026-06-18: `12 passed`.
- `python -m py_compile pycodex/utils/image/__init__.py
  tests/test_utils_image_lib_rs.py tests/test_utils_image_error_rs.py` passed.
