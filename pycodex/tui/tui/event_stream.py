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
import queue
import threading
import time
from typing import Any, Callable, Deque, Iterable, List, Optional, Protocol, TextIO, Tuple

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


@dataclass(frozen=True)
class TerminalInputEvent:
    """Small Rust-shaped terminal event for the terminal product path."""

    kind: str
    text: str = ""


@dataclass(frozen=True)
class TerminalTurnEventPoll:
    """One app-server turn event poll result for the terminal product path."""

    kind: str
    event: Any = None


class TerminalInputSource:
    def poll(self, timeout: float) -> TerminalInputEvent | None:
        raise NotImplementedError


class StringTerminalInputSource(TerminalInputSource):
    """Deterministic char event source for fake TTY tests."""

    def __init__(self, stdin: TextIO) -> None:
        self.stdin = stdin

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        char = self.stdin.read(1)
        if char == "":
            return TerminalInputEvent("eof")
        return terminal_event_from_char(char)


class LineTerminalInputSource(TerminalInputSource):
    """Degraded cooked-line fallback for hosts without key-event support.

    Rust receives key and resize events from crossterm in one event stream.
    The normal Python Windows TTY path mirrors that with
    ``WindowsConsoleInputSource``. This adapter is retained only for
    compatibility when a key-event source cannot be initialized.
    """

    def __init__(self, stdin: TextIO) -> None:
        self.stdin = stdin
        self._queue: queue.Queue[TerminalInputEvent] = queue.Queue()
        self._thread = threading.Thread(target=self._read_lines, daemon=True)
        self._thread.start()

    def _read_lines(self) -> None:
        while True:
            line = self.stdin.readline()
            if line == "":
                self._queue.put(TerminalInputEvent("eof"))
                return
            self._queue.put(TerminalInputEvent("line", line))

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        try:
            return self._queue.get(timeout=max(0.0, timeout))
        except queue.Empty:
            return None


class WindowsConsoleInputSource(TerminalInputSource):
    """Windows terminal input adapter backed by the Rust-like console source."""

    def __init__(
        self,
        msvcrt_module: Any | None = None,
        *,
        console_handle: int | None = None,
        console_record_reader: Callable[[], Any | None] | None = None,
        event_source: Any | None = None,
    ) -> None:
        if msvcrt_module is None:
            import msvcrt

            msvcrt_module = msvcrt
        self._source = event_source or WindowsConsoleEventSource(
            msvcrt_module,
            console_handle=console_handle,
            console_record_reader=console_record_reader,
        )

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            event = self._source.poll_next()
            mapped = terminal_input_event_from_event_result(event)
            if mapped is not None:
                return mapped
            if time.monotonic() >= deadline:
                return None
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))


class SelectTerminalInputSource(TerminalInputSource):
    """Best-effort non-Windows TTY adapter, used only outside Windows."""

    def __init__(self, stdin: TextIO) -> None:
        self.stdin = stdin

    def poll(self, timeout: float) -> TerminalInputEvent | None:
        import select

        ready, _, _ = select.select([self.stdin], [], [], timeout)
        if not ready:
            return None
        char = self.stdin.read(1)
        if char == "":
            return TerminalInputEvent("eof")
        return terminal_event_from_char(char)


def make_terminal_input_source(stdin: TextIO) -> TerminalInputSource | None:
    """Create the terminal product-path input source for ``stdin``.

    Rust ``tui::event_stream`` owns the runtime boundary that turns terminal
    input into app events.  The Python scrollback product path keeps the same
    boundary by centralizing StringIO tests, Windows console key input, and
    best-effort select-based TTY polling here instead of in the runner.
    """

    if isinstance(stdin, str):
        return None
    if hasattr(stdin, "getvalue"):
        return StringTerminalInputSource(stdin)
    if os.name == "nt":
        try:
            return WindowsConsoleInputSource(console_handle=_windows_console_handle_from_stdin(stdin))
        except Exception:
            return LineTerminalInputSource(stdin)
    try:
        stdin.fileno()
    except Exception:
        return None
    return SelectTerminalInputSource(stdin)


def _windows_console_handle_from_stdin(stdin: TextIO) -> int | None:
    try:
        import msvcrt

        return int(msvcrt.get_osfhandle(stdin.fileno()))
    except Exception:
        return None


def get_or_make_terminal_input_source(
    existing: TerminalInputSource | None,
    stdin: TextIO,
) -> TerminalInputSource | None:
    """Return the active terminal input source, creating it when absent.

    Rust ``EventBrokerState::active_event_source_mut`` owns the reuse/create
    boundary for the shared crossterm input source.  The terminal runner stores
    the current source slot, but this module owns the policy for reusing it.
    """

    if existing is not None:
        return existing
    return make_terminal_input_source(stdin)


