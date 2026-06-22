from __future__ import annotations

from pathlib import Path

from pycodex.utils.image import (
    DecodeImageError,
    EncodeImageError,
    ImageProcessingError,
    ReadImageError,
    UnsupportedImageFormatError,
)


class DecodingSourceError(Exception):
    is_decoding = True


def test_decode_error_preserves_decoding_errors() -> None:
    # Source: codex/codex-rs/utils/image/src/error.rs
    # Rust crate: codex-utils-image
    # Rust module: src/error.rs
    # Contract: ImageProcessingError::decode_error maps decoding errors to Decode.
    source = DecodingSourceError("bad pixels")

    error = ImageProcessingError.decode_error("bad.png", source)

    assert isinstance(error, DecodeImageError)
    assert error.path == Path("bad.png")
    assert error.source is source
    assert error.is_invalid_image() is True


def test_decode_error_maps_non_decoding_errors_to_unsupported_mime() -> None:
    # Rust contract: non-decoding image errors become UnsupportedImageFormat using mime_guess from path.
    error = ImageProcessingError.decode_error("bad.webp", RuntimeError("unsupported"))

    assert isinstance(error, UnsupportedImageFormatError)
    assert error.mime == "image/webp"
    assert error.is_invalid_image() is False


def test_decode_error_uses_unknown_when_path_has_no_mime() -> None:
    # Rust contract: unsupported format falls back to "unknown" when mime_guess finds no type.
    error = ImageProcessingError.decode_error("bad.unknown-extension", RuntimeError("unsupported"))

    assert isinstance(error, UnsupportedImageFormatError)
    assert error.mime == "unknown"


def test_error_messages_match_rust_display_shape() -> None:
    # Rust contract: thiserror Display messages include the path/format/mime details.
    read_error = ReadImageError("image.png", OSError("denied"))
    decode_error = DecodeImageError("image.png", RuntimeError("bad"))
    encode_error = EncodeImageError("Png", RuntimeError("bad"))
    unsupported_error = UnsupportedImageFormatError("image/avif")

    assert str(read_error) == "failed to read image at image.png: denied"
    assert str(decode_error) == "failed to decode image at image.png: bad"
    assert str(encode_error) == "failed to encode image as 'Png': bad"
    assert str(unsupported_error) == "unsupported image `image/avif`"
