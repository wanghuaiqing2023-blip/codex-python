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


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

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
        return TextElement(byte_range=map_fn(self.byte_range), _placeholder=self._placeholder)

    def set_placeholder(self, placeholder: str | None) -> None:
        self._placeholder = placeholder

    def placeholder_for_conversion_only(self) -> str | None:
        return self._placeholder

    def placeholder(self, text: str) -> str | None:
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
            return cls.text_input(
                _required_str(data, "text"),
                tuple(TextElement.from_mapping(item) for item in data.get("text_elements", ())),
            )
        if input_type == "image":
            raw_detail = data.get("detail")
            return cls.image(
                _required_str(data, "image_url"),
                ImageDetail(str(raw_detail)) if raw_detail is not None else None,
            )
        if input_type == "local_image":
            raw_detail = data.get("detail")
            return cls.local_image(
                Path(_required_str(data, "path")),
                ImageDetail(str(raw_detail)) if raw_detail is not None else None,
            )
        if input_type == "skill":
            return cls.skill(_required_str(data, "name"), Path(_required_str(data, "path")))
        if input_type == "mention":
            return cls.mention(_required_str(data, "name"), _required_str(data, "path"))
        raise ValueError(f"unknown user input type: {input_type}")

    def to_mapping(self) -> dict[str, object]:
        data: dict[str, object] = {"type": self.type}
        if self.type == "text":
            data["text"] = self.text or ""
            data["text_elements"] = [element.to_mapping() for element in self.text_elements]
        elif self.type == "image":
            data["image_url"] = self.image_url or ""
            if self.detail is not None:
                data["detail"] = self.detail.value
        elif self.type == "local_image":
            data["path"] = str(self.path)
            if self.detail is not None:
                data["detail"] = self.detail.value
        elif self.type == "skill":
            data["name"] = self.name or ""
            data["path"] = str(self.path)
        elif self.type == "mention":
            data["name"] = self.name or ""
            data["path"] = str(self.path)
        return data
