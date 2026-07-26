from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from pycodex.protocol import ContentItem, ResponseInputItem, ResponseItem


class ContextualUserFragment(Protocol):
    @classmethod
    def role(cls) -> str: ...

    def markers(self) -> tuple[str, str]: ...

    @classmethod
    def type_markers(cls) -> tuple[str, str]: ...

    @classmethod
    def matches_text(cls, text: str) -> bool: ...

    def body(self) -> str: ...

    def render(self) -> str: ...

    def into_response_input_item(self) -> ResponseInputItem: ...

    def into_response_item(self) -> ResponseItem: ...


class FragmentRegistration(Protocol):
    def matches_text(self, text: str) -> bool: ...


@dataclass(frozen=True)
class FragmentRegistrationProxy:
    fragment_type: type[Any]

    @classmethod
    def new(cls, fragment_type: type[Any]) -> "FragmentRegistrationProxy":
        return cls(fragment_type)

    def __post_init__(self) -> None:
        if not isinstance(self.fragment_type, type):
            raise TypeError("fragment_type must be a type")
        if not callable(getattr(self.fragment_type, "matches_text", None)):
            raise TypeError("fragment_type must provide matches_text")

    def matches_text(self, text: str) -> bool:
        if not isinstance(text, str):
            raise TypeError("text must be a string")
        return bool(self.fragment_type.matches_text(text))


def matches_marked_text(start_marker: str, end_marker: str, text: str) -> bool:
    if not start_marker or not end_marker:
        return False
    leading_trimmed = text.lstrip()
    trailing_trimmed = leading_trimmed.rstrip()
    return leading_trimmed[: len(start_marker)].lower() == start_marker.lower() and trailing_trimmed[
        len(trailing_trimmed) - len(end_marker) :
    ].lower() == end_marker.lower()


@dataclass(frozen=True)
class ContextualUserFragmentBase:
    @classmethod
    def role(cls) -> str:
        return "user"

    def markers(self) -> tuple[str, str]:
        return self.type_markers()

    @classmethod
    def type_markers(cls) -> tuple[str, str]:
        return "", ""

    @classmethod
    def matches_text(cls, text: str) -> bool:
        start_marker, end_marker = cls.type_markers()
        return matches_marked_text(start_marker, end_marker, text)

    def body(self) -> str:
        return ""

    def render(self) -> str:
        start_marker, end_marker = self.markers()
        body = self.body()
        if not start_marker and not end_marker:
            return body
        return f"{start_marker}{body}{end_marker}"

    def into_response_input_item(self) -> ResponseInputItem:
        return ResponseInputItem.message(self.role(), (ContentItem.input_text(self.render()),))

    def into_response_item(self) -> ResponseItem:
        return ResponseItem.message(self.role(), (ContentItem.input_text(self.render()),))


__all__ = [
    "ContextualUserFragment",
    "ContextualUserFragmentBase",
    "FragmentRegistration",
    "FragmentRegistrationProxy",
    "matches_marked_text",
]
