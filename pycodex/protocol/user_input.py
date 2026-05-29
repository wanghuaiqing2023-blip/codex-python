"""User input protocol types.

Ported from ``codex/codex-rs/protocol/src/user_input.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .models import ImageDetail


MAX_USER_INPUT_TEXT_CHARS = 1 << 20
JsonValue = Any


def _mapping(value: JsonValue, label: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise TypeError(f"{label} must be a mapping")
    return value


def _required_str(value: dict[str, JsonValue], key: str) -> str:
    raw = value.get(key)
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_str(value: dict[str, JsonValue], key: str) -> str | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return raw


def _optional_detail(value: dict[str, JsonValue], key: str) -> ImageDetail | None:
    raw = value.get(key)
    if raw is None:
        return None
    if not isinstance(raw, str):
        raise TypeError(f"{key} must be a string")
    return ImageDetail(raw)


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise TypeError("start must be an integer")
        if isinstance(self.end, bool) or not isinstance(self.end, int):
            raise TypeError("end must be an integer")
        if self.start < 0:
            raise ValueError("start must be non-negative")
        if self.end < 0:
            raise ValueError("end must be non-negative")

    @classmethod
    def from_range(cls, start: int, end: int) -> "ByteRange":
        return cls(start=start, end=end)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "ByteRange":
        data = _mapping(value, "byte range")
        start = data.get("start")
        end = data.get("end")
        if isinstance(start, bool) or not isinstance(start, int):
            raise TypeError("start must be an integer")
        if isinstance(end, bool) or not isinstance(end, int):
            raise TypeError("end must be an integer")
        return cls(start=start, end=end)

    def to_mapping(self) -> dict[str, int]:
        return {"start": self.start, "end": self.end}


@dataclass
class TextElement:
    byte_range: ByteRange
    _placeholder: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.byte_range, ByteRange):
            raise TypeError("byte_range must be a ByteRange")
        if self._placeholder is not None and not isinstance(self._placeholder, str):
            raise TypeError("placeholder must be a string or None")

    @classmethod
    def new(cls, byte_range: ByteRange, placeholder: str | None) -> "TextElement":
        return cls(byte_range=byte_range, _placeholder=placeholder)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "TextElement":
        data = _mapping(value, "text element")
        return cls(
            byte_range=ByteRange.from_mapping(data["byte_range"]),
            _placeholder=_optional_str(data, "placeholder"),
        )

    def map_range(self, map_fn: Callable[[ByteRange], ByteRange]) -> "TextElement":
        mapped = map_fn(self.byte_range)
        if not isinstance(mapped, ByteRange):
            raise TypeError("map_range callback must return a ByteRange")
        return TextElement(byte_range=mapped, _placeholder=self._placeholder)

    def set_placeholder(self, placeholder: str | None) -> None:
        if placeholder is not None and not isinstance(placeholder, str):
            raise TypeError("placeholder must be a string or None")
        self._placeholder = placeholder

    def placeholder_for_conversion_only(self) -> str | None:
        return self._placeholder

    def placeholder(self, text: str) -> str | None:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        if self._placeholder is not None:
            return self._placeholder
        encoded = text.encode("utf-8")
        if self.byte_range.start < 0 or self.byte_range.end < self.byte_range.start or self.byte_range.end > len(encoded):
            return None
        try:
            return encoded[self.byte_range.start : self.byte_range.end].decode("utf-8")
        except UnicodeDecodeError:
            return None

    def to_mapping(self) -> dict[str, object]:
        return {
            "byte_range": self.byte_range.to_mapping(),
            "placeholder": self.placeholder_for_conversion_only(),
        }


@dataclass(frozen=True)
class UserInput:
    type: str
    text: str | None = None
    text_elements: tuple[TextElement, ...] = ()
    image_url: str | None = None
    path: Path | str | None = None
    detail: ImageDetail | None = None
    name: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.type, str):
            raise TypeError("type must be a string")
        if self.detail is not None and not isinstance(self.detail, ImageDetail):
            if isinstance(self.detail, str):
                object.__setattr__(self, "detail", ImageDetail(self.detail))
            else:
                raise TypeError("detail must be an ImageDetail or None")
        if self.type == "text":
            if not isinstance(self.text, str):
                raise TypeError("text input requires text")
            if isinstance(self.text_elements, str) or not isinstance(self.text_elements, (list, tuple)):
                raise TypeError("text_elements must be a list or tuple")
            object.__setattr__(self, "text_elements", tuple(self.text_elements))
            if not all(isinstance(element, TextElement) for element in self.text_elements):
                raise TypeError("text_elements entries must be TextElement")
            if self.image_url is not None or self.path is not None or self.detail is not None or self.name is not None:
                raise ValueError("text input cannot include image_url, path, detail, or name")
            return
        if self.type == "image":
            if not isinstance(self.image_url, str):
                raise TypeError("image input requires image_url")
            if self.text is not None or self.text_elements or self.path is not None or self.name is not None:
                raise ValueError("image input cannot include text, text_elements, path, or name")
            return
        if self.type == "local_image":
            if not isinstance(self.path, (str, Path)):
                raise TypeError("local_image input requires path")
            object.__setattr__(self, "path", Path(self.path))
            if self.text is not None or self.text_elements or self.image_url is not None or self.name is not None:
                raise ValueError("local_image input cannot include text, text_elements, image_url, or name")
            return
        if self.type == "skill":
            if not isinstance(self.name, str):
                raise TypeError("skill input requires name")
            if not isinstance(self.path, (str, Path)):
                raise TypeError("skill input requires path")
            object.__setattr__(self, "path", Path(self.path))
            if self.text is not None or self.text_elements or self.image_url is not None or self.detail is not None:
                raise ValueError("skill input cannot include text, text_elements, image_url, or detail")
            return
        if self.type == "mention":
            if not isinstance(self.name, str):
                raise TypeError("mention input requires name")
            if not isinstance(self.path, str):
                raise TypeError("mention input requires path")
            if self.text is not None or self.text_elements or self.image_url is not None or self.detail is not None:
                raise ValueError("mention input cannot include text, text_elements, image_url, or detail")
            return
        raise ValueError(f"unknown user input type: {self.type}")

    @classmethod
    def text_input(cls, text: str, text_elements: tuple[TextElement, ...] = ()) -> "UserInput":
        return cls(type="text", text=text, text_elements=text_elements)

    @classmethod
    def image(cls, image_url: str, detail: ImageDetail | None = None) -> "UserInput":
        return cls(type="image", image_url=image_url, detail=detail)

    @classmethod
    def local_image(cls, path: Path, detail: ImageDetail | None = None) -> "UserInput":
        return cls(type="local_image", path=path, detail=detail)

    @classmethod
    def skill(cls, name: str, path: Path) -> "UserInput":
        return cls(type="skill", name=name, path=path)

    @classmethod
    def mention(cls, name: str, path: str) -> "UserInput":
        return cls(type="mention", name=name, path=path)

    @classmethod
    def from_mapping(cls, value: JsonValue) -> "UserInput":
        data = _mapping(value, "user input")
        input_type = _required_str(data, "type")
        if input_type == "text":
            text_elements = data.get("text_elements", ())
            if isinstance(text_elements, str) or not isinstance(text_elements, (list, tuple)):
                raise TypeError("text_elements must be a list")
            return cls.text_input(
                _required_str(data, "text"),
                tuple(TextElement.from_mapping(item) for item in text_elements),
            )
        if input_type == "image":
            return cls.image(
                _required_str(data, "image_url"),
                _optional_detail(data, "detail"),
            )
        if input_type == "local_image":
            return cls.local_image(
                Path(_required_str(data, "path")),
                _optional_detail(data, "detail"),
            )
        if input_type == "skill":
            return cls.skill(_required_str(data, "name"), Path(_required_str(data, "path")))
        if input_type == "mention":
            return cls.mention(_required_str(data, "name"), _required_str(data, "path"))
        raise ValueError(f"unknown user input type: {input_type}")

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {"type": self.type}
        if self.type == "text":
            data["text"] = self.text
            data["text_elements"] = [element.to_mapping() for element in self.text_elements]
        elif self.type == "image":
            data["image_url"] = self.image_url
            if self.detail is not None:
                data["detail"] = self.detail.value
        elif self.type == "local_image":
            data["path"] = str(self.path)
            if self.detail is not None:
                data["detail"] = self.detail.value
        elif self.type == "skill":
            data["name"] = self.name
            data["path"] = str(self.path)
        elif self.type == "mention":
            data["name"] = self.name
            data["path"] = str(self.path)
        return data
