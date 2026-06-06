"""Strict string templating ported from ``codex-utils-template``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Mapping


class TemplateParseErrorKind(str, Enum):
    EMPTY_PLACEHOLDER = "empty_placeholder"
    NESTED_PLACEHOLDER = "nested_placeholder"
    UNMATCHED_CLOSING_DELIMITER = "unmatched_closing_delimiter"
    UNTERMINATED_PLACEHOLDER = "unterminated_placeholder"


class TemplateRenderErrorKind(str, Enum):
    DUPLICATE_VALUE = "duplicate_value"
    EXTRA_VALUE = "extra_value"
    MISSING_VALUE = "missing_value"


@dataclass(frozen=True)
class TemplateParseError(Exception):
    kind: TemplateParseErrorKind
    start: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", TemplateParseErrorKind(self.kind))
        if isinstance(self.start, bool) or not isinstance(self.start, int):
            raise TypeError("start must be an integer")
        Exception.__init__(self, str(self))

    @classmethod
    def empty_placeholder(cls, start: int) -> "TemplateParseError":
        return cls(TemplateParseErrorKind.EMPTY_PLACEHOLDER, start)

    @classmethod
    def nested_placeholder(cls, start: int) -> "TemplateParseError":
        return cls(TemplateParseErrorKind.NESTED_PLACEHOLDER, start)

    @classmethod
    def unmatched_closing_delimiter(cls, start: int) -> "TemplateParseError":
        return cls(TemplateParseErrorKind.UNMATCHED_CLOSING_DELIMITER, start)

    @classmethod
    def unterminated_placeholder(cls, start: int) -> "TemplateParseError":
        return cls(TemplateParseErrorKind.UNTERMINATED_PLACEHOLDER, start)

    def __str__(self) -> str:
        if self.kind is TemplateParseErrorKind.EMPTY_PLACEHOLDER:
            return f"template placeholder at byte {self.start} is empty"
        if self.kind is TemplateParseErrorKind.NESTED_PLACEHOLDER:
            return f"template placeholder starting at byte {self.start} contains a nested `{{{{`"
        if self.kind is TemplateParseErrorKind.UNMATCHED_CLOSING_DELIMITER:
            return f"template contains an unmatched `}}}}` at byte {self.start}"
        return f"template placeholder starting at byte {self.start} is missing `}}}}`"


@dataclass(frozen=True)
class TemplateRenderError(Exception):
    kind: TemplateRenderErrorKind
    name: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", TemplateRenderErrorKind(self.kind))
        if not isinstance(self.name, str):
            raise TypeError("name must be a string")
        Exception.__init__(self, str(self))

    @classmethod
    def duplicate_value(cls, name: str) -> "TemplateRenderError":
        return cls(TemplateRenderErrorKind.DUPLICATE_VALUE, name)

    @classmethod
    def extra_value(cls, name: str) -> "TemplateRenderError":
        return cls(TemplateRenderErrorKind.EXTRA_VALUE, name)

    @classmethod
    def missing_value(cls, name: str) -> "TemplateRenderError":
        return cls(TemplateRenderErrorKind.MISSING_VALUE, name)

    def __str__(self) -> str:
        if self.kind is TemplateRenderErrorKind.DUPLICATE_VALUE:
            return f"template value `{self.name}` was provided more than once"
        if self.kind is TemplateRenderErrorKind.EXTRA_VALUE:
            return f"template value `{self.name}` is not used by this template"
        return f"template placeholder `{self.name}` is missing a value"


@dataclass(frozen=True)
class TemplateError(Exception):
    parse: TemplateParseError | None = None
    render: TemplateRenderError | None = None

    def __post_init__(self) -> None:
        if (self.parse is None) == (self.render is None):
            raise ValueError("TemplateError requires exactly one parse or render error")
        if self.parse is not None and not isinstance(self.parse, TemplateParseError):
            raise TypeError("parse must be TemplateParseError or None")
        if self.render is not None and not isinstance(self.render, TemplateRenderError):
            raise TypeError("render must be TemplateRenderError or None")
        Exception.__init__(self, str(self))

    @classmethod
    def from_parse(cls, error: TemplateParseError) -> "TemplateError":
        return cls(parse=error)

    @classmethod
    def from_render(cls, error: TemplateRenderError) -> "TemplateError":
        return cls(render=error)

    def __str__(self) -> str:
        return str(self.parse if self.parse is not None else self.render)


@dataclass(frozen=True)
class _Segment:
    kind: str
    value: str


@dataclass(frozen=True)
class Template:
    _segments: tuple[_Segment, ...]
    _placeholders: tuple[str, ...]

    @classmethod
    def parse(cls, source: str) -> "Template":
        if not isinstance(source, str):
            raise TypeError("source must be a string")
        source_bytes = source.encode("utf-8")
        placeholders: set[str] = set()
        segments: list[_Segment] = []
        literal_start = 0
        cursor = 0

        while cursor < len(source_bytes):
            rest = source_bytes[cursor:]
            if rest.startswith(b"{{{{"):
                _push_literal(segments, _decode_slice(source_bytes, literal_start, cursor))
                _push_literal(segments, "{{")
                cursor += 4
                literal_start = cursor
                continue
            if rest.startswith(b"}}}}"):
                _push_literal(segments, _decode_slice(source_bytes, literal_start, cursor))
                _push_literal(segments, "}}")
                cursor += 4
                literal_start = cursor
                continue
            if rest.startswith(b"{{"):
                _push_literal(segments, _decode_slice(source_bytes, literal_start, cursor))
                placeholder, next_cursor = _parse_placeholder(source_bytes, cursor)
                placeholders.add(placeholder)
                segments.append(_Segment("placeholder", placeholder))
                cursor = next_cursor
                literal_start = cursor
                continue
            if rest.startswith(b"}}"):
                raise TemplateParseError.unmatched_closing_delimiter(cursor)
            cursor += _next_utf8_char_len(source_bytes, cursor)

        _push_literal(segments, _decode_slice(source_bytes, literal_start, len(source_bytes)))
        return cls(tuple(segments), tuple(sorted(placeholders)))

    def placeholders(self) -> tuple[str, ...]:
        return self._placeholders

    def render(self, variables: Mapping[str, str] | Iterable[tuple[str, str]]) -> str:
        values = _build_variable_map(variables)
        for placeholder in self._placeholders:
            if placeholder not in values:
                raise TemplateRenderError.missing_value(placeholder)
        for name in sorted(values):
            if name not in self._placeholders:
                raise TemplateRenderError.extra_value(name)

        rendered: list[str] = []
        for segment in self._segments:
            if segment.kind == "literal":
                rendered.append(segment.value)
            else:
                try:
                    rendered.append(values[segment.value])
                except KeyError as exc:
                    raise TemplateRenderError.missing_value(segment.value) from exc
        return "".join(rendered)


def render(template: str, variables: Mapping[str, str] | Iterable[tuple[str, str]]) -> str:
    try:
        parsed = Template.parse(template)
    except TemplateParseError as exc:
        raise TemplateError.from_parse(exc) from exc
    try:
        return parsed.render(variables)
    except TemplateRenderError as exc:
        raise TemplateError.from_render(exc) from exc


def _push_literal(segments: list[_Segment], literal: str) -> None:
    if literal == "":
        return
    if segments and segments[-1].kind == "literal":
        prior = segments.pop()
        segments.append(_Segment("literal", prior.value + literal))
    else:
        segments.append(_Segment("literal", literal))


def _parse_placeholder(source_bytes: bytes, start: int) -> tuple[str, int]:
    placeholder_start = start + 2
    cursor = placeholder_start
    while cursor < len(source_bytes):
        rest = source_bytes[cursor:]
        if rest.startswith(b"{{"):
            raise TemplateParseError.nested_placeholder(start)
        if rest.startswith(b"}}"):
            placeholder = _decode_slice(source_bytes, placeholder_start, cursor).strip()
            if placeholder == "":
                raise TemplateParseError.empty_placeholder(start)
            return placeholder, cursor + 2
        cursor += _next_utf8_char_len(source_bytes, cursor)
    raise TemplateParseError.unterminated_placeholder(start)


def _build_variable_map(variables: Mapping[str, str] | Iterable[tuple[str, str]]) -> dict[str, str]:
    iterator = variables.items() if isinstance(variables, Mapping) else variables
    values: dict[str, str] = {}
    for name, value in iterator:
        name_str = str(name)
        if name_str in values:
            raise TemplateRenderError.duplicate_value(name_str)
        values[name_str] = str(value)
    return values


def _decode_slice(source_bytes: bytes, start: int, end: int) -> str:
    return source_bytes[start:end].decode("utf-8")


def _next_utf8_char_len(source_bytes: bytes, cursor: int) -> int:
    byte = source_bytes[cursor]
    if byte < 0x80:
        return 1
    if byte < 0xE0:
        return 2
    if byte < 0xF0:
        return 3
    return 4


__all__ = [
    "Template",
    "TemplateError",
    "TemplateParseError",
    "TemplateParseErrorKind",
    "TemplateRenderError",
    "TemplateRenderErrorKind",
    "render",
]
