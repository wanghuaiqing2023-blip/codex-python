# pycodex.utils.image

Rust crate: `codex-utils-image`

Rust anchor: `codex/codex-rs/utils/image`

This package mirrors the public crate interface exported from
`utils/image/src/lib.rs`. Standard-library header parsing and data URL encoding
cover source-byte preservation paths; resize/re-encode behavior is implemented
through a lazy optional Pillow codec bridge so no new hard dependency is added.

## 2026-06-18 crate completion

`utils/image/src/lib.rs` and `utils/image/src/error.rs` are both tracked in
`TEST_ALIGNMENT.md`. The package now covers `MAX_DIMENSION`, `EncodedImage`,
data URL conversion, prompt image modes, source-byte preservation for
PNG/JPEG/WebP, original-mode preservation, digest+mode cache key semantics,
large-image resize/re-encode behavior, GIF-to-PNG conversion, and Rust-shaped
image processing errors. Focused validation passed with `12 passed`, plus
`py_compile` for the package and tests.

## 2026-06-18 lib.rs partial alignment

`utils/image/src/lib.rs` is now tracked in `TEST_ALIGNMENT.md` and
`LIB_RS_STATUS.md`. The Python package covers `MAX_DIMENSION`, `EncodedImage`,
data URL conversion, prompt image modes, source-byte preservation for small
PNG/JPEG/WebP headers, original-mode preservation, digest+mode cache key
semantics, large-image resize/re-encode behavior, and GIF-to-PNG conversion.

## 2026-06-18 error.rs alignment

`utils/image/src/error.rs` is tracked in `TEST_ALIGNMENT.md` and
`ERROR_RS_STATUS.md`. The Python error boundary mirrors read/decode/encode and
unsupported-image errors, `decode_error(...)` classification, path-derived MIME
fallback, and invalid-image classification.

## 2026-06-09 error-boundary slice

The Rust `error.rs` boundary is mirrored with structured Python exceptions:
`ReadImageError`, `DecodeImageError`, `EncodeImageError`, and
`UnsupportedImageFormatError`. `ImageProcessingError.decode_error(...)` and
`is_invalid_image()` preserve the Rust helper semantics.
