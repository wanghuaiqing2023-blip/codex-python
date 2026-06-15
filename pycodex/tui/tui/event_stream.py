"""Semantic event-stream port for Rust ``codex-tui::tui::event_stream``.

Rust source: ``codex/codex-rs/tui/src/tui/event_stream.rs``.

The real Rust module owns crossterm/tokio stream plumbing.  Python keeps that
terminal I/O as an explicit runtime boundary and ports the module-local event
broker semantics with deterministic in-memory sources: pause/resume lifecycle,
draw-event fan-out, crossterm-event mapping, skipped unmapped events, and stream
termination on source errors/EOF.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Deque, Iterable, List, Optional, Protocol, Tuple

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="tui::event_stream",
    source="codex/codex-rs/tui/src/tui/event_stream.rs",
    status="complete",
)

EventResult = Any
Item = Any


class TuiEventKind(str, Enum):
    DRAW = "draw"
    KEY = "key"
    RESIZE = "resize"
    PASTE = "paste"


@dataclass(frozen=True)
class TuiEvent:
    kind: TuiEventKind
    payload: Any = None

    @classmethod
    def draw(cls) -> "TuiEvent":
        return cls(TuiEventKind.DRAW)

    @classmethod
    def key(cls, key: Any) -> "TuiEvent":
        return cls(TuiEventKind.KEY, key)

    @classmethod
    def resize(cls) -> "TuiEvent":
        return cls(TuiEventKind.RESIZE)

    @classmethod
    def paste(cls, text: str) -> "TuiEvent":
        return cls(TuiEventKind.PASTE, text)


class EventSource(Protocol):
    """Python protocol boundary for Rust ``EventSource``."""

    def poll_next(self) -> Optional[EventResult]:
        ...


class EventBrokerState(str, Enum):
    PAUSED = "paused"
    START = "start"
    RUNNING = "running"


@dataclass
class EventBroker:
    """Shared input source lifecycle, mirroring Rust ``EventBroker``.

    ``pause_events`` drops the active source.  ``resume_events`` marks the source
    for recreation on the next poll/send and wakes paused streams through a
    monotonically increasing ``resume_generation`` value.
    """

    source_factory: Callable[[], EventSource]
    state: EventBrokerState = EventBrokerState.START
    source: Optional[EventSource] = None
    resume_generation: int = 0

    @classmethod
    def new(cls, source_factory: Optional[Callable[[], EventSource]] = None) -> "EventBroker":
        return cls(source_factory or CrosstermEventSource)

    def active_event_source(self) -> Optional[EventSource]:
        if self.state is EventBrokerState.PAUSED:
            return None
        if self.state is EventBrokerState.START:
            self.source = self.source_factory()
            self.state = EventBrokerState.RUNNING
        return self.source

    def pause_events(self) -> None:
        self.source = None
        self.state = EventBrokerState.PAUSED

    def resume_events(self) -> None:
        self.source = None
        self.state = EventBrokerState.START
        self.resume_generation += 1

    def resume_events_rx(self) -> int:
        return self.resume_generation


@dataclass
class CrosstermEventSource:
    """Runtime boundary for real crossterm input.

    Python does not read terminal stdin here.  Callers that need real terminal
    input should provide a Textual/runtime-backed source.
    """

    def poll_next(self) -> Optional[EventResult]:
        return None


def default() -> CrosstermEventSource:
    return CrosstermEventSource()


@dataclass
class DrawSignal:
    lagged: bool = False


@dataclass
class DrawChannel:
    events: Deque[DrawSignal] = field(default_factory=deque)

    def send(self, lagged: bool = False) -> None:
        self.events.append(DrawSignal(lagged=lagged))

    def poll_next(self) -> Optional[DrawSignal]:
        if not self.events:
            return None
        return self.events.popleft()


@dataclass
class FocusFlag:
    value: bool = True

    def set(self, value: bool) -> None:
        self.value = bool(value)


@dataclass
class TuiEventStream:
    broker: EventBroker
    draw_stream: DrawChannel = field(default_factory=DrawChannel)
    terminal_focused: FocusFlag = field(default_factory=FocusFlag)
    poll_draw_first: bool = False
    _last_resume_generation: int = 0
    ended: bool = False

    @classmethod
    def new(
        cls,
        broker: EventBroker,
        draw_rx: Optional[DrawChannel] = None,
        terminal_focused: Optional[FocusFlag] = None,
        *args: Any,
        **kwargs: Any,
    ) -> "TuiEventStream":
        return cls(broker, draw_rx or DrawChannel(), terminal_focused or FocusFlag())

    def poll_crossterm_event(self) -> Optional[TuiEvent]:
        while not self.ended:
            source = self.broker.active_event_source()
            if source is None:
                generation = self.broker.resume_events_rx()
                if generation != self._last_resume_generation:
                    self._last_resume_generation = generation
                    continue
                return None

            event_result = source.poll_next()
            if event_result is None:
                return None
            if isinstance(event_result, BaseException):
                self.broker.state = EventBrokerState.START
                self.broker.source = None
                self.ended = True
                return None

            mapped = self.map_crossterm_event(event_result)
            if mapped is not None:
                return mapped
        return None

    def poll_draw_event(self) -> Optional[TuiEvent]:
        signal = self.draw_stream.poll_next()
        if signal is None:
            return None
        return TuiEvent.draw()

    def map_crossterm_event(self, event: Any) -> Optional[TuiEvent]:
        kind, payload = _event_kind_and_payload(event)
        if kind == "key":
            return TuiEvent.key(payload)
        if kind == "resize":
            return TuiEvent.resize()
        if kind == "paste":
            return TuiEvent.paste(str(payload))
        if kind == "focus_gained":
            self.terminal_focused.set(True)
            return TuiEvent.draw()
        if kind == "focus_lost":
            self.terminal_focused.set(False)
            return None
        return None

    def poll_next(self) -> Optional[TuiEvent]:
        draw_first = self.poll_draw_first
        self.poll_draw_first = not self.poll_draw_first

        if draw_first:
            event = self.poll_draw_event()
            if event is not None:
                return event
            return self.poll_crossterm_event()

        event = self.poll_crossterm_event()
        if event is not None:
            return event
        return self.poll_draw_event()

    def __iter__(self) -> "TuiEventStream":
        return self

    def __next__(self) -> TuiEvent:
        event = self.poll_next()
        if event is None:
            raise StopIteration
        return event


@dataclass
class FakeEventSource:
    events: Deque[EventResult] = field(default_factory=deque)

    @classmethod
    def new(cls) -> "FakeEventSource":
        return cls()

    def send(self, event: EventResult) -> None:
        self.events.append(event)

    def poll_next(self) -> Optional[EventResult]:
        if not self.events:
            return None
        return self.events.popleft()


@dataclass
class FakeEventSourceHandle:
    broker: EventBroker

    @classmethod
    def new(cls, broker: EventBroker) -> "FakeEventSourceHandle":
        return cls(broker)

    def send(self, event: EventResult) -> None:
        source = self.broker.active_event_source()
        if isinstance(source, FakeEventSource):
            source.send(event)


def make_stream(
    broker: EventBroker,
    draw_rx: Optional[DrawChannel] = None,
    terminal_focused: Optional[FocusFlag] = None,
) -> TuiEventStream:
    return TuiEventStream.new(broker, draw_rx, terminal_focused)


SetupState = Tuple[EventBroker, FakeEventSourceHandle, DrawChannel, DrawChannel, FocusFlag]


def setup() -> SetupState:
    broker = EventBroker.new(FakeEventSource)
    broker.active_event_source()
    handle = FakeEventSourceHandle.new(broker)
    draw_channel = DrawChannel()
    terminal_focused = FocusFlag(True)
    return broker, handle, draw_channel, draw_channel, terminal_focused


def poll_next(stream: TuiEventStream) -> Optional[TuiEvent]:
    return stream.poll_next()


def _event_kind_and_payload(event: Any) -> Tuple[str, Any]:
    if isinstance(event, dict):
        kind = event.get("kind") or event.get("type") or event.get("event")
        payload = event.get("payload", event.get("key", event.get("text")))
        return str(kind).lower(), payload
    if isinstance(event, tuple) and event:
        kind = str(event[0]).lower()
        payload = event[1] if len(event) > 1 else None
        return kind, payload
    kind = getattr(event, "kind", getattr(event, "type", event))
    payload = getattr(event, "payload", getattr(event, "key", getattr(event, "text", None)))
    return str(kind).lower(), payload


async def key_event_skips_unmapped() -> None:
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    handle.send(("focus_lost", None))
    handle.send(("key", "a"))
    assert stream.poll_next() == TuiEvent.key("a")


async def draw_and_key_events_yield_both() -> None:
    broker, handle, draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    draw_tx.send()
    handle.send(("key", "a"))
    events = [stream.poll_next(), stream.poll_next()]
    assert TuiEvent.draw() in events
    assert TuiEvent.key("a") in events


async def lagged_draw_maps_to_draw() -> None:
    broker, _handle, draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    draw_tx.send(lagged=True)
    assert stream.poll_next() == TuiEvent.draw()


async def resize_event_maps_to_resize() -> None:
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    handle.send(("resize", (80, 24)))
    assert stream.poll_next() == TuiEvent.resize()


async def error_or_eof_ends_stream() -> None:
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    handle.send(OSError("boom"))
    assert stream.poll_next() is None
    assert stream.ended is True


async def resume_wakes_paused_stream() -> None:
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    broker.pause_events()
    assert stream.poll_next() is None
    broker.resume_events()
    handle.send(("key", "r"))
    assert stream.poll_next() == TuiEvent.key("r")


async def resume_wakes_pending_stream() -> None:
    broker, handle, _draw_tx, draw_rx, terminal_focused = setup()
    stream = make_stream(broker, draw_rx, terminal_focused)
    assert stream.poll_next() is None
    broker.pause_events()
    broker.resume_events()
    handle.send(("key", "p"))
    assert stream.poll_next() == TuiEvent.key("p")


__all__ = [
    "CrosstermEventSource",
    "DrawChannel",
    "DrawSignal",
    "EventBroker",
    "EventBrokerState",
    "EventResult",
    "EventSource",
    "FakeEventSource",
    "FakeEventSourceHandle",
    "FocusFlag",
    "Item",
    "RUST_MODULE",
    "SetupState",
    "TuiEvent",
    "TuiEventKind",
    "TuiEventStream",
    "default",
    "draw_and_key_events_yield_both",
    "error_or_eof_ends_stream",
    "key_event_skips_unmapped",
    "lagged_draw_maps_to_draw",
    "make_stream",
    "poll_next",
    "resize_event_maps_to_resize",
    "resume_wakes_paused_stream",
    "resume_wakes_pending_stream",
    "setup",
]

