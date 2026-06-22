"""Image request/response models from Rust ``codex-api/src/images.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


JsonValue = Any


class ImageBackground(str, Enum):
    TRANSPARENT = "transparent"
    OPAQUE = "opaque"
    AUTO = "auto"


class ImageQuality(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    AUTO = "auto"


@dataclass(frozen=True)
class ImageUrl:
    image_url: str

    @classmethod
    def from_json_dict(cls, value: JsonValue) -> "ImageUrl":
        data = _as_dict(value, "image url")
        return cls(image_url=_required_str(data, "image_url"))

    def to_json_dict(self) -> dict[str, JsonValue]:
        return {"image_url": self.image_url}


@dataclass(frozen=True)
class ImageGenerationRequest:
    prompt: str
    model: str
    background: ImageBackground | None = None
    n: int | None = None
    quality: ImageQuality | None = None
    size: str | None = None

    def to_json_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {"prompt": self.prompt, "model": self.model}
        _put_optional_enum(value, "background", self.background)
        _put_optional(value, "n", self.n)
        _put_optional_enum(value, "quality", self.quality)
        _put_optional(value, "size", self.size)
        return value


@dataclass(frozen=True)
class ImageEditRequest:
    images: list[ImageUrl]
    prompt: str
    model: str
    background: ImageBackground | None = None
    n: int | None = None
    quality: ImageQuality | None = None
    size: str | None = None

    def to_json_dict(self) -> dict[str, JsonValue]:
        value: dict[str, JsonValue] = {
            "images": [image.to_json_dict() for image in self.images],
            "prompt": self.prompt,
            "model": self.model,
        }
        _put_optional_enum(value, "background", self.background)
        _put_optional(value, "n", self.n)
        _put_optional_enum(value, "quality", self.quality)
        _put_optional(value, "size", self.size)
        return value


@dataclass(frozen=True)
class ImageData:
    b64_json: str

    @classmethod
    def from_json_dict(cls, value: JsonValue) -> "ImageData":
        data = _as_dict(value, "image data")
        return cls(b64_json=_required_str(data, "b64_json"))


@dataclass(frozen=True)
class ImageResponse:
    created: int
    data: list[ImageData]
    background: ImageBackground | None = None
    quality: ImageQuality | None = None
    size: str | None = None

    @classmethod
    def from_json_dict(cls, value: JsonValue) -> "ImageResponse":
        data = _as_dict(value, "image response")
        raw_data = data.get("data")
        if not isinstance(raw_data, list):
            raise KeyError("data")
        return cls(
            created=_required_int(data, "created"),
            data=[ImageData.from_json_dict(item) for item in raw_data],
            background=_optional_enum(data, "background", ImageBackground),
            quality=_optional_enum(data, "quality", ImageQuality),
            size=_optional_str(data, "size"),
        )


def _put_optional(value: dict[str, JsonValue], key: str, item: JsonValue | None) -> None:
    if item is not None:
        value[key] = item


def _put_optional_enum(value: dict[str, JsonValue], key: str, item: Enum | None) -> None:
    if item is not None:
        value[key] = item.value


def _optional_enum(data: dict[str, JsonValue], key: str, enum_type: type[Enum]) -> Any:
    raw = data.get(key)
    if raw is None:
        return None
    return enum_type(raw)


def _optional_str(data: dict[str, JsonValue], key: str) -> str | None:
    raw = data.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _required_str(data: dict[str, JsonValue], key: str) -> str:
    raw = data.get(key)
    if not isinstance(raw, str):
        raise KeyError(key)
    return raw


def _required_int(data: dict[str, JsonValue], key: str) -> int:
    raw = data.get(key)
    if not isinstance(raw, int) or isinstance(raw, bool) or raw < 0:
        raise KeyError(key)
    return raw


def _as_dict(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


__all__ = [
    "ImageBackground",
    "ImageData",
    "ImageEditRequest",
    "ImageGenerationRequest",
    "ImageQuality",
    "ImageResponse",
    "ImageUrl",
]
