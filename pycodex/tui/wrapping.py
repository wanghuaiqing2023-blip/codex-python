"""URL-aware text wrapping for ``codex-tui::wrapping``.

Rust source: ``codex/codex-rs/tui/src/wrapping.rs``.

This ports the module's user-visible wrapping contract with Python semantic
``Line``/``Span`` values.  It intentionally avoids a third-party textwrap clone;
the implementation preserves the Rust tests' important behavior: styled span
splitting, indent handling, URL-like detection, URL-preserving adaptive wrap,
and simple source ranges.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable, List, Optional, Sequence, Tuple, Union
from urllib.parse import urlparse

from ._porting import RustTuiModule
from .line_truncation import Line, Span, _display_width

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="wrapping",
    source="codex/codex-rs/tui/src/wrapping.rs",
)

_DECORATIVE_MARKERS = {"-", "*", "+", "•", "◦", "▪", ">", "|", "┃", "│", "┆", "┊", "┋", "┇", "┈", "┉"}


@dataclass
class RtOptions:
    width_value: int
    initial_indent_line: Line
    subsequent_indent_line: Line
    break_words_value: bool = True
    preserve_urls: bool = False
    no_hyphenation: bool = False

    @classmethod
    def new(cls, width: int) -> "RtOptions":
        return cls(width_value=max(0, int(width)), initial_indent_line=Line([]), subsequent_indent_line=Line([]))

    def clone(self) -> "RtOptions":
        return RtOptions(
            self.width_value,
            _line_from_any(self.initial_indent_line),
            _line_from_any(self.subsequent_indent_line),
            self.break_words_value,
            self.preserve_urls,
            self.no_hyphenation,
        )

    def width(self, width: int) -> "RtOptions":
        out = self.clone()
        out.width_value = max(0, int(width))
        return out

    def initial_indent(self, indent: Any) -> "RtOptions":
        out = self.clone()
        out.initial_indent_line = _line_from_any(indent)
        return out

    def subsequent_indent(self, indent: Any) -> "RtOptions":
        out = self.clone()
        out.subsequent_indent_line = _line_from_any(indent)
        return out

    def break_words(self, break_words: bool) -> "RtOptions":
        out = self.clone()
        out.break_words_value = bool(break_words)
        return out

    def word_separator(self, _separator: Any) -> "RtOptions":
        out = self.clone()
        out.preserve_urls = True
        return out

    def word_splitter(self, _splitter: Any) -> "RtOptions":
        out = self.clone()
        out.no_hyphenation = True
        return out

    def wrap_algorithm(self, _algorithm: Any) -> "RtOptions":
        return self.clone()

    def line_ending(self, _line_ending: Any) -> "RtOptions":
        return self.clone()


def from_(value: Any) -> RtOptions:
    if isinstance(value, RtOptions):
        return value.clone()
    return RtOptions.new(int(value))


def concat_line(line: Line) -> str:
    return "".join(span.content for span in line.spans)


def flatten_line(line: Line) -> str:
    return concat_line(line)


def line_contains_url_like(line: Line) -> bool:
    return text_contains_url_like(concat_line(line))


def line_has_mixed_url_and_non_url_tokens(line: Line) -> bool:
    return text_has_mixed_url_and_non_url_tokens(concat_line(line))


def text_contains_url_like(text: str) -> bool:
    return any(is_url_like_token(token) for token in text.split())


def text_has_mixed_url_and_non_url_tokens(text: str) -> bool:
    saw_url = False
    saw_non_url = False
    for raw_token in text.split():
        if is_url_like_token(raw_token):
            saw_url = True
        elif is_substantive_non_url_token(raw_token):
            saw_non_url = True
        if saw_url and saw_non_url:
            return True
    return False


def is_url_like_token(raw_token: str) -> bool:
    token = trim_url_token(raw_token)
    return bool(token) and (is_absolute_url_like(token) or is_bare_url_like(token))


def is_substantive_non_url_token(raw_token: str) -> bool:
    token = trim_url_token(raw_token)
    if not token or is_decorative_marker_token(raw_token, token):
        return False
    return any(ch.isalnum() for ch in token)


def is_decorative_marker_token(raw_token: str, token: str) -> bool:
    raw = raw_token.strip()
    return raw in _DECORATIVE_MARKERS or is_ordered_list_marker(raw, token)


def is_ordered_list_marker(raw_token: str, token: str) -> bool:
    return token.isdigit() and (raw_token.endswith(".") or raw_token.endswith(")"))


def trim_url_token(token: str) -> str:
    return token.strip("()[]{}<>,.;:!'\"")


def is_absolute_url_like(token: str) -> bool:
    if "://" not in token:
        return False
    parsed = urlparse(token)
    if parsed.scheme.lower() in {"http", "https", "ftp", "ftps", "ws", "wss"}:
        return bool(parsed.netloc)
    return has_valid_scheme_prefix(token)


def has_valid_scheme_prefix(token: str) -> bool:
    if "://" not in token:
        return False
    scheme, rest = token.split("://", 1)
    if not scheme or not rest:
        return False
    return bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*$", scheme))


def is_bare_url_like(token: str) -> bool:
    host_port, has_trailer = split_host_port_and_trailer(token)
    if not host_port:
        return False
    if not has_trailer and not host_port.lower().startswith("www."):
        return False
    host, port = split_host_and_port(host_port)
    if not host:
        return False
    if port is not None and not is_valid_port(port):
        return False
    return host.lower() == "localhost" or is_ipv4(host) or is_domain_name(host)


def split_host_port_and_trailer(token: str) -> Tuple[str, bool]:
    positions = [idx for idx in (token.find("/"), token.find("?"), token.find("#")) if idx >= 0]
    if not positions:
        return token, False
    idx = min(positions)
    return token[:idx], True


def split_host_and_port(host_port: str) -> Tuple[str, Optional[str]]:
    if host_port.startswith("["):
        return host_port, None
    if ":" in host_port:
        host, port = host_port.rsplit(":", 1)
        if host and port and port.isdigit():
            return host, port
    return host_port, None


def is_valid_port(port: str) -> bool:
    if not port or len(port) > 5 or not port.isdigit():
        return False
    return 0 <= int(port) <= 65535


def is_ipv4(host: str) -> bool:
    parts = host.split(".")
    if len(parts) != 4:
        return False
    try:
        return all(part != "" and 0 <= int(part) <= 255 for part in parts)
    except ValueError:
        return False


def is_domain_name(host: str) -> bool:
    host = host.lower()
    if "." not in host:
        return False
    labels = host.split(".")
    return is_tld(labels[-1]) and all(is_domain_label(label) for label in labels[:-1])


def is_tld(label: str) -> bool:
    return 2 <= len(label) <= 63 and label.isalpha() and label.isascii()


def is_domain_label(label: str) -> bool:
    if not label or len(label) > 63:
        return False
    return label[0].isalnum() and label[-1].isalnum() and all(ch.isalnum() or ch == "-" for ch in label)


def url_preserving_wrap_options(opts: RtOptions) -> RtOptions:
    out = from_(opts)
    out.preserve_urls = True
    out.no_hyphenation = True
    out.break_words_value = False
    return out


def adaptive_wrap_line(line: Line, base: Union[RtOptions, int]) -> List[Line]:
    opts = from_(base)
    if not line_contains_url_like(line):
        return word_wrap_line(line, opts)
    if line_has_mixed_url_and_non_url_tokens(line):
        return mixed_url_wrap_line(line, opts)
    return word_wrap_line(line, url_preserving_wrap_options(opts))


def adaptive_wrap_lines(lines: Iterable[Any], width_or_options: Union[RtOptions, int]) -> List[Line]:
    base = from_(width_or_options)
    out: List[Line] = []
    for idx, value in enumerate(lines):
        opts = base.clone() if idx == 0 else base.clone().initial_indent(base.subsequent_indent_line)
        out.extend(adaptive_wrap_line(_line_from_any(value), opts))
    return out


def word_wrap_line(line: Line, width_or_options: Union[RtOptions, int]) -> List[Line]:
    opts = from_(width_or_options)
    return _wrap_line(line, opts, preserve_urls=opts.preserve_urls)


def mixed_url_wrap_line(line: Line, opts: RtOptions) -> List[Line]:
    return _wrap_line(line, opts, preserve_urls=True, split_non_url=True)


def word_wrap_lines(lines: Iterable[Any], width_or_options: Union[RtOptions, int]) -> List[Line]:
    return _wrap_lines(lines, width_or_options, adaptive=False)


def word_wrap_lines_borrowed(lines: Iterable[Any], width_or_options: Union[RtOptions, int]) -> List[Line]:
    return word_wrap_lines(lines, width_or_options)


def _wrap_lines(lines: Iterable[Any], width_or_options: Union[RtOptions, int], adaptive: bool) -> List[Line]:
    base = from_(width_or_options)
    out: List[Line] = []
    for idx, value in enumerate(lines):
        opts = base.clone() if idx == 0 else base.clone().initial_indent(base.subsequent_indent_line)
        line = _line_from_any(value)
        out.extend(adaptive_wrap_line(line, opts) if adaptive else word_wrap_line(line, opts))
    return out


def wrap_ranges(text: str, width_or_options: Union[RtOptions, int]) -> List[range]:
    return [range(start, min(len(text), end) + 1) for start, end in _wrap_text_ranges(text, from_(width_or_options), trim=False)]


def wrap_ranges_trim(text: str, width_or_options: Union[RtOptions, int]) -> List[range]:
    return [range(start, end) for start, end in _wrap_text_ranges(text, from_(width_or_options), trim=True)]


def borrowed_slice_range(text: str, slice_text: str) -> Optional[range]:
    idx = text.find(slice_text)
    return None if idx < 0 else range(idx, idx + len(slice_text))


def map_owned_wrapped_line_to_range(text: str, cursor: int, wrapped: str, synthetic_prefix: str) -> range:
    body = wrapped[len(synthetic_prefix) :] if synthetic_prefix and wrapped.startswith(synthetic_prefix) else wrapped
    start = cursor
    if not body.startswith(" "):
        while start < len(text) and text[start] == " ":
            start += 1
    end = start
    saw_source = False
    for i, ch in enumerate(body):
        if end < len(text) and text[end] == ch:
            end += 1
            saw_source = True
            continue
        if ch == "-" and i == len(body) - 1:
            continue
        if saw_source:
            break
    return range(start, end)


def mixed_url_wrap_ranges(text: str, opts: RtOptions) -> List[range]:
    return wrap_ranges_trim(text, opts)


def split_mixed_url_word(word: str, width: int) -> List[str]:
    if is_url_like_token(word):
        return [word]
    return _split_by_width(word, width)


@dataclass
class MixedUrlWord:
    text: str

    def width(self) -> int:
        return _display_width(self.text)


class LineInput:
    def __init__(self, value: Any) -> None:
        self.value = _line_from_any(value)

    def as_ref(self) -> Line:
        return self.value


class IntoLineInput:
    pass


def into_line_input(value: Any) -> LineInput:
    return LineInput(value)


def slice_line_spans(line: Line, start: int, end: int) -> Line:
    text_pos = 0
    spans: list[Span] = []
    for span in line.spans:
        span_text = span.content
        span_end = text_pos + len(span_text)
        if span_end > start and text_pos < end:
            local_start = max(0, start - text_pos)
            local_end = min(len(span_text), end - text_pos)
            if local_start < local_end:
                spans.append(Span(span_text[local_start:local_end], span.style))
        text_pos = span_end
    return Line(spans, style=line.style, alignment=line.alignment)


def _wrap_line(line: Line, opts: RtOptions, preserve_urls: bool = False, split_non_url: bool = False) -> List[Line]:
    text = concat_line(line)
    if text == "":
        return [Line([], style=line.style, alignment=line.alignment)]

    pieces = _wrap_text(text, opts, preserve_urls=preserve_urls, split_non_url=split_non_url)
    result: List[Line] = []
    cursor = 0
    for rendered, body in pieces:
        body_start = text.find(body, cursor) if body else cursor
        if body_start < 0:
            body_start = cursor
        body_end = body_start + len(body)
        body_line = slice_line_spans(line, body_start, body_end)
        spans = []
        indent = rendered[: max(0, len(rendered) - len(body))]
        if indent:
            spans.append(Span(indent))
        spans.extend(body_line.spans)
        result.append(Line(spans, style=line.style, alignment=line.alignment))
        cursor = body_end
    return result or [Line([], style=line.style, alignment=line.alignment)]


def _wrap_text(text: str, opts: RtOptions, preserve_urls: bool, split_non_url: bool = False) -> List[Tuple[str, str]]:
    lines: List[Tuple[str, str]] = []
    remaining = text
    first = True
    while remaining != "":
        indent = concat_line(opts.initial_indent_line if first else opts.subsequent_indent_line)
        width = max(1, opts.width_value - _display_width(indent))
        body, rest = _take_line(remaining, width, opts, preserve_urls, split_non_url, keep_leading=first)
        lines.append((indent + body, body))
        remaining = rest
        first = False
    return lines


def _take_line(
    text: str,
    width: int,
    opts: RtOptions,
    preserve_urls: bool,
    split_non_url: bool,
    keep_leading: bool,
) -> Tuple[str, str]:
    if _display_width(text) <= width:
        return text, ""
    if not keep_leading:
        text = text.lstrip(" ")
    if preserve_urls:
        first_token = text.split(" ", 1)[0]
        if is_url_like_token(first_token):
            return first_token, text[len(first_token) :].lstrip(" ")
    if not opts.break_words_value and " " not in text.strip():
        return text, ""

    limit_index = _char_index_for_width(text, width)
    break_at = text.rfind(" ", 0, limit_index + 1)
    if break_at > 0:
        return text[:break_at].rstrip(" "), text[break_at:].lstrip(" ")

    hyphen_at = -1 if opts.no_hyphenation or preserve_urls else text.rfind("-", 0, limit_index + 1)
    if hyphen_at > 0:
        return text[: hyphen_at + 1], text[hyphen_at + 1 :].lstrip(" ")

    if opts.break_words_value or split_non_url:
        cut = max(1, limit_index)
        return text[:cut], text[cut:].lstrip(" ")
    return text, ""


def _char_index_for_width(text: str, width: int) -> int:
    used = 0
    for idx, ch in enumerate(text):
        ch_width = _display_width(ch)
        if used + ch_width > width:
            return idx
        used += ch_width
    return len(text)


def _split_by_width(text: str, width: int) -> List[str]:
    parts = []
    rest = text
    while rest:
        cut = max(1, _char_index_for_width(rest, width))
        parts.append(rest[:cut])
        rest = rest[cut:]
    return parts


def _wrap_text_ranges(text: str, opts: RtOptions, trim: bool) -> List[Tuple[int, int]]:
    lines = _wrap_text(text, opts, preserve_urls=opts.preserve_urls)
    ranges = []
    cursor = 0
    for _rendered, body in lines:
        start = text.find(body, cursor) if body else cursor
        if start < 0:
            start = cursor
        end = start + len(body)
        if not trim:
            while end < len(text) and text[end] == " ":
                end += 1
        ranges.append((start, end))
        cursor = end
    return ranges


def _line_from_any(value: Any) -> Line:
    if isinstance(value, Line):
        return Line([Span(span.content, span.style) for span in value.spans], style=value.style, alignment=value.alignment)
    if isinstance(value, Span):
        return Line([Span(value.content, value.style)])
    if isinstance(value, str):
        return Line([Span(value)]) if value else Line([])
    if isinstance(value, Sequence):
        spans = [item if isinstance(item, Span) else Span(str(item)) for item in value]
        return Line(spans)
    return Line([Span(str(value))])


__all__ = [name for name in globals() if not name.startswith("_")]
