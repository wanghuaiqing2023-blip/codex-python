# pycodex.utils.image

Rust crate: `codex-utils-image`

Rust anchor: `codex/codex-rs/utils/image`

This package mirrors the public crate interface exported from
`utils/image/src/lib.rs`.  Standard-library header parsing and data URL
encoding are ported for small/original images; resize/re-encode behavior remains
blocked on an approved image codec dependency.

## 2026-06-09 error-boundary slice

The Rust `error.rs` boundary is mirrored with structured Python exceptions:
`ReadImageError`, `DecodeImageError`, `EncodeImageError`, and
`UnsupportedImageFormatError`. `ImageProcessingError.decode_error(...)` and
`is_invalid_image()` preserve the Rust helper semantics. Full resize/re-encode
parity still requires an approved image codec dependency.