@dataclass
class TerminalInputSourceProvider:
    """Lazy terminal input-source cache for the terminal product path.

    Rust ``EventBrokerState`` owns the active event-source slot.  Python's
    scrollback runner only needs a small provider object so the create/reuse
    policy stays inside ``tui::event_stream``.
    """

    stdin: TextIO
    source: TerminalInputSource | None = None

    def get(self) -> TerminalInputSource | None:
        self.source = get_or_make_terminal_input_source(self.source, self.stdin)
        return self.source


def poll_terminal_turn_event(event_stream: Any, *, timeout: float) -> TerminalTurnEventPoll:
    """Poll a turn event stream and classify event/idle/closed states.

    Rust ``tui::event_stream`` owns the event-source boundary.  The Python
    terminal product path receives an app-runtime stream with a small set of
    compatibility shapes, so this helper keeps those stream-state checks out
    of the terminal runner.
    """

    event = event_stream.next_event(timeout=timeout)
    if event is not None:
        return TerminalTurnEventPoll("event", event)
    if terminal_turn_event_stream_closed(event_stream):
        return TerminalTurnEventPoll("closed")
    return TerminalTurnEventPoll("idle")


def terminal_turn_event_stream_closed(event_stream: Any) -> bool:
    """Return whether a terminal turn event stream has finished."""

    closed = getattr(event_stream, "closed", None)
    if callable(closed):
        try:
            return bool(closed())
        except Exception:
            return False
    if closed is not None:
        return bool(closed)
    return bool(getattr(event_stream, "is_closed", False))


def run_terminal_turn_event_loop(
    event_stream: Any,
    *,
    timeout: float,
    on_event: Callable[[Any], Any],
    on_closed: Callable[[], Any],
    on_idle: Callable[[], Any],
    before_event: Callable[[], Any],
) -> Any | None:
    """Consume one submitted turn stream through terminal event callbacks."""

    while True:
        polled = poll_terminal_turn_event(event_stream, timeout=timeout)
        if polled.kind != "event":
            if polled.kind == "closed":
                on_closed()
                return None
            on_idle()
            continue
        event = polled.event
        before_event()
        on_event(event)
        if str(getattr(event, "kind", "")) == "TurnCompleted":
            return event


def run_terminal_turn_idle_tick(
    *,
    check_resize: Callable[[], Any],
    refresh_turn_status: Callable[[], Any],
) -> None:
    """Run terminal idle-time maintenance for a submitted turn stream.

    Rust ``tui::event_stream`` owns idle/event/closed dispatch.  The Python
    terminal product path keeps the app-specific side effects as callbacks, but
    the event-stream boundary owns that resize handling happens before status
    refresh on idle polls.
    """

    check_resize()
    refresh_turn_status()


def terminal_event_from_char(char: str) -> TerminalInputEvent:
    if char in {"\r", "\n"}:
        return TerminalInputEvent("enter")
    if char == "\t":
        return TerminalInputEvent("tab")
    if char == "\x1b":
        return TerminalInputEvent("escape")
    if char in {"\b", "\x7f"}:
        return TerminalInputEvent("backspace")
    if char == "\x03":
        return TerminalInputEvent("interrupt")
    if char == "\x1a":
        return TerminalInputEvent("eof")
    return TerminalInputEvent("text", char)


def terminal_input_event_from_key_payload(payload: Any) -> TerminalInputEvent | None:
    text = str(payload)
    normalized = _terminal_key_payload_name(text)
    if normalized in {"up", "down", "left", "right", "home", "end", "page_up", "page_down", "delete"}:
        return TerminalInputEvent(normalized)
    ansi = _ansi_escape_key(text)
    if ansi is not None:
        return TerminalInputEvent(ansi)
    if text == "enter":
        return TerminalInputEvent("enter")
    if text == "tab":
        return TerminalInputEvent("tab")
    if text == "escape":
        return TerminalInputEvent("escape")
    if len(text) == 1:
        return terminal_event_from_char(text)
    return None


