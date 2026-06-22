"""Minimal SSE helpers for the Rust ``codex-client`` port.

Rust source:
- ``codex/codex-rs/codex-client/src/sse.rs``
"""

from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Iterator
from dataclasses import dataclass

from .error import StreamError
from .error import TransportError


@dataclass(frozen=True)
class SseResult:
    data: str | None = None
    error: StreamError | None = None

    @classmethod
    def ok(cls, data: str) -> "SseResult":
        return cls(data=data)

    @classmethod
    def err(cls, error: StreamError) -> "SseResult":
        return cls(error=error)

    @property
    def is_ok(self) -> bool:
        return self.error is None


class IdleTimeout:
    """Sentinel for tests/adapters to mirror Rust's idle timeout branch."""


def sse_stream(
    stream: Iterable[bytes | str | TransportError | BaseException | IdleTimeout],
    idle_timeout: float | None = None,
) -> Iterator[SseResult]:
    """Forward raw SSE ``data:`` frames as UTF-8 strings.

    Rust spawns a Tokio task and sends ``Result<String, StreamError>`` values
    over an mpsc channel. Python exposes the same result sequence as a
    synchronous iterator so the parsing/error contract stays dependency-light.
    """

    del idle_timeout
    parser = _SseParser()
    saw_event = False

    for item in stream:
        if isinstance(item, IdleTimeout):
            yield SseResult.err(StreamError.timeout())
            return
        if isinstance(item, TransportError):
            yield SseResult.err(StreamError.stream(str(item)))
            return
        if isinstance(item, BaseException):
            yield SseResult.err(StreamError.stream(str(item)))
            return

        chunk = item.encode() if isinstance(item, str) else bytes(item)
        try:
            for data in parser.feed(chunk):
                saw_event = True
                yield SseResult.ok(data)
        except UnicodeDecodeError as exc:
            yield SseResult.err(StreamError.stream(str(exc)))
            return

    try:
        for data in parser.finish():
            saw_event = True
            yield SseResult.ok(data)
    except UnicodeDecodeError as exc:
        yield SseResult.err(StreamError.stream(str(exc)))
        return

    yield SseResult.err(StreamError.stream("stream closed before completion"))


class _SseParser:
    def __init__(self) -> None:
        self._buffer = b""
        self._data_lines: list[str] = []

    def feed(self, chunk: bytes) -> Iterator[str]:
        self._buffer += chunk
        while True:
            line, sep, rest = self._next_line(self._buffer)
            if sep is None:
                return
            self._buffer = rest
            yielded = self._handle_line(line.decode("utf-8"))
            if yielded is not None:
                yield yielded

    def finish(self) -> Iterator[str]:
        if self._buffer:
            yielded = self._handle_line(self._buffer.decode("utf-8"))
            self._buffer = b""
            if yielded is not None:
                yield yielded

    @staticmethod
    def _next_line(buffer: bytes) -> tuple[bytes, bytes | None, bytes]:
        positions = [
            pos for pos in (buffer.find(b"\n"), buffer.find(b"\r")) if pos != -1
        ]
        if not positions:
            return buffer, None, b""
        pos = min(positions)
        if buffer[pos : pos + 2] == b"\r\n":
            return buffer[:pos], b"\r\n", buffer[pos + 2 :]
        return buffer[:pos], buffer[pos : pos + 1], buffer[pos + 1 :]

    def _handle_line(self, line: str) -> str | None:
        if line == "":
            if not self._data_lines:
                return None
            data = "\n".join(self._data_lines)
            self._data_lines = []
            return data
        if line.startswith(":"):
            return None
        field, value = _split_field(line)
        if field == "data":
            self._data_lines.append(value)
        return None


def _split_field(line: str) -> tuple[str, str]:
    if ":" not in line:
        return line, ""
    field, value = line.split(":", 1)
    if value.startswith(" "):
        value = value[1:]
    return field, value
