"""Textual-backed event source for Rust-style ``tui::event_stream``.

This module is the internal adapter layer: application code may feed Textual
runtime events into ``TextualEventSource``, while the rest of the TUI continues
to consume Rust-like ``EventBroker`` / ``TuiEventStream`` APIs.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Deque, Optional, Tuple

from .event_stream import DrawChannel
from .event_stream import EventBroker
from .event_stream import EventResult
from .event_stream import EventSource
from .event_stream import FocusFlag
from .event_stream import TuiEventStream


@dataclass
class TextualEventSource(EventSource):
    """Queue-backed ``EventSource`` that normalizes Textual events.

    Textual owns the real terminal event loop.  The app/event handlers can call
    ``send_textual_event`` with a Textual event object; this source converts it
    into the crossterm-like tuple shape consumed by ``TuiEventStream``.
    """

    events: Deque[EventResult] = field(default_factory=deque)

    def poll_next(self) -> Optional[EventResult]:
        if not self.events:
            return None
        return self.events.popleft()

    def send_textual_event(self, event: Any) -> None:
        normalized = textual_event_to_crossterm_like(event)
        if normalized is not None:
            self.events.append(normalized)

    def send_error(self, error: BaseException) -> None:
        self.events.append(error)


@dataclass
class TextualEventRuntime:
    """Convenience holder for a Textual-backed Rust-style event stream."""

    source: TextualEventSource
    broker: EventBroker
    draw_channel: DrawChannel
    terminal_focused: FocusFlag
    stream: TuiEventStream

    def send_textual_event(self, event: Any) -> None:
        if self.broker.state.value == "paused":
            return
        self.source.send_textual_event(event)

    def request_draw(self) -> None:
        self.draw_channel.send()

    def pause_events(self) -> None:
        self.broker.pause_events()

    def resume_events(self) -> None:
        self.broker.resume_events()


@dataclass
class TextualEventBridge:
    runtime: TextualEventRuntime

    @classmethod
    def new(cls) -> "TextualEventBridge":
        return cls(make_textual_event_runtime())

    @property
    def stream(self) -> TuiEventStream:
        return self.runtime.stream

    def on_key(self, event: Any) -> None:
        self.runtime.send_textual_event(event)

    def on_resize(self, event: Any) -> None:
        self.runtime.send_textual_event(event)

    def on_paste(self, event: Any) -> None:
        self.runtime.send_textual_event(event)

    def on_focus(self) -> None:
        self.runtime.terminal_focused.set(True)
        self.runtime.send_textual_event({"kind": "focus"})

    def on_blur(self) -> None:
        self.runtime.terminal_focused.set(False)
        setattr(self.runtime.terminal_focused, "_suppress_next_focus_gained", True)
        self.runtime.send_textual_event({"kind": "blur"})

    def pause_events(self) -> None:
        self.runtime.pause_events()

    def resume_events(self) -> None:
        self.runtime.resume_events()


def make_textual_event_runtime(
    source: Optional[TextualEventSource] = None,
    draw_channel: Optional[DrawChannel] = None,
    terminal_focused: Optional[FocusFlag] = None,
) -> TextualEventRuntime:
    event_source = source or TextualEventSource()
    broker = EventBroker.new(lambda: event_source)
    draw = draw_channel or DrawChannel()
    focused = terminal_focused or FocusFlag(True)
    stream = TuiEventStream.new(broker, draw, focused)
    return TextualEventRuntime(event_source, broker, draw, focused, stream)


def textual_event_to_crossterm_like(event: Any) -> Optional[Tuple[str, Any]]:
    """Convert a Textual event object into event_stream's crossterm-like shape."""

    if isinstance(event, tuple) and event:
        return event  # already normalized
    if isinstance(event, dict):
        kind = str(event.get("kind") or event.get("type") or event.get("event") or "").lower()
        return _normalize_kind_payload(kind, event)

    cls_name = event.__class__.__name__.lower()
    kind = str(getattr(event, "kind", getattr(event, "type", cls_name))).lower()
    return _normalize_kind_payload(kind or cls_name, event)


def _normalize_kind_payload(kind: str, event: Any) -> Optional[Tuple[str, Any]]:
    compact = kind.replace("_", "").replace("-", "")
    if compact in {"key", "keyevent"}:
        return ("key", _first_attr(event, "key", "character", "char", "name", "payload"))
    if compact in {"resize", "resizeevent"}:
        return ("resize", _resize_payload(event))
    if compact in {"paste", "pasteevent"}:
        return ("paste", _first_attr(event, "text", "payload", "value"))
    if compact in {"focus", "focusgained", "focusevent"}:
        return ("focus_gained", None)
    if compact in {"blur", "focuslost", "blurevent"}:
        return ("focus_lost", None)
    if compact in {"mouse", "mousemove", "mousedown", "mouseup"}:
        return None
    return None


def _first_attr(event: Any, *names: str) -> Any:
    if isinstance(event, dict):
        for name in names:
            if name in event:
                return event[name]
        return None
    for name in names:
        if hasattr(event, name):
            return getattr(event, name)
    return None


def _resize_payload(event: Any) -> Any:
    size = _first_attr(event, "size")
    if size is not None:
        width = getattr(size, "width", None)
        height = getattr(size, "height", None)
        if width is not None and height is not None:
            return (width, height)
        return size
    width = _first_attr(event, "width", "columns")
    height = _first_attr(event, "height", "rows")
    if width is not None or height is not None:
        return (width, height)
    return _first_attr(event, "payload")


__all__ = [
    "TextualEventBridge",
    "TextualEventRuntime",
    "TextualEventSource",
    "make_textual_event_runtime",
    "textual_event_to_crossterm_like",
]