def terminal_input_event_from_event_result(event: Any) -> TerminalInputEvent | None:
    if event is None:
        return None
    if isinstance(event, TerminalInputEvent):
        return event
    if isinstance(event, TuiEvent):
        if event.kind is TuiEventKind.KEY:
            return terminal_input_event_from_key_payload(event.payload)
        if event.kind is TuiEventKind.RESIZE:
            return TerminalInputEvent("resize")
        if event.kind is TuiEventKind.PASTE:
            return TerminalInputEvent("text", str(event.payload))
        return None
    if isinstance(event, tuple) and event:
        kind = event[0]
        payload = event[1] if len(event) > 1 else None
        if kind == "key":
            return terminal_input_event_from_key_payload(payload)
        if kind == "resize":
            return TerminalInputEvent("resize")
        if kind == "paste":
            return TerminalInputEvent("text", str(payload or ""))
    return None


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
    Textual product path uses Textual for terminal ownership, but keeping the
    Windows console adapter behind an ``EventSource`` preserves the same
    module boundary for tests and host-terminal helpers: raw terminal input
    becomes crossterm-shaped key events before the app/composer layer consumes
    it.
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
                if ch in ("[", "O"):
                    ansi_event = self._poll_ansi_escape_key(ch)
                    if ansi_event is not None:
                        _trace_input_event("windows_console.return", {"event": _describe_event(ansi_event)})
                        return ansi_event
                    _trace_input_event("windows_console.return", {"event": _describe_event(("key", "\x1b"))})
                    return ("key", "\x1b")
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

    def _poll_ansi_escape_key(self, introducer: str) -> Optional[EventResult]:
        sequence = "\x1b" + introducer
        while self.msvcrt_module.kbhit():
            ch = self.msvcrt_module.getwch()
            _trace_input_event("windows_console.getwch_ansi", {"ch": _describe_key(ch)})
            sequence += ch
            mapped = _ansi_escape_key(sequence)
            if mapped is not None:
                return ("key", mapped)
            if ch.isalpha() or ch == "~":
                break
        for ch in sequence[2:]:
            self._pending_events.append(("key", ch))
        return None


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
    if char and str(char) != "\x00":
        return ("key", str(char))
    mapped = _windows_console_virtual_key(int(virtual_key)) if virtual_key is not None else None
    if mapped is None:
        return None
    return ("key", mapped)


def _terminal_key_payload_name(payload: str) -> str:
    text = payload.strip().lower().replace("-", "_")
    aliases = {
        "arrowup": "up",
        "arrow_up": "up",
        "up_arrow": "up",
        "arrowdown": "down",
        "arrow_down": "down",
        "down_arrow": "down",
        "arrowleft": "left",
        "arrow_left": "left",
        "left_arrow": "left",
        "arrowright": "right",
        "arrow_right": "right",
        "right_arrow": "right",
        "pgup": "page_up",
        "pageup": "page_up",
        "page_up": "page_up",
        "pgdn": "page_down",
        "pagedown": "page_down",
        "page_down": "page_down",
        "del": "delete",
        "delete": "delete",
    }
    return aliases.get(text, text)


def _ansi_escape_key(payload: str) -> str | None:
    if not payload.startswith("\x1b"):
        return None
    return {
        "\x1b[A": "up",
        "\x1b[B": "down",
        "\x1b[C": "right",
        "\x1b[D": "left",
        "\x1b[H": "home",
        "\x1b[F": "end",
        "\x1bOA": "up",
        "\x1bOB": "down",
        "\x1bOC": "right",
        "\x1bOD": "left",
        "\x1bOH": "home",
        "\x1bOF": "end",
        "\x1b[1~": "home",
        "\x1b[3~": "delete",
        "\x1b[4~": "end",
        "\x1b[5~": "page_up",
        "\x1b[6~": "page_down",
        "\x1b[7~": "home",
        "\x1b[8~": "end",
    }.get(payload)


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
    "LineTerminalInputSource",
    "SelectTerminalInputSource",
    "StringTerminalInputSource",
    "TerminalInputEvent",
    "TerminalInputSource",
    "TerminalInputSourceProvider",
    "TerminalTurnEventPoll",
    "TuiEvent",
    "TuiEventKind",
    "TuiEventStream",
    "WindowsConsoleEventSource",
    "WindowsConsoleInputSource",
    "default",
    "draw_and_key_events_yield_both",
    "error_or_eof_ends_stream",
    "get_or_make_terminal_input_source",
    "key_event_skips_unmapped",
    "lagged_draw_maps_to_draw",
    "make_terminal_input_source",
    "make_stream",
    "poll_next",
    "poll_terminal_turn_event",
    "resize_event_maps_to_resize",
    "resume_wakes_paused_stream",
    "resume_wakes_pending_stream",
    "run_terminal_turn_idle_tick",
    "run_terminal_turn_event_loop",
    "setup",
    "terminal_event_from_char",
    "terminal_input_event_from_event_result",
    "terminal_input_event_from_key_payload",
    "terminal_turn_event_stream_closed",
]

