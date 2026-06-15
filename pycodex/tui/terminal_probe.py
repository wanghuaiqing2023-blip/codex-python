"""Short terminal response probe parsers for ``codex-tui::terminal_probe``.

Rust source: ``codex/codex-rs/tui/src/terminal_probe.rs``.

The byte parsers and startup-probe state machine are ported directly.  The
Unix-specific nonblocking TTY duplication/polling path is intentionally not
fabricated in Python; callers can inject a TTY-like object into ``read_until``
and ``read_startup_probe`` for deterministic behavior, while ``Tty.open`` makes
the missing platform boundary explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from typing import Any, Callable, Iterable, List, Optional, Tuple

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="terminal_probe",
    source="codex/codex-rs/tui/src/terminal_probe.rs",
    status="complete",
)

DEFAULT_TIMEOUT = timedelta(milliseconds=100)


@dataclass(frozen=True)
class Position:
    x: int
    y: int


@dataclass(frozen=True)
class DefaultColors:
    fg: Tuple[int, int, int]
    bg: Tuple[int, int, int]


@dataclass
class StartupProbe:
    cursor_position: Optional[Position] = None
    default_colors: Optional[DefaultColors] = None
    keyboard_enhancement_supported: Optional[bool] = None


class StartupKeyboardEnhancementProbe(Enum):
    Query = "query"
    Skip = "skip"


class KeyboardProbeState(Enum):
    Pending = "pending"
    UnsupportedFallback = "unsupported_fallback"
    Supported = "supported"
    SupportedAndFallback = "supported_and_fallback"


class Tty:
    """Platform TTY boundary from Rust; not silently simulated in Python."""

    @classmethod
    def open(cls) -> "Tty":
        if _tty_factory is not None:
            return _tty_factory()
        raise NotImplementedError(
            "terminal_probe.Tty.open requires a real nonblocking terminal handle implementation"
        )

    def write_all(self, data: bytes) -> None:
        raise NotImplementedError("terminal_probe.Tty.write_all is platform-specific")

    def read_available(self, buffer: bytearray) -> None:
        raise NotImplementedError("terminal_probe.Tty.read_available is platform-specific")

    def poll_readable(self, timeout: timedelta) -> bool:
        raise NotImplementedError("terminal_probe.Tty.poll_readable is platform-specific")


def dup_file(fd: int) -> Any:
    raise NotImplementedError("terminal_probe.dup_file is a Unix file-descriptor operation")


_tty_factory: Optional[Callable[[], Tty]] = None


def set_tty_factory(factory: Optional[Callable[[], Tty]]) -> None:
    """Install a runtime TTY factory for terminal probe adapters.

    Rust owns the concrete duplicated-stdio/nonblocking-tty path. Python keeps
    that side effect explicit: parsers and state transitions are implemented
    here, while real terminal I/O must be supplied by a runtime adapter.
    """

    global _tty_factory
    _tty_factory = factory


def drop(value: Any) -> None:
    return None


def default_colors(timeout: timedelta = DEFAULT_TIMEOUT) -> Optional[DefaultColors]:
    tty = Tty.open()
    tty.write_all(b"\x1B]10;?\x1B\\\x1B]11;?\x1B\\")
    return read_until(tty, timeout, parse_default_colors)


def startup(
    timeout: timedelta = DEFAULT_TIMEOUT,
    keyboard_probe: StartupKeyboardEnhancementProbe = StartupKeyboardEnhancementProbe.Query,
) -> StartupProbe:
    tty = Tty.open()
    if keyboard_probe is StartupKeyboardEnhancementProbe.Query:
        tty.write_all(b"\x1B[6n\x1B]10;?\x1B\\\x1B]11;?\x1B\\\x1B[?u\x1B[c")
    else:
        tty.write_all(b"\x1B[6n\x1B]10;?\x1B\\\x1B]11;?\x1B\\")
    return read_startup_probe(tty, timeout, keyboard_probe)


def read_until(tty: Any, timeout: timedelta, parse: Callable[[bytes], Optional[Any]]) -> Optional[Any]:
    buffer = bytearray()
    while True:
        tty.read_available(buffer)
        value = parse(bytes(buffer))
        if value is not None:
            return value
        if not tty.poll_readable(timeout):
            return None


def read_startup_probe(
    tty: Any,
    timeout: timedelta,
    keyboard_probe: StartupKeyboardEnhancementProbe,
) -> StartupProbe:
    buffer = bytearray()
    probe = StartupProbe()
    saw_supported_keyboard = False
    while True:
        tty.read_available(buffer)
        saw_supported_keyboard = update_startup_probe(
            probe, saw_supported_keyboard, bytes(buffer), keyboard_probe
        )
        if startup_probe_complete(probe, keyboard_probe):
            return probe
        if not tty.poll_readable(timeout):
            finish_startup_probe(probe, keyboard_probe, saw_supported_keyboard)
            return probe


def update_startup_probe(
    probe: StartupProbe,
    saw_supported_keyboard: bool,
    buffer: bytes,
    keyboard_probe: StartupKeyboardEnhancementProbe,
) -> bool:
    if probe.cursor_position is None:
        probe.cursor_position = parse_cursor_position(buffer)
    if probe.default_colors is None:
        probe.default_colors = parse_default_colors(buffer)
    if keyboard_probe is StartupKeyboardEnhancementProbe.Skip or probe.keyboard_enhancement_supported is not None:
        return saw_supported_keyboard

    state = parse_keyboard_enhancement_support(buffer)
    if state is KeyboardProbeState.SupportedAndFallback:
        probe.keyboard_enhancement_supported = True
    elif state is KeyboardProbeState.Supported:
        saw_supported_keyboard = True
    elif state is KeyboardProbeState.UnsupportedFallback:
        probe.keyboard_enhancement_supported = False
    return saw_supported_keyboard


def startup_probe_complete(
    probe: StartupProbe,
    keyboard_probe: StartupKeyboardEnhancementProbe,
) -> bool:
    return (
        probe.cursor_position is not None
        and probe.default_colors is not None
        and (
            keyboard_probe is StartupKeyboardEnhancementProbe.Skip
            or probe.keyboard_enhancement_supported is not None
        )
    )


def finish_startup_probe(
    probe: StartupProbe,
    keyboard_probe: StartupKeyboardEnhancementProbe,
    saw_supported_keyboard: bool,
) -> None:
    if (
        keyboard_probe is StartupKeyboardEnhancementProbe.Query
        and probe.keyboard_enhancement_supported is None
    ):
        probe.keyboard_enhancement_supported = True if saw_supported_keyboard else None


def parse_cursor_position(buffer: bytes) -> Optional[Position]:
    for start in find_all_subslices(buffer, b"\x1B["):
        rest = buffer[start + 2 :]
        try:
            end = rest.index(ord("R"))
        except ValueError:
            continue
        try:
            payload = rest[:end].decode("utf-8")
        except UnicodeDecodeError:
            continue
        if ";" not in payload:
            continue
        row_text, col_text = payload.split(";", 1)
        try:
            row = int(row_text)
            col = int(col_text)
        except ValueError:
            continue
        return Position(x=max(0, col - 1), y=max(0, row - 1))
    return None


def parse_osc_color(buffer: bytes, slot: int) -> Optional[Tuple[int, int, int]]:
    prefix = f"\x1B]{slot};".encode()
    start = find_subslice(buffer, prefix)
    if start is None:
        return None
    payload_start = start + len(prefix)
    rest = buffer[payload_start:]
    end = osc_payload_end(rest)
    if end is None:
        return None
    payload_end, _terminator_len = end
    try:
        payload = rest[:payload_end].decode("utf-8")
    except UnicodeDecodeError:
        return None
    return parse_osc_rgb(payload)


def parse_default_colors(buffer: bytes) -> Optional[DefaultColors]:
    fg = parse_osc_color(buffer, 10)
    bg = parse_osc_color(buffer, 11)
    if fg is None or bg is None:
        return None
    return DefaultColors(fg=fg, bg=bg)


def osc_payload_end(buffer: bytes) -> Optional[Tuple[int, int]]:
    idx = 0
    while idx < len(buffer):
        byte = buffer[idx]
        if byte == 0x07:
            return idx, 1
        if byte == 0x1B and idx + 1 < len(buffer) and buffer[idx + 1] == ord("\\"):
            return idx, 2
        idx += 1
    return None


def parse_osc_rgb(payload: str) -> Optional[Tuple[int, int, int]]:
    stripped = payload.strip()
    if ":" not in stripped:
        return None
    prefix, values = stripped.split(":", 1)
    lowered = prefix.lower()
    if lowered not in ("rgb", "rgba"):
        return None
    parts = values.split("/")
    expected = 4 if lowered == "rgba" else 3
    if len(parts) != expected:
        return None
    components: List[Optional[int]] = [parse_osc_component(part) for part in parts]
    if any(component is None for component in components):
        return None
    return int(components[0]), int(components[1]), int(components[2])


def parse_osc_component(component: str) -> Optional[int]:
    try:
        if len(component) == 2:
            return int(component, 16)
        if len(component) == 4:
            return int(component, 16) // 257
    except ValueError:
        return None
    return None


def parse_keyboard_enhancement_support(buffer: bytes) -> KeyboardProbeState:
    has_flags = find_keyboard_flags(buffer) is not None
    has_pda = find_primary_device_attributes(buffer) is not None
    if has_flags and has_pda:
        return KeyboardProbeState.SupportedAndFallback
    if has_flags:
        return KeyboardProbeState.Supported
    if has_pda:
        return KeyboardProbeState.UnsupportedFallback
    return KeyboardProbeState.Pending


def find_keyboard_flags(buffer: bytes) -> Optional[int]:
    for start in find_all_subslices(buffer, b"\x1B[?"):
        rest = buffer[start + 3 :]
        try:
            end = rest.index(ord("u"))
        except ValueError:
            continue
        if end == 0:
            continue
        try:
            bits = int(rest[:end].decode("utf-8"))
        except (UnicodeDecodeError, ValueError):
            continue
        return bits & 0x0F
    return None


def find_primary_device_attributes(buffer: bytes) -> Optional[bool]:
    for start in find_all_subslices(buffer, b"\x1B[?"):
        rest = buffer[start + 3 :]
        try:
            end = rest.index(ord("c"))
        except ValueError:
            continue
        if end > 0 and all(chr(byte).isdigit() or byte == ord(";") for byte in rest[:end]):
            return True
    return None


def find_subslice(haystack: bytes, needle: bytes) -> Optional[int]:
    if needle == b"":
        return 0
    idx = haystack.find(needle)
    return idx if idx >= 0 else None


def find_all_subslices(haystack: bytes, needle: bytes) -> Iterable[int]:
    if needle == b"":
        return iter(())
    return (idx for idx in range(0, len(haystack) - len(needle) + 1) if haystack[idx : idx + len(needle)] == needle)


__all__ = [
    "DEFAULT_TIMEOUT",
    "DefaultColors",
    "KeyboardProbeState",
    "Position",
    "RUST_MODULE",
    "StartupKeyboardEnhancementProbe",
    "StartupProbe",
    "Tty",
    "default_colors",
    "drop",
    "dup_file",
    "find_all_subslices",
    "find_keyboard_flags",
    "find_primary_device_attributes",
    "find_subslice",
    "finish_startup_probe",
    "osc_payload_end",
    "parse_cursor_position",
    "parse_default_colors",
    "parse_keyboard_enhancement_support",
    "parse_osc_color",
    "parse_osc_component",
    "parse_osc_rgb",
    "read_startup_probe",
    "read_until",
    "set_tty_factory",
    "startup",
    "startup_probe_complete",
    "update_startup_probe",
]
