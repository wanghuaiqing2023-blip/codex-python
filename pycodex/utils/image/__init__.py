"""Python interface for Rust ``codex-utils-image``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import base64
from collections import OrderedDict
import hashlib
import io
import mimetypes
from pathlib import Path
import struct


MAX_DIMENSION = 2048
_IMAGE_CACHE_SIZE = 32
_IMAGE_CACHE: "OrderedDict[tuple[bytes, PromptImageMode], EncodedImage]" = OrderedDict()


class ImageProcessingError(Exception):
    kind = "image"

    @staticmethod
    def decode_error(path: str | Path, source: BaseException) -> "ImageProcessingError":
        if isinstance(source, DecodeImageError):
            return source
        if getattr(source, "is_decoding", False):
            return DecodeImageError(path, source)
        return UnsupportedImageFormatError(_guess_mime(path))

    def is_invalid_image(self) -> bool:
        return isinstance(self, DecodeImageError)


class ReadImageError(ImageProcessingError):
    kind = "read"

    def __init__(self, path: str | Path, source: BaseException) -> None:
        self.path = Path(path)
        self.source = source
        super().__init__(f"failed to read image at {self.path}: {source}")


class DecodeImageError(ImageProcessingError):
    kind = "decode"

    def __init__(self, path: str | Path, source: BaseException) -> None:
        self.path = Path(path)
        self.source = source
        super().__init__(f"failed to decode image at {self.path}: {source}")


class EncodeImageError(ImageProcessingError):
    kind = "encode"

    def __init__(self, image_format: str, source: BaseException) -> None:
        self.format = image_format
        self.source = source
        super().__init__(f"failed to encode image as {image_format!r}: {source}")


class UnsupportedImageFormatError(ImageProcessingError):
    kind = "unsupported"

    def __init__(self, mime: str) -> None:
        self.mime = mime
        super().__init__(f"unsupported image `{mime}`")


@dataclass(frozen=True)
class EncodedImage:
    bytes: bytes
    mime: str
    width: int
    height: int

    def into_data_url(self) -> str:
        encoded = base64.b64encode(self.bytes).decode("ascii")
        return f"data:{self.mime};base64,{encoded}"


class PromptImageMode(str, Enum):
    RESIZE_TO_FIT = "resize_to_fit"
    ORIGINAL = "original"


def load_for_prompt_bytes(
    path: str | Path,
    file_bytes: bytes,
    mode: PromptImageMode = PromptImageMode.RESIZE_TO_FIT,
) -> EncodedImage:
    key = (hashlib.sha1(file_bytes).digest(), mode)
    cached = _IMAGE_CACHE.get(key)
    if cached is not None:
        _IMAGE_CACHE.move_to_end(key)
        return cached

    parsed = _parse_image_header(file_bytes)
    if parsed is None:
        suffix = Path(path).suffix.lstrip(".") or "unknown"
        raise UnsupportedImageFormatError(suffix)
    mime, width, height = parsed
    needs_resize = mode is not PromptImageMode.ORIGINAL and (
        width > MAX_DIMENSION or height > MAX_DIMENSION
    )
    can_preserve_source_bytes = mime in {"image/png", "image/jpeg", "image/webp"}
    if not needs_resize and can_preserve_source_bytes:
        return _cache_image(
            key,
            EncodedImage(bytes=file_bytes, mime=mime, width=width, height=height),
        )

    reencoded = _reencode_with_pillow(path, file_bytes, mime, needs_resize)
    if reencoded is not None:
        return _cache_image(key, reencoded)

    operation = "resize" if needs_resize else _target_format_label(mime)
    raise EncodeImageError(
        operation,
        RuntimeError(
            "codex-utils-image resize/encode path requires an approved image codec dependency"
        ),
    )


def _cache_image(
    key: tuple[bytes, PromptImageMode],
    image: EncodedImage,
) -> EncodedImage:
    _IMAGE_CACHE[key] = image
    _IMAGE_CACHE.move_to_end(key)
    while len(_IMAGE_CACHE) > _IMAGE_CACHE_SIZE:
        _IMAGE_CACHE.popitem(last=False)
    return image


def _reencode_with_pillow(
    path: str | Path,
    file_bytes: bytes,
    source_mime: str,
    needs_resize: bool,
) -> EncodedImage | None:
    try:
        from PIL import Image as PillowImage
        from PIL import UnidentifiedImageError
    except ImportError:
        return None

    try:
        with PillowImage.open(io.BytesIO(file_bytes)) as source:
            image = source.copy()
    except UnidentifiedImageError as exc:
        raise DecodeImageError(path, exc) from exc
    except OSError as exc:
        raise DecodeImageError(path, exc) from exc

    if needs_resize:
        width, height = image.size
        scale = min(MAX_DIMENSION / width, MAX_DIMENSION / height)
        image = image.resize(
            (max(1, round(width * scale)), max(1, round(height * scale))),
            _pillow_resampling_filter(PillowImage),
        )

    target_format = _target_format(source_mime)
    output = io.BytesIO()
    try:
        if target_format == "JPEG":
            image = image.convert("RGB")
        elif image.mode not in {"RGB", "RGBA"}:
            image = image.convert("RGBA")
        save_kwargs = {"format": target_format}
        if target_format == "JPEG":
            save_kwargs["quality"] = 85
        image.save(output, **save_kwargs)
    except OSError as exc:
        raise EncodeImageError(_target_format_label(source_mime), exc) from exc

    width, height = image.size
    return EncodedImage(
        bytes=output.getvalue(),
        mime=_mime_for_format(target_format),
        width=width,
        height=height,
    )


def _target_format(source_mime: str) -> str:
    if source_mime == "image/jpeg":
        return "JPEG"
    if source_mime == "image/webp":
        return "WEBP"
    return "PNG"


def _target_format_label(source_mime: str) -> str:
    return {"JPEG": "Jpeg", "WEBP": "WebP", "PNG": "Png"}[_target_format(source_mime)]


def _mime_for_format(image_format: str) -> str:
    return {
        "JPEG": "image/jpeg",
        "PNG": "image/png",
        "WEBP": "image/webp",
    }[image_format]


def _pillow_resampling_filter(pillow_image: object) -> object:
    resampling = getattr(pillow_image, "Resampling", None)
    if resampling is not None:
        return resampling.BILINEAR
    return pillow_image.BILINEAR


def _parse_image_header(data: bytes) -> tuple[str, int, int] | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "image/png", width, height
    if data.startswith(b"\xff\xd8"):
        size = _jpeg_size(data)
        if size:
            return "image/jpeg", *size
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        size = _webp_size(data)
        if size:
            return "image/webp", *size
    if data.startswith((b"GIF87a", b"GIF89a")) and len(data) >= 10:
        width, height = struct.unpack("<HH", data[6:10])
        return "image/gif", width, height
    return None


def _guess_mime(path: str | Path) -> str:
    mime, _encoding = mimetypes.guess_type(Path(path).name)
    return mime or "unknown"


def _jpeg_size(data: bytes) -> tuple[int, int] | None:
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        index += 2
        if marker in {0xD8, 0xD9}:
            continue
        if index + 2 > len(data):
            return None
        length = int.from_bytes(data[index : index + 2], "big")
        if length < 2 or index + length > len(data):
            return None
        if 0xC0 <= marker <= 0xCF and marker not in {0xC4, 0xC8, 0xCC}:
            height = int.from_bytes(data[index + 3 : index + 5], "big")
            width = int.from_bytes(data[index + 5 : index + 7], "big")
            return width, height
        index += length
    return None


def _webp_size(data: bytes) -> tuple[int, int] | None:
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = int.from_bytes(data[24:27] + b"\x00", "little") + 1
        height = int.from_bytes(data[27:30] + b"\x00", "little") + 1
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        width = int.from_bytes(data[26:28], "little") & 0x3FFF
        height = int.from_bytes(data[28:30], "little") & 0x3FFF
        return width, height
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        width = (bits & 0x3FFF) + 1
        height = ((bits >> 14) & 0x3FFF) + 1
        return width, height
    return None

__all__ = [
    "DecodeImageError",
    "EncodedImage",
    "EncodeImageError",
    "ImageProcessingError",
    "MAX_DIMENSION",
    "PromptImageMode",
    "ReadImageError",
    "UnsupportedImageFormatError",
    "load_for_prompt_bytes",
]
