"""Image processing errors owned by ``codex-utils-image::error``."""

from __future__ import annotations

import mimetypes
from pathlib import Path


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


def _guess_mime(path: str | Path) -> str:
    mime, _encoding = mimetypes.guess_type(Path(path).name)
    return mime or "unknown"


__all__ = [
    "DecodeImageError",
    "EncodeImageError",
    "ImageProcessingError",
    "ReadImageError",
    "UnsupportedImageFormatError",
]
