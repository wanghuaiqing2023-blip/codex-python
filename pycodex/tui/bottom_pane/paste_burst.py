"""Paste-burst detection for terminals without bracketed paste.

Port of Rust ``codex-tui::bottom_pane::paste_burst``.  Time values are
represented as seconds-like numeric values or datetime/timedelta-compatible
objects; tests can pass simple floats.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="bottom_pane::paste_burst",
    source="codex/codex-rs/tui/src/bottom_pane/paste_burst.rs",
)

PASTE_BURST_MIN_CHARS = 3
PASTE_ENTER_SUPPRESS_WINDOW = 0.120
PASTE_BURST_CHAR_INTERVAL = 0.008
PASTE_BURST_ACTIVE_IDLE_TIMEOUT = 0.060 if sys.platform == "win32" else 0.008


@dataclass(frozen=True)
class CharDecision:
    """Semantic equivalent of Rust ``CharDecision``."""

    kind: str
    retro_chars: int | None = None

    @classmethod
    def begin_buffer(cls, retro_chars: int) -> "CharDecision":
        return cls("BeginBuffer", retro_chars)

    BUFFER_APPEND: "CharDecision"
    RETAIN_FIRST_CHAR: "CharDecision"
    BEGIN_BUFFER_FROM_PENDING: "CharDecision"


CharDecision.BUFFER_APPEND = CharDecision("BufferAppend")
CharDecision.RETAIN_FIRST_CHAR = CharDecision("RetainFirstChar")
CharDecision.BEGIN_BUFFER_FROM_PENDING = CharDecision("BeginBufferFromPending")


@dataclass(frozen=True)
class RetroGrab:
    start_byte: int
    grabbed: str


class FlushResultKind(Enum):
    PASTE = "Paste"
    TYPED = "Typed"
    NONE = "None"


@dataclass(frozen=True)
class FlushResult:
    kind: FlushResultKind
    value: str | None = None

    @classmethod
    def paste(cls, text: str) -> "FlushResult":
        return cls(FlushResultKind.PASTE, text)

    @classmethod
    def typed(cls, char: str) -> "FlushResult":
        return cls(FlushResultKind.TYPED, char)

    @classmethod
    def none(cls) -> "FlushResult":
        return cls(FlushResultKind.NONE, None)


@dataclass
class PasteBurst:
    last_plain_char_time: Any | None = None
    consecutive_plain_char_burst: int = 0
    burst_window_until: Any | None = None
    buffer: str = ""
    active: bool = False
    pending_first_char: tuple[str, Any] | None = None

    @staticmethod
    def recommended_flush_delay() -> float:
        return PASTE_BURST_CHAR_INTERVAL + 0.001

    @staticmethod
    def recommended_active_flush_delay() -> float:
        return PASTE_BURST_ACTIVE_IDLE_TIMEOUT + 0.001

    def on_plain_char(self, ch: str, now: Any) -> CharDecision:
        self.note_plain_char(now)

        if self.active:
            self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)
            return CharDecision.BUFFER_APPEND

        if self.pending_first_char is not None:
            held, held_at = self.pending_first_char
            if _duration_since(now, held_at) <= PASTE_BURST_CHAR_INTERVAL:
                self.active = True
                self.pending_first_char = None
                self.buffer += held
                self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)
                return CharDecision.BEGIN_BUFFER_FROM_PENDING

        if self.consecutive_plain_char_burst >= PASTE_BURST_MIN_CHARS:
            return CharDecision.begin_buffer(max(self.consecutive_plain_char_burst - 1, 0))

        self.pending_first_char = (ch, now)
        return CharDecision.RETAIN_FIRST_CHAR

    def on_plain_char_no_hold(self, now: Any) -> CharDecision | None:
        self.note_plain_char(now)

        if self.active:
            self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)
            return CharDecision.BUFFER_APPEND

        if self.consecutive_plain_char_burst >= PASTE_BURST_MIN_CHARS:
            return CharDecision.begin_buffer(max(self.consecutive_plain_char_burst - 1, 0))

        return None

    def note_plain_char(self, now: Any) -> None:
        if self.last_plain_char_time is not None and _duration_since(now, self.last_plain_char_time) <= PASTE_BURST_CHAR_INTERVAL:
            self.consecutive_plain_char_burst = min(self.consecutive_plain_char_burst + 1, 2**16 - 1)
        else:
            self.consecutive_plain_char_burst = 1
        self.last_plain_char_time = now

    def flush_if_due(self, now: Any) -> FlushResult:
        timeout = PASTE_BURST_ACTIVE_IDLE_TIMEOUT if self.is_active_internal() else PASTE_BURST_CHAR_INTERVAL
        timed_out = self.last_plain_char_time is not None and _duration_since(now, self.last_plain_char_time) > timeout
        if timed_out and self.is_active_internal():
            self.active = False
            out = self.buffer
            self.buffer = ""
            return FlushResult.paste(out)
        if timed_out and self.pending_first_char is not None:
            ch, _ = self.pending_first_char
            self.pending_first_char = None
            return FlushResult.typed(ch)
        return FlushResult.none()

    def append_newline_if_active(self, now: Any) -> bool:
        if self.is_active():
            self.buffer += "\n"
            self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)
            return True
        return False

    def newline_should_insert_instead_of_submit(self, now: Any) -> bool:
        in_burst_window = self.burst_window_until is not None and _compare_time(now, self.burst_window_until) <= 0
        return self.is_active() or in_burst_window

    def extend_window(self, now: Any) -> None:
        self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)

    def begin_with_retro_grabbed(self, grabbed: str, now: Any) -> None:
        if grabbed:
            self.buffer += grabbed
        self.active = True
        self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)

    def append_char_to_buffer(self, ch: str, now: Any) -> None:
        self.buffer += ch
        self.burst_window_until = _add_duration(now, PASTE_ENTER_SUPPRESS_WINDOW)

    def try_append_char_if_active(self, ch: str, now: Any) -> bool:
        if self.active or bool(self.buffer):
            self.append_char_to_buffer(ch, now)
            return True
        return False

    def decide_begin_buffer(self, now: Any, before: str, retro_chars: int) -> RetroGrab | None:
        start_byte = retro_start_index(before, retro_chars)
        grabbed = _slice_from_utf8_byte(before, start_byte)
        looks_pastey = any(ch.isspace() for ch in grabbed) or len(grabbed) >= 16
        if looks_pastey:
            self.begin_with_retro_grabbed(grabbed, now)
            return RetroGrab(start_byte=start_byte, grabbed=grabbed)
        return None

    def flush_before_modified_input(self) -> str | None:
        if not self.is_active():
            return None
        self.active = False
        out = self.buffer
        self.buffer = ""
        if self.pending_first_char is not None:
            ch, _ = self.pending_first_char
            self.pending_first_char = None
            out += ch
        return out

    def clear_window_after_non_char(self) -> None:
        self.consecutive_plain_char_burst = 0
        self.last_plain_char_time = None
        self.burst_window_until = None
        self.active = False
        self.pending_first_char = None

    def is_active(self) -> bool:
        return self.is_active_internal() or self.pending_first_char is not None

    def is_active_internal(self) -> bool:
        return self.active or bool(self.buffer)

    def clear_after_explicit_paste(self) -> None:
        self.last_plain_char_time = None
        self.consecutive_plain_char_burst = 0
        self.burst_window_until = None
        self.active = False
        self.buffer = ""
        self.pending_first_char = None


def retro_start_index(before: str, retro_chars: int) -> int:
    """Return the UTF-8 byte index where the last ``retro_chars`` chars start."""

    if retro_chars == 0:
        return len(before.encode("utf-8"))
    chars = list(before)
    start_char = max(len(chars) - retro_chars, 0)
    return len("".join(chars[:start_char]).encode("utf-8"))


def _slice_from_utf8_byte(text: str, start_byte: int) -> str:
    return text.encode("utf-8")[start_byte:].decode("utf-8")


def _duration_since(now: Any, previous: Any) -> float:
    delta = now - previous
    return delta.total_seconds() if hasattr(delta, "total_seconds") else float(delta)


def _add_duration(now: Any, seconds: float) -> Any:
    try:
        return now + seconds
    except TypeError:
        from datetime import timedelta

        return now + timedelta(seconds=seconds)


def _compare_time(left: Any, right: Any) -> int:
    return -1 if left < right else 1 if left > right else 0


__all__ = [
    "CharDecision",
    "FlushResult",
    "FlushResultKind",
    "PASTE_BURST_ACTIVE_IDLE_TIMEOUT",
    "PASTE_BURST_CHAR_INTERVAL",
    "PASTE_BURST_MIN_CHARS",
    "PASTE_ENTER_SUPPRESS_WINDOW",
    "PasteBurst",
    "RUST_MODULE",
    "RetroGrab",
    "retro_start_index",
]
