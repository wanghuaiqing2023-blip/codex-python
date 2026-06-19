"""User, assistant, reasoning, and streaming message history cells.

Upstream source: ``codex/codex-rs/tui/src/history_cell/messages.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from .._porting import RustTuiModule
from ..line_truncation import Line, Span
from ..terminal_hyperlinks import (
    HyperlinkLine,
    annotate_web_urls,
    plain_hyperlink_lines,
    prefix_hyperlink_lines,
    visible_lines,
)
from .base import adaptive_wrap_lines, plain_lines

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="history_cell::messages",
    source="codex/codex-rs/tui/src/history_cell/messages.rs",
)

LIVE_PREFIX_COLS = 2
USER_MESSAGE_STYLE = "user_message"
USER_TEXT_ELEMENT_STYLE = "user_message cyan"
SUMMARY_STYLE = "dim italic"
ASSISTANT_PREFIX = "> "
ASSISTANT_CONTINUATION_PREFIX = "  "


@dataclass(frozen=True)
class ByteRange:
    start: int
    end: int

    @classmethod
    def coerce(cls, value: Any) -> "ByteRange":
        if isinstance(value, cls):
            return value
        if isinstance(value, range):
            return cls(value.start, value.stop)
        if isinstance(value, tuple) and len(value) == 2:
            return cls(int(value[0]), int(value[1]))
        start = getattr(value, "start", None)
        end = getattr(value, "end", None)
        if start is not None and end is not None:
            return cls(int(start), int(end))
        raise TypeError(f"cannot coerce byte range from {value!r}")


@dataclass(frozen=True)
class TextElement:
    byte_range: ByteRange
    text: str | None = None

    @classmethod
    def new(cls, byte_range: Any, text: str | None = None) -> "TextElement":
        return cls(ByteRange.coerce(byte_range), text)

    @classmethod
    def coerce(cls, value: Any) -> "TextElement":
        if isinstance(value, cls):
            return value
        byte_range = getattr(value, "byte_range", getattr(value, "range", None))
        text = getattr(value, "text", getattr(value, "name", None))
        if isinstance(value, dict):
            byte_range = value.get("byte_range", value.get("range"))
            text = value.get("text", value.get("name"))
        return cls.new(byte_range, text)


def line_text(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def raw_lines_from_source(source: str) -> list[Line]:
    if source == "":
        return []
    parts = source.split("\n")
    if parts and parts[-1] == "":
        parts.pop()
    return [Line.from_text(part) for part in parts]


def local_image_label_text(label_number: int) -> str:
    return f"[Image #{int(label_number)}]"


def _byte_to_char_index(text: str, byte_index: int) -> int | None:
    if byte_index < 0:
        return None
    encoded = text.encode("utf-8")
    if byte_index > len(encoded):
        return None
    try:
        return len(encoded[:byte_index].decode("utf-8"))
    except UnicodeDecodeError:
        return None


def build_user_message_lines_with_elements(
    message: str,
    elements: Iterable[TextElement | Any],
    style: Any = USER_MESSAGE_STYLE,
    element_style: Any = USER_TEXT_ELEMENT_STYLE,
) -> list[Line]:
    sorted_elements = sorted(
        (TextElement.coerce(element) for element in elements),
        key=lambda element: element.byte_range.start,
    )
    lines: list[Line] = []
    byte_offset = 0
    for line_part in message.split("\n"):
        line_byte_len = len(line_part.encode("utf-8"))
        line_start = byte_offset
        line_end = line_start + line_byte_len
        cursor = line_start
        spans: list[Span] = []

        for element in sorted_elements:
            start = max(element.byte_range.start, line_start)
            end = min(element.byte_range.end, line_end)
            if start >= end:
                continue
            rel_start = _byte_to_char_index(line_part, start - line_start)
            rel_end = _byte_to_char_index(line_part, end - line_start)
            rel_cursor = _byte_to_char_index(line_part, cursor - line_start)
            if rel_start is None or rel_end is None or rel_cursor is None:
                continue
            if cursor < start:
                spans.append(Span(line_part[rel_cursor:rel_start], None))
            spans.append(Span(line_part[rel_start:rel_end], element_style))
            cursor = end

        rel_cursor = _byte_to_char_index(line_part, cursor - line_start)
        if rel_cursor is not None and cursor < line_end:
            spans.append(Span(line_part[rel_cursor:], None))

        if spans:
            lines.append(Line.from_spans(spans, style=style))
        else:
            lines.append(Line.from_text(line_part, style=style))
        byte_offset = line_end + 1
    return lines


def remote_image_display_line(style: Any, index: int) -> Line:
    return Line.from_text(local_image_label_text(index), style=style)


def trim_trailing_blank_lines(lines: Iterable[Line]) -> list[Line]:
    out = list(lines)
    while out and all(span.content.strip() == "" for span in out[-1].spans):
        out.pop()
    return out


@dataclass
class UserHistoryCell:
    message: str
    text_elements: list[TextElement] = field(default_factory=list)
    local_image_paths: list[Path] = field(default_factory=list)
    remote_image_urls: list[str] = field(default_factory=list)

    def display_lines(self, width: int) -> list[Line]:
        wrap_width = max(1, int(width) - LIVE_PREFIX_COLS - 1)
        wrapped_remote_images: list[Line] | None = None
        if self.remote_image_urls:
            image_lines = [
                remote_image_display_line(USER_TEXT_ELEMENT_STYLE, index + 1)
                for index, _url in enumerate(self.remote_image_urls)
            ]
            wrapped_remote_images = adaptive_wrap_lines(image_lines, wrap_width)

        wrapped_message: list[Line] | None = None
        if self.message or self.text_elements:
            if self.text_elements:
                raw = build_user_message_lines_with_elements(
                    self.message,
                    self.text_elements,
                    USER_MESSAGE_STYLE,
                    USER_TEXT_ELEMENT_STYLE,
                )
            else:
                trimmed = self.message.rstrip("\r\n")
                raw = [Line.from_text(part, style=USER_MESSAGE_STYLE) for part in trimmed.split("\n")]
            wrapped = adaptive_wrap_lines(raw, wrap_width)
            wrapped_message = trim_trailing_blank_lines(wrapped)
            if not wrapped_message:
                wrapped_message = None

        if wrapped_remote_images is None and wrapped_message is None:
            return []

        lines = [Line.from_text("", style=USER_MESSAGE_STYLE)]
        if wrapped_remote_images is not None:
            lines.extend(adaptive_wrap_lines(wrapped_remote_images, max(1, int(width)), "  ", "  "))
            if wrapped_message is not None:
                lines.append(Line.from_text("", style=USER_MESSAGE_STYLE))
        if wrapped_message is not None:
            lines.extend(adaptive_wrap_lines(wrapped_message, max(1, int(width)), ASSISTANT_PREFIX, "  "))
        lines.append(Line.from_text("", style=USER_MESSAGE_STYLE))
        return lines

    def raw_lines(self) -> list[Line]:
        lines = raw_lines_from_source(self.message.rstrip("\r\n"))
        if self.remote_image_urls:
            if lines:
                lines.append(Line.from_text(""))
            lines.extend(
                Line.from_text(local_image_label_text(index + 1))
                for index, _url in enumerate(self.remote_image_urls)
            )
        return lines


@dataclass
class ReasoningSummaryCell:
    header: str
    content: str
    cwd: Path
    transcript_only: bool = False

    @classmethod
    def new(
        cls, header: str, content: str, cwd: str | Path, transcript_only: bool
    ) -> "ReasoningSummaryCell":
        return cls(str(header), str(content), Path(cwd), bool(transcript_only))

    def lines(self, width: int) -> list[Line]:
        source_lines = [Line.from_text(part, style=SUMMARY_STYLE) for part in self.content.splitlines()]
        if not source_lines and self.content:
            source_lines = [Line.from_text(self.content, style=SUMMARY_STYLE)]
        return adaptive_wrap_lines(source_lines, max(1, int(width)), ASSISTANT_PREFIX, "  ")

    def display_lines(self, width: int) -> list[Line]:
        return [] if self.transcript_only else self.lines(width)

    def transcript_lines(self, width: int) -> list[Line]:
        return self.lines(width)

    def raw_lines(self) -> list[Line]:
        if self.transcript_only:
            return []
        return raw_lines_from_source(self.content)


@dataclass
class AgentMessageCell:
    lines: list[HyperlinkLine]
    is_first_line: bool = True

    @classmethod
    def new(cls, lines: Iterable[Line | str], is_first_line: bool) -> "AgentMessageCell":
        return cls(plain_hyperlink_lines(lines), bool(is_first_line))

    @classmethod
    def new_hyperlink_lines(
        cls, lines: Iterable[HyperlinkLine], is_first_line: bool
    ) -> "AgentMessageCell":
        return cls(list(lines), bool(is_first_line))

    def display_lines(self, width: int) -> list[Line]:
        return visible_lines(self.display_hyperlink_lines(width))

    def display_hyperlink_lines(self, _width: int) -> list[HyperlinkLine]:
        return prefix_hyperlink_lines(
            self.lines,
            ASSISTANT_PREFIX if self.is_first_line else ASSISTANT_CONTINUATION_PREFIX,
            ASSISTANT_CONTINUATION_PREFIX,
        )

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(visible_lines(self.lines))

    def is_stream_continuation(self) -> bool:
        return not self.is_first_line


@dataclass
class AgentMarkdownCell:
    markdown_source: str
    cwd: Path

    @classmethod
    def new(cls, markdown_source: str, cwd: str | Path) -> "AgentMarkdownCell":
        return cls(str(markdown_source), Path(cwd))

    def display_lines(self, width: int) -> list[Line]:
        return visible_lines(self.display_hyperlink_lines(width))

    def display_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        source_lines = [Line.from_text(part) for part in self.markdown_source.splitlines()]
        if not source_lines and self.markdown_source:
            source_lines = [Line.from_text(self.markdown_source)]
        wrapped = adaptive_wrap_lines(source_lines, max(1, int(width) - LIVE_PREFIX_COLS), "", "")
        return prefix_hyperlink_lines(annotate_web_urls(wrapped), ASSISTANT_PREFIX, "  ")

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return raw_lines_from_source(self.markdown_source)


@dataclass
class StreamingAgentTailCell:
    lines: list[HyperlinkLine]
    is_first_line: bool = True

    @classmethod
    def new(
        cls, lines: Iterable[HyperlinkLine], is_first_line: bool
    ) -> "StreamingAgentTailCell":
        return cls(list(lines), bool(is_first_line))

    def display_lines(self, width: int) -> list[Line]:
        return visible_lines(self.display_hyperlink_lines(width))

    def display_hyperlink_lines(self, _width: int) -> list[HyperlinkLine]:
        return prefix_hyperlink_lines(
            self.lines,
            ASSISTANT_PREFIX if self.is_first_line else ASSISTANT_CONTINUATION_PREFIX,
            ASSISTANT_CONTINUATION_PREFIX,
        )

    def transcript_hyperlink_lines(self, width: int) -> list[HyperlinkLine]:
        return self.display_hyperlink_lines(width)

    def raw_lines(self) -> list[Line]:
        return plain_lines(self.display_lines(65535))

    def is_stream_continuation(self) -> bool:
        return not self.is_first_line


def new_user_prompt(
    message: str,
    text_elements: Iterable[TextElement | Any] | None = None,
    local_image_paths: Iterable[str | Path] | None = None,
    remote_image_urls: Iterable[str] | None = None,
) -> UserHistoryCell:
    return UserHistoryCell(
        str(message),
        [TextElement.coerce(element) for element in (text_elements or [])],
        [Path(path) for path in (local_image_paths or [])],
        [str(url) for url in (remote_image_urls or [])],
    )


def new_reasoning_summary_block(
    full_reasoning_buffer: str, cwd: str | Path
) -> ReasoningSummaryCell:
    trimmed = str(full_reasoning_buffer).strip()
    open_idx = trimmed.find("**")
    if open_idx >= 0:
        after_open = trimmed[open_idx + 2 :]
        close_rel = after_open.find("**")
        if close_rel >= 0:
            after_close_idx = open_idx + 2 + close_rel + 2
            if after_close_idx < len(trimmed):
                return ReasoningSummaryCell.new(
                    trimmed[:after_close_idx],
                    trimmed[after_close_idx:],
                    cwd,
                    False,
                )
    return ReasoningSummaryCell.new("", trimmed, cwd, True)


def display_lines(cell: Any, width: int) -> list[Line]:
    return cell.display_lines(width)


def raw_lines(cell: Any) -> list[Line]:
    return cell.raw_lines()


def transcript_lines(cell: Any, width: int) -> list[Line]:
    method = getattr(cell, "transcript_lines", None)
    return method(width) if callable(method) else cell.display_lines(width)


def display_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    method = getattr(cell, "display_hyperlink_lines", None)
    if callable(method):
        return method(width)
    return plain_hyperlink_lines(cell.display_lines(width))


def transcript_hyperlink_lines(cell: Any, width: int) -> list[HyperlinkLine]:
    method = getattr(cell, "transcript_hyperlink_lines", None)
    if callable(method):
        return method(width)
    return display_hyperlink_lines(cell, width)


def is_stream_continuation(cell: Any) -> bool:
    method = getattr(cell, "is_stream_continuation", None)
    return bool(method()) if callable(method) else False


__all__ = [
    "ASSISTANT_CONTINUATION_PREFIX",
    "ASSISTANT_PREFIX",
    "AgentMarkdownCell",
    "AgentMessageCell",
    "ByteRange",
    "LIVE_PREFIX_COLS",
    "RUST_MODULE",
    "ReasoningSummaryCell",
    "StreamingAgentTailCell",
    "TextElement",
    "UserHistoryCell",
    "build_user_message_lines_with_elements",
    "display_hyperlink_lines",
    "display_lines",
    "is_stream_continuation",
    "line_text",
    "local_image_label_text",
    "new_reasoning_summary_block",
    "new_user_prompt",
    "raw_lines",
    "raw_lines_from_source",
    "remote_image_display_line",
    "transcript_hyperlink_lines",
    "transcript_lines",
    "trim_trailing_blank_lines",
]
