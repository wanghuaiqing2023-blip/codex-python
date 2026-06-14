"""Small semantic equivalent of ratatui text values."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Union

from .style import Style


@dataclass(frozen=True)
class Span:
    content: str
    style: Style = Style()

    @classmethod
    def raw(cls, content: object) -> "Span":
        return cls(str(content))

    @classmethod
    def styled(cls, content: object, style: Style) -> "Span":
        return cls(str(content), style)

    @property
    def width(self) -> int:
        return len(self.content)

    def to_rich_text(self):
        from pycodex.tui.textual_compat import Text as RichText

        return RichText(self.content, style=self.style.to_rich_style())


@dataclass(frozen=True)
class Line:
    spans: tuple[Span, ...] = ()

    @classmethod
    def raw(cls, content: object) -> "Line":
        return cls((Span.raw(content),))

    @classmethod
    def from_spans(cls, spans: Iterable[Union[Span, str]]) -> "Line":
        return cls(tuple(span if isinstance(span, Span) else Span.raw(span) for span in spans))

    @property
    def plain(self) -> str:
        return "".join(span.content for span in self.spans)

    @property
    def width(self) -> int:
        return sum(span.width for span in self.spans)

    def to_rich_text(self):
        from pycodex.tui.textual_compat import Text as RichText

        rich = RichText()
        for span in self.spans:
            rich.append(span.content, style=span.style.to_rich_style())
        return rich


@dataclass(frozen=True)
class Text:
    lines: tuple[Line, ...] = ()

    @classmethod
    def raw(cls, content: object) -> "Text":
        return cls(tuple(Line.raw(line) for line in str(content).splitlines() or [""]))

    @classmethod
    def from_lines(cls, lines: Iterable[Union[Line, str]]) -> "Text":
        return cls(tuple(line if isinstance(line, Line) else Line.raw(line) for line in lines))

    @property
    def plain(self) -> str:
        return "\n".join(line.plain for line in self.lines)

    def to_rich_text(self):
        from pycodex.tui.textual_compat import Text as RichText

        rich = RichText()
        for index, line in enumerate(self.lines):
            if index:
                rich.append("\n")
            for span in line.spans:
                rich.append(span.content, style=span.style.to_rich_style())
        return rich


__all__ = ["Line", "Span", "Text"]

