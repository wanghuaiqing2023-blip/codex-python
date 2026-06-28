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
import json
import os
from pathlib import Path
import time
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


@dataclass
class WindowsConsoleEventSource:
    """Windows console source for product-path key polling.

    Rust production uses ``crossterm::event::EventStream`` and maps
    ``Event::Key`` through ``TuiEventStream::map_crossterm_event``.  Python's
    lightweight terminal path cannot use crossterm, but keeping the Windows
    console polling behind an ``EventSource`` preserves the same event-stream
    boundary: raw terminal input becomes crossterm-shaped key events before the
    app/composer layer consumes it.
    """

    msvcrt_module: Any
    console_handle: int | None = None
    console_record_reader: Callable[[], Any | None] | None = None
    _pending_special_prefix: bool = False
    _pending_alt_prefix: bool = False
    _pending_events: Deque[EventResult] = field(default_factory=deque)

    def poll_next(self) -> Optional[EventResult]:
        while True:
            if self._pending_events:
                event = self._pending_events.popleft()
                _trace_input_event("windows_console.pending_event", {"event": _describe_event(event)})
                return event
            console_event = self._poll_console_input_event()
            if console_event is not None:
                _trace_input_event("windows_console.return", {"event": _describe_event(console_event), "source": "console_record"})
                return console_event
            if self._pending_alt_prefix:
                if not self.msvcrt_module.kbhit():
                    self._pending_alt_prefix = False
                    _trace_input_event("windows_console.alt_escape", {"event": _describe_event(("key", "\x1b"))})
                    return ("key", "\x1b")
                ch = self.msvcrt_module.getwch()
                _trace_input_event("windows_console.getwch_alt", {"ch": _describe_key(ch)})
                self._pending_alt_prefix = False
                if len(ch) == 1 and ch >= " ":
                    event = ("key", f"alt-{ch.lower()}")
                    _trace_input_event("windows_console.return", {"event": _describe_event(event)})
                    return event
                if ch in ("\x00", "\xe0"):
                    self._pending_special_prefix = True
                    _trace_input_event("windows_console.return", {"event": _describe_event(("key", "\x1b"))})
                    return ("key", "\x1b")
                self._pending_events.append(("key", ch))
                _trace_input_event("windows_console.return", {"event": _describe_event(("key", "\x1b"))})
                return ("key", "\x1b")
            if self._pending_special_prefix:
                if not self.msvcrt_module.kbhit():
                    return None
                ch = self.msvcrt_module.getwch()
                _trace_input_event("windows_console.getwch_special", {"ch": _describe_key(ch)})
                self._pending_special_prefix = False
                mapped = _windows_console_special_key(ch)
                if mapped is not None:
                    event = ("key", mapped)
                    _trace_input_event("windows_console.return", {"event": _describe_event(event)})
                    return event
                continue
            if self.msvcrt_module.kbhit():
                ch = self.msvcrt_module.getwch()
                _trace_input_event("windows_console.getwch", {"ch": _describe_key(ch)})
                if ch == "\x1b" and self.msvcrt_module.kbhit():
                    self._pending_alt_prefix = True
                    continue
                if ch in ("\x00", "\xe0"):
                    self._pending_special_prefix = True
                    continue
                event = ("key", ch)
                _trace_input_event("windows_console.return", {"event": _describe_event(event)})
                return event
            return None

    def _poll_console_input_event(self) -> Optional[EventResult]:
        reader = self.console_record_reader
        record = reader() if callable(reader) else _read_windows_console_input_record(self.console_handle)
        if record is None:
            return None
        event = _windows_console_record_to_event(record)
        _trace_input_event(
            "windows_console.input_record",
            {"record": _describe_console_record(record), "event": _describe_event(event) if event is not None else None},
        )
        return event


def _windows_console_special_key(ch: str) -> str | None:
    return {
        ";": "f1",
        "<": "f2",
        "=": "f3",
        ">": "f4",
        "?": "f5",
        "@": "f6",
        "A": "f7",
        "B": "f8",
        "C": "f9",
        "D": "f10",
        "\x85": "f11",
        "\x86": "f12",
        "G": "home",
        "H": "up",
        "I": "page_up",
        "K": "left",
        "M": "right",
        "O": "end",
        "P": "down",
        "Q": "page_down",
        "S": "delete",
    }.get(ch)


def _windows_console_record_to_event(record: Any) -> Optional[EventResult]:
    kind = _record_field(record, "kind")
    if kind not in (None, "key"):
        return None
    key_down = _record_field(record, "key_down", True)
    if not bool(key_down):
        return None
    char = _record_field(record, "char", "")
    virtual_key = _record_field(record, "virtual_key", None)
    if char:
        return ("key", str(char))
    mapped = _windows_console_virtual_key(int(virtual_key)) if virtual_key is not None else None
    if mapped is None:
        return None
    return ("key", mapped)


