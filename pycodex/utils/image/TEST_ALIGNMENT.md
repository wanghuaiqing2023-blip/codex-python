# codex-utils-image test alignment

Rust crate: `codex-utils-image`

Python package: `pycodex/utils/image`

Status: `complete`

Certified modules:

- `codex/codex-rs/utils/image/src/error.rs`
  -> `pycodex/utils/image/__init__.py`
- `codex/codex-rs/utils/image/src/lib.rs`
  -> `pycodex/utils/image/__init__.py`

Remaining Rust modules:

None. All known Rust modules are tracked and complete.

Rust tests and fixtures for tracked modules:

- `src/lib.rs`
  - Source-contract coverage identified for `MAX_DIMENSION`, `EncodedImage`,
    `EncodedImage::into_data_url`, `PromptImageMode`, `load_for_prompt_bytes`,
    source-byte preservation for PNG/JPEG/WebP within bounds, original-mode
    preservation, unsupported/invalid image errors, digest-based cache keys, and
    resize/re-encode behavior for large images and non-preserved formats such as
    GIF.
- `src/error.rs`
  - Source-contract coverage for read/decode/encode/unsupported error variants,
    display message shape, `decode_error(...)` classification of decoding vs
    unsupported format errors, MIME fallback behavior, and invalid-image
    classification.

Python parity coverage:

- `tests/test_utils_image_lib_rs.py`
  - `test_encoded_image_into_data_url_matches_rust_shape`
  - `test_small_png_resize_to_fit_preserves_source_bytes`
  - `test_original_mode_preserves_large_png_header_bytes`
  - `test_invalid_image_is_reported_as_image_processing_error`
  - `test_large_resize_to_fit_downscales_png`
  - `test_gif_is_reencoded_to_png`
  - `test_reprocesses_updated_file_contents_by_digest`
  - `test_cache_key_includes_prompt_image_mode`
- `tests/test_utils_image_error_rs.py`
  - `test_decode_error_preserves_decoding_errors`
  - `test_decode_error_maps_non_decoding_errors_to_unsupported_mime`
  - `test_decode_error_uses_unknown_when_path_has_no_mime`
  - `test_error_messages_match_rust_display_shape`

Known gaps:

None for the tracked crate/module behavior contract.

Implementation note:

- Rust uses the `image` crate for codec work. Python keeps PNG/JPEG/WebP
  pass-through paths dependency-free and lazily uses Pillow only for behavior
  that requires a codec, namely resize/re-encode and GIF-to-PNG conversion.
Validation:

- `python -m pytest tests/test_utils_image_lib_rs.py
  tests/test_utils_image_error_rs.py -q` passed on 2026-06-18 with `12 passed`.
- `python -m py_compile pycodex/utils/image/__init__.py
  tests/test_utils_image_lib_rs.py tests/test_utils_image_error_rs.py` passed.
