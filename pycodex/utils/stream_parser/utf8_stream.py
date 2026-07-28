"""UTF-8 stream adapter from Rust ``utf8_stream.rs``."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Generic, TypeVar

from .stream_text import StreamTextChunk, StreamTextParser

class Utf8StreamParserErrorKind(Enum):
    INVALID_UTF8 = "invalid_utf8"
    INCOMPLETE_UTF8_AT_EOF = "incomplete_utf8_at_eof"


@dataclass(frozen=True)
class Utf8StreamParserError(Exception):
    kind: Utf8StreamParserErrorKind
    valid_up_to: int | None = None
    error_len: int | None = None

    @classmethod
    def invalid_utf8(cls, valid_up_to: int, error_len: int) -> "Utf8StreamParserError":
        return cls(Utf8StreamParserErrorKind.INVALID_UTF8, valid_up_to, error_len)

    @classmethod
    def incomplete_utf8_at_eof(cls) -> "Utf8StreamParserError":
        return cls(Utf8StreamParserErrorKind.INCOMPLETE_UTF8_AT_EOF)

    def __str__(self) -> str:
        if self.kind is Utf8StreamParserErrorKind.INVALID_UTF8:
            return (
                "invalid UTF-8 in streamed bytes at offset "
                f"{self.valid_up_to} (error length {self.error_len})"
            )
        return "incomplete UTF-8 code point at end of stream"


P = TypeVar("P", bound=StreamTextParser[object])


class Utf8StreamParser(Generic[P]):
    def __init__(self, inner: P) -> None:
        self._inner = inner
        self._pending_utf8 = bytearray()

    def push_bytes(self, chunk: bytes | bytearray | memoryview) -> StreamTextChunk[object]:
        chunk_bytes = bytes(chunk)
        old_len = len(self._pending_utf8)
        self._pending_utf8.extend(chunk_bytes)

        try:
            text = self._pending_utf8.decode("utf-8")
        except UnicodeDecodeError as err:
            if err.reason != "unexpected end of data":
                self._pending_utf8 = self._pending_utf8[:old_len]
                raise Utf8StreamParserError.invalid_utf8(err.start, max(err.end - err.start, 0)) from None

            valid_up_to = err.start
            if valid_up_to == 0:
                return StreamTextChunk()

            try:
                text = bytes(self._pending_utf8[:valid_up_to]).decode("utf-8")
            except UnicodeDecodeError as prefix_err:
                self._pending_utf8 = self._pending_utf8[:old_len]
                raise Utf8StreamParserError.invalid_utf8(
                    prefix_err.start,
                    max(prefix_err.end - prefix_err.start, 0),
                ) from None

            out = self._inner.push_str(text)
            del self._pending_utf8[:valid_up_to]
            return out

        out = self._inner.push_str(text)
        self._pending_utf8.clear()
        return out

    def finish(self) -> StreamTextChunk[object]:
        if self._pending_utf8:
            try:
                text = self._pending_utf8.decode("utf-8")
            except UnicodeDecodeError as err:
                if err.reason != "unexpected end of data":
                    raise Utf8StreamParserError.invalid_utf8(err.start, max(err.end - err.start, 0)) from None
                raise Utf8StreamParserError.incomplete_utf8_at_eof() from None

            out = self._inner.push_str(text)
            self._pending_utf8.clear()
        else:
            out = StreamTextChunk()

        tail = self._inner.finish()
        out.visible_text += tail.visible_text
        out.extracted.extend(tail.extracted)
        return out

    def into_inner(self) -> P:
        if not self._pending_utf8:
            return self._inner
        try:
            self._pending_utf8.decode("utf-8")
        except UnicodeDecodeError as err:
            if err.reason != "unexpected end of data":
                raise Utf8StreamParserError.invalid_utf8(err.start, max(err.end - err.start, 0)) from None
            raise Utf8StreamParserError.incomplete_utf8_at_eof() from None
        return self._inner

    def into_inner_lossy(self) -> P:
        return self._inner