def _windows_console_virtual_key(code: int) -> str | None:
    return {
        0x08: "\b",
        0x09: "\t",
        0x0D: "\r",
        0x1B: "\x1b",
        0x21: "page_up",
        0x22: "page_down",
        0x23: "end",
        0x24: "home",
        0x25: "left",
        0x26: "up",
        0x27: "right",
        0x28: "down",
        0x2E: "delete",
    }.get(code)


def _record_field(record: Any, name: str, default: Any = None) -> Any:
    if isinstance(record, dict):
        return record.get(name, default)
    return getattr(record, name, default)


def _describe_console_record(record: Any) -> dict[str, Any]:
    return {
        "kind": _record_field(record, "kind"),
        "key_down": _record_field(record, "key_down"),
        "virtual_key": _record_field(record, "virtual_key"),
        "char": _describe_key(str(_record_field(record, "char", ""))),
    }


def _read_windows_console_input_record(handle: int | None) -> Any | None:
    if handle is None or os.name != "nt":
        return None
    try:
        import ctypes
        import ctypes.wintypes
    except ImportError:
        return None

    class _KeyEventRecord(ctypes.Structure):
        _fields_ = [
            ("bKeyDown", ctypes.wintypes.BOOL),
            ("wRepeatCount", ctypes.wintypes.WORD),
            ("wVirtualKeyCode", ctypes.wintypes.WORD),
            ("wVirtualScanCode", ctypes.wintypes.WORD),
            ("UnicodeChar", ctypes.c_wchar),
            ("dwControlKeyState", ctypes.wintypes.DWORD),
        ]

    class _EventUnion(ctypes.Union):
        _fields_ = [
            ("KeyEvent", _KeyEventRecord),
            ("padding", ctypes.c_byte * 16),
        ]

    class _InputRecord(ctypes.Structure):
        _fields_ = [
            ("EventType", ctypes.wintypes.WORD),
            ("Event", _EventUnion),
        ]

    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
    for _ in range(16):
        peek_record = _InputRecord()
        read_count = ctypes.wintypes.DWORD(0)
        ok = kernel32.PeekConsoleInputW(
            ctypes.c_void_p(handle),
            ctypes.byref(peek_record),
            ctypes.wintypes.DWORD(1),
            ctypes.byref(read_count),
        )
        if not ok or int(read_count.value) == 0:
            return None
        record = _InputRecord()
        read_count = ctypes.wintypes.DWORD(0)
        ok = kernel32.ReadConsoleInputW(
            ctypes.c_void_p(handle),
            ctypes.byref(record),
            ctypes.wintypes.DWORD(1),
            ctypes.byref(read_count),
        )
        if not ok or int(read_count.value) == 0:
            return None
        if int(record.EventType) != 0x0001:
            continue
        key = record.Event.KeyEvent
        return {
            "kind": "key",
            "key_down": bool(key.bKeyDown),
            "virtual_key": int(key.wVirtualKeyCode),
            "char": key.UnicodeChar or "",
            "repeat_count": int(key.wRepeatCount),
            "control_key_state": int(key.dwControlKeyState),
        }
    return None


def _trace_input_event(label: str, payload: dict[str, Any]) -> None:
    target = os.environ.get("PYCODEX_TUI_INPUT_TRACE")
    if not target:
        return
    path = Path(".tmp/tui-input-trace.jsonl") if target == "1" else Path(target)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), "label": label, **payload}
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        return


def _describe_event(event: EventResult) -> dict[str, Any]:
    try:
        kind, payload = _event_kind_and_payload(event)
    except Exception:
        return {"repr": repr(event)}
    return {"kind": kind, "payload": _describe_key(str(payload)) if kind == "key" else repr(payload)}


def _describe_key(ch: str) -> dict[str, Any]:
    return {
        "len": len(ch),
        "repr": repr(ch),
        "codepoints": [ord(part) for part in ch],
        "names": [_control_key_name(part) for part in ch],
    }


def _control_key_name(ch: str) -> str:
    return {
        "\r": "CR",
        "\n": "LF",
        "\t": "TAB",
        "\x00": "NUL",
        "\xe0": "EXTENDED",
        "\x1b": "ESC",
        "\x03": "CTRL_C",
        "\x14": "CTRL_T",
    }.get(ch, "printable" if ch >= " " else f"control_{ord(ch)}")


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
            if getattr(self.terminal_focused, "_suppress_next_focus_gained", False):
                setattr(self.terminal_focused, "_suppress_next_focus_gained", False)
            else:
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
    "WindowsConsoleEventSource",
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

