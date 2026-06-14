"""Portable backend/test-backend subset for ratatui bridge.

This module intentionally models backend state, not terminal side effects. Real
terminal integration should stay in the Python TUI runtime/Textual boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional, Protocol, TypeVar

from .buffer import Buffer
from .layout import Rect, Size

T = TypeVar("T")


@dataclass(frozen=True)
class WindowSize:
    columns_rows: Size
    pixels: Optional[Size] = None


class Backend(Protocol):
    def size(self) -> Size:
        ...

    def window_size(self) -> WindowSize:
        ...

    def buffer(self) -> Buffer:
        ...

    def flush(self) -> None:
        ...


class TestBackend:
    """Cell-buffer backend equivalent for parity tests and semantic rendering."""

    def __init__(self, width: int, height: int) -> None:
        self._size = Size.new(width, height)
        self._buffer = Buffer.empty(Rect.new(0, 0, self._size.width, self._size.height))
        self.flush_count = 0

    @classmethod
    def new(cls, width: int, height: int) -> "TestBackend":
        return cls(width, height)

    def size(self) -> Size:
        return self._size

    def window_size(self) -> WindowSize:
        return WindowSize(self._size)

    def buffer(self) -> Buffer:
        return self._buffer

    def resize(self, width: int, height: int) -> None:
        self._size = Size.new(width, height)
        self._buffer = Buffer.empty(Rect.new(0, 0, self._size.width, self._size.height))

    def flush(self) -> None:
        self.flush_count += 1


class CrosstermBackend:
    """Compatibility placeholder for Rust type boundaries.

    Python should not perform crossterm side effects through this class. It is
    intentionally non-rendering and raises for buffer access.
    """

    def __init__(self, stream: object = None) -> None:
        self.stream = stream

    def size(self) -> Size:
        raise NotImplementedError("CrosstermBackend size is runtime-specific in Python")

    def window_size(self) -> WindowSize:
        raise NotImplementedError("CrosstermBackend window_size is runtime-specific in Python")

    def buffer(self) -> Buffer:
        raise NotImplementedError("CrosstermBackend does not expose a semantic buffer")

    def flush(self) -> None:
        raise NotImplementedError("CrosstermBackend flush is runtime-specific in Python")


@dataclass
class Frame:
    area: Rect
    buffer: Buffer

    def size(self) -> Rect:
        return self.area

    def render_widget(self, widget: object, area: Rect) -> None:
        render = getattr(widget, "render", None)
        if render is None:
            raise TypeError("widget must provide render(area, buffer)")
        render(area, self.buffer)

    def render_widget_ref(self, widget: object, area: Rect) -> None:
        render_ref = getattr(widget, "render_ref", None)
        if render_ref is None:
            self.render_widget(widget, area)
            return
        render_ref(area, self.buffer)


class Terminal:
    """Small semantic wrapper around a bridge backend."""

    def __init__(self, backend: Backend) -> None:
        self.backend = backend

    @classmethod
    def new(cls, backend: Backend) -> "Terminal":
        return cls(backend)

    def size(self) -> Size:
        return self.backend.size()

    def window_size(self) -> WindowSize:
        return self.backend.window_size()

    def draw(self, callback: Callable[[Frame], T]) -> T:
        size = self.backend.size()
        frame = Frame(Rect.new(0, 0, size.width, size.height), self.backend.buffer())
        result = callback(frame)
        self.backend.flush()
        return result

    def backend_mut(self) -> Backend:
        return self.backend

    def backend_ref(self) -> Backend:
        return self.backend


__all__ = [
    "Backend",
    "CrosstermBackend",
    "Frame",
    "Terminal",
    "TestBackend",
    "WindowSize",
]
