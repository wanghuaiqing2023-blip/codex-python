from __future__ import annotations

import base64
import io

import pytest

from pycodex.utils.image import (
    EncodedImage,
    ImageProcessingError,
    MAX_DIMENSION,
    PromptImageMode,
    load_for_prompt_bytes,
)


def _png_header(width: int, height: int) -> bytes:
    return b"\x89PNG\r\n\x1a\n" + (b"\x00" * 8) + width.to_bytes(4, "big") + height.to_bytes(4, "big")


def _pillow_image_bytes(width: int, height: int, image_format: str) -> bytes:
    pillow_image = pytest.importorskip("PIL.Image")
    image = pillow_image.new("RGBA", (width, height), (128, 64, 32, 255))
    output = io.BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_encoded_image_into_data_url_matches_rust_shape() -> None:
    # Source: codex/codex-rs/utils/image/src/lib.rs
    # Rust crate: codex-utils-image
    # Rust module: src/lib.rs
    # Contract: EncodedImage::into_data_url prefixes mime and base64-encodes bytes.
    image = EncodedImage(bytes=b"abc", mime="image/png", width=1, height=1)

    assert image.into_data_url() == f"data:image/png;base64,{base64.b64encode(b'abc').decode('ascii')}"


def test_small_png_resize_to_fit_preserves_source_bytes() -> None:
    # Rust contract: PNG inputs within MAX_DIMENSION preserve original bytes in resize-to-fit mode.
    data = _png_header(64, 32)

    image = load_for_prompt_bytes("in-memory-image", data, PromptImageMode.RESIZE_TO_FIT)

    assert image.width == 64
    assert image.height == 32
    assert image.mime == "image/png"
    assert image.bytes == data


def test_original_mode_preserves_large_png_header_bytes() -> None:
    # Rust contract: PromptImageMode::Original preserves source bytes even above MAX_DIMENSION.
    data = _png_header(4096, 2048)

    image = load_for_prompt_bytes("in-memory-image", data, PromptImageMode.ORIGINAL)

    assert image.width == 4096
    assert image.height == 2048
    assert image.mime == "image/png"
    assert image.bytes == data


def test_invalid_image_is_reported_as_image_processing_error() -> None:
    # Rust contract: invalid or unsupported bytes return ImageProcessingError.
    with pytest.raises(ImageProcessingError):
        load_for_prompt_bytes("in-memory-image", b"not an image", PromptImageMode.RESIZE_TO_FIT)


def test_large_resize_to_fit_downscales_png() -> None:
    # Rust contract: resize-to-fit scales large images so neither dimension exceeds MAX_DIMENSION.
    data = _pillow_image_bytes(4096, 2048, "PNG")

    image = load_for_prompt_bytes("in-memory-image.png", data, PromptImageMode.RESIZE_TO_FIT)

    assert image.width == MAX_DIMENSION
    assert image.height == 1024
    assert image.mime == "image/png"
    assert image.bytes != data


def test_gif_is_reencoded_to_png() -> None:
    # Rust contract: non-preserved formats such as GIF are decoded and re-encoded as PNG.
    data = _pillow_image_bytes(16, 8, "GIF")

    image = load_for_prompt_bytes("in-memory-image.gif", data, PromptImageMode.RESIZE_TO_FIT)

    assert image.width == 16
    assert image.height == 8
    assert image.mime == "image/png"
    assert image.bytes.startswith(b"\x89PNG\r\n\x1a\n")


def test_reprocesses_updated_file_contents_by_digest() -> None:
    # Rust contract: cache key includes file-content digest, so changed bytes are reprocessed.
    first = load_for_prompt_bytes(
        "in-memory-image",
        _png_header(32, 16),
        PromptImageMode.RESIZE_TO_FIT,
    )
    second = load_for_prompt_bytes(
        "in-memory-image",
        _png_header(96, 48),
        PromptImageMode.RESIZE_TO_FIT,
    )

    assert first.width == 32
    assert first.height == 16
    assert second.width == 96
    assert second.height == 48
    assert second.bytes != first.bytes


def test_cache_key_includes_prompt_image_mode() -> None:
    # Rust contract: cache key includes PromptImageMode as well as digest.
    data = _pillow_image_bytes(4096, 2048, "PNG")

    original = load_for_prompt_bytes("in-memory-image", data, PromptImageMode.ORIGINAL)
    resized = load_for_prompt_bytes("in-memory-image", data, PromptImageMode.RESIZE_TO_FIT)

    assert original.width == 4096
    assert original.height == 2048
    assert original.bytes == data
    assert resized.width == MAX_DIMENSION
    assert resized.height == 1024
    assert resized.bytes != original.bytes
