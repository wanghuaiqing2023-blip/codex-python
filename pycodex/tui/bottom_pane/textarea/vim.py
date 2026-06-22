"""Vim text-object semantics for Rust ``bottom_pane/textarea/vim.rs``.

This module keeps the Rust module boundary small: it ports the enum/state
shapes plus deterministic text-object range calculation. Full TextArea key event
routing remains in ``bottom_pane/textarea.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterable

from ..._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::textarea::vim",
    source="codex/codex-rs/tui/src/bottom_pane/textarea/vim.rs",
)

WORD_SEPARATORS = "`~!@#$%^&*()-=+[{]}\\|;:'\",.<>/?"


class VimMode(Enum):
    Normal = "normal"
    Insert = "insert"


class VimOperator(Enum):
    Delete = "delete"
    Yank = "yank"
    Change = "change"


@dataclass(frozen=True)
class VimPending:
    kind: str
    operator: VimOperator | None = None
    scope: "VimTextObjectScope | None" = None

    @classmethod
    def None_(cls) -> "VimPending":
        return cls("None")

    @classmethod
    def Operator(cls, operator: VimOperator) -> "VimPending":
        return cls("Operator", operator=operator)

    @classmethod
    def TextObject(cls, operator: VimOperator, scope: "VimTextObjectScope") -> "VimPending":
        return cls("TextObject", operator=operator, scope=scope)


class VimMotion(Enum):
    Left = "left"
    Right = "right"
    Up = "up"
    Down = "down"
    WordForward = "word_forward"
    WordBackward = "word_backward"
    WordEnd = "word_end"
    LineStart = "line_start"
    LineEnd = "line_end"


class VimTextObjectScope(Enum):
    Inner = "inner"
    Around = "around"


class VimTextObject(Enum):
    Word = "word"
    BigWord = "big_word"
    Parentheses = "parentheses"
    Brackets = "brackets"
    Braces = "braces"
    DoubleQuote = "double_quote"
    SingleQuote = "single_quote"
    Backtick = "backtick"


@dataclass(frozen=True)
class TextElement:
    range: range
    name: str | None = None


@dataclass
class TextAreaVim:
    text: str = ""
    cursor_pos: int = 0
    elements: list[TextElement] | None = None

    def __post_init__(self) -> None:
        self.cursor_pos = max(0, min(int(self.cursor_pos), len(self.text.encode("utf-8"))))
        if self.elements is None:
            self.elements = []

    def text_object_range(self, object_: VimTextObject, scope: VimTextObjectScope) -> range | None:
        object_ = VimTextObject(object_)
        scope = VimTextObjectScope(scope)
        if object_ is VimTextObject.Word:
            return self.word_text_object_range(scope, big_word=False)
        if object_ is VimTextObject.BigWord:
            return self.word_text_object_range(scope, big_word=True)
        if object_ is VimTextObject.Parentheses:
            return self.paired_text_object_range(scope, "(", ")")
        if object_ is VimTextObject.Brackets:
            return self.paired_text_object_range(scope, "[", "]")
        if object_ is VimTextObject.Braces:
            return self.paired_text_object_range(scope, "{", "}")
        if object_ is VimTextObject.DoubleQuote:
            return self.quoted_text_object_range(scope, '"')
        if object_ is VimTextObject.SingleQuote:
            return self.quoted_text_object_range(scope, "'")
        return self.quoted_text_object_range(scope, "`")

    def word_text_object_range(self, scope: VimTextObjectScope, big_word: bool = False) -> range | None:
        inner = self.big_word_range_at_cursor() if big_word else self.small_word_range_at_cursor()
        if inner is None:
            return None
        return inner if scope is VimTextObjectScope.Inner else self.expand_word_around(inner)

    def big_word_range_at_cursor(self) -> range | None:
        for run in self.non_ws_runs():
            if self.cursor_overlaps_range(run) or self.cursor_is_at_range_end(run):
                return run
        return None

    def small_word_range_at_cursor(self) -> range | None:
        for run in self.non_ws_runs():
            if not self.cursor_overlaps_range(run) and not self.cursor_is_at_range_end(run):
                continue
            last_piece: range | None = None
            run_text = slice_bytes(self.text, run)
            for piece_start, piece in split_word_pieces(run_text):
                piece_range = range(run.start + piece_start, run.start + piece_start + len(piece.encode("utf-8")))
                if self.cursor_overlaps_range(piece_range):
                    return piece_range
                last_piece = piece_range
            if self.cursor_is_at_range_end(run):
                return last_piece or run
            return run
        return None

    def non_ws_runs(self) -> list[range]:
        runs: list[range] = []
        start: int | None = None
        for idx, ch in char_indices(self.text):
            if ch.isspace():
                if start is not None:
                    runs.append(range(start, idx))
                    start = None
            elif start is None:
                start = idx
        if start is not None:
            runs.append(range(start, len(self.text.encode("utf-8"))))
        return runs

    def cursor_overlaps_range(self, range_: range) -> bool:
        return range_.start <= self.cursor_pos < range_.stop

    def cursor_is_at_range_end(self, range_: range) -> bool:
        return range_.start < range_.stop and self.cursor_pos == range_.stop

    def expand_word_around(self, inner: range) -> range:
        following = self.following_whitespace_end(inner.stop)
        if following > inner.stop:
            return range(inner.start, following)
        return range(self.preceding_whitespace_start(inner.start), inner.stop)

    def following_whitespace_end(self, start: int) -> int:
        end = start
        for idx, ch in char_indices_from_byte(self.text, start):
            if not ch.isspace():
                break
            end = idx + len(ch.encode("utf-8"))
        return end

    def preceding_whitespace_start(self, end: int) -> int:
        start = end
        for idx, ch in reversed(list(char_indices_before_byte(self.text, end))):
            if not ch.isspace():
                break
            start = idx
        return start

    def paired_text_object_range(self, scope: VimTextObjectScope, open_: str, close: str) -> range | None:
        stack: list[int] = []
        best: range | None = None
        for idx, ch in char_indices(self.text):
            if self.is_inside_element(idx):
                continue
            if ch == open_:
                stack.append(idx)
            elif ch == close and stack:
                open_idx = stack.pop()
                close_end = idx + len(ch.encode("utf-8"))
                if open_idx <= self.cursor_pos <= idx:
                    candidate = range(open_idx + len(open_.encode("utf-8")), idx) if scope is VimTextObjectScope.Inner else range(open_idx, close_end)
                    if candidate.start <= candidate.stop and (best is None or range_len(candidate) < range_len(best)):
                        best = candidate
        return best

    def quoted_text_object_range(self, scope: VimTextObjectScope, quote: str) -> range | None:
        line = range(self.beginning_of_current_line(), self.end_of_current_line())
        open_idx: int | None = None
        best: range | None = None
        for idx, ch in char_indices_from_byte(self.text, line.start):
            if idx >= line.stop:
                break
            if self.is_inside_element(idx) or ch != quote or self.is_escaped(idx):
                continue
            if open_idx is None:
                open_idx = idx
                continue
            if open_idx <= self.cursor_pos < idx:
                if scope is VimTextObjectScope.Inner:
                    candidate = range(open_idx + len(quote.encode("utf-8")) + 1, idx + 1)
                else:
                    candidate = range(open_idx + 1, idx + len(quote.encode("utf-8")) + 1)
                if candidate.start <= candidate.stop and (best is None or range_len(candidate) < range_len(best)):
                    best = candidate
            open_idx = None
        return best

    def beginning_of_current_line(self) -> int:
        start = 0
        for idx, ch in char_indices_before_byte(self.text, self.cursor_pos):
            if ch == "\n":
                start = idx + 1
        return start

    def end_of_current_line(self) -> int:
        for idx, ch in char_indices_from_byte(self.text, self.cursor_pos):
            if ch == "\n":
                return idx
        return len(self.text.encode("utf-8"))

    def is_inside_element(self, pos: int) -> bool:
        return any(element.range.start <= pos < element.range.stop for element in self.elements or [])

    def is_escaped(self, pos: int) -> bool:
        backslashes = 0
        prefix = slice_bytes(self.text, range(0, pos))
        for ch in reversed(prefix):
            if ch != "\\":
                break
            backslashes += 1
        return backslashes % 2 == 1


def idx_range(open_idx: int, close_idx: int, quote: str) -> range:
    return range(int(open_idx), int(close_idx) + len(str(quote).encode("utf-8")))


def text_object_range(text_area: TextAreaVim, object_: VimTextObject, scope: VimTextObjectScope) -> range | None:
    return text_area.text_object_range(object_, scope)


def split_word_pieces(run: str) -> list[tuple[int, str]]:
    pieces: list[tuple[int, str]] = []
    piece_start = 0
    current_is_sep: bool | None = None
    for idx, ch in char_indices(run):
        is_sep = ch in WORD_SEPARATORS
        if current_is_sep is None:
            current_is_sep = is_sep
            continue
        if is_sep == current_is_sep:
            continue
        pieces.append((piece_start, slice_bytes(run, range(piece_start, idx))))
        piece_start = idx
        current_is_sep = is_sep
    if current_is_sep is not None:
        pieces.append((piece_start, slice_bytes(run, range(piece_start, len(run.encode("utf-8"))))))
    return pieces


def char_indices(text: str) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    offset = 0
    for ch in text:
        out.append((offset, ch))
        offset += len(ch.encode("utf-8"))
    return out


def char_indices_from_byte(text: str, start: int) -> list[tuple[int, str]]:
    return [(idx, ch) for idx, ch in char_indices(text) if idx >= start]


def char_indices_before_byte(text: str, end: int) -> list[tuple[int, str]]:
    return [(idx, ch) for idx, ch in char_indices(text) if idx < end]


def slice_bytes(text: str, byte_range: range) -> str:
    data = text.encode("utf-8")[byte_range.start : byte_range.stop]
    return data.decode("utf-8")


def range_len(value: range) -> int:
    return max(value.stop - value.start, 0)


__all__ = [
    "RUST_MODULE",
    "TextAreaVim",
    "TextElement",
    "VimMode",
    "VimMotion",
    "VimOperator",
    "VimPending",
    "VimTextObject",
    "VimTextObjectScope",
    "idx_range",
    "split_word_pieces",
    "text_object_range",
]
