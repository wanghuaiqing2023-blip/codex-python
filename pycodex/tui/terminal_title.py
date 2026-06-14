"""Terminal title sanitization and OSC encoding for ``codex-tui``.

Rust source: ``codex/codex-rs/tui/src/terminal_title.rs``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import sys
from typing import TextIO

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="terminal_title",
    source="codex/codex-rs/tui/src/terminal_title.rs",
)

MAX_TERMINAL_TITLE_CHARS = 240


class SetTerminalTitleResult(Enum):
    Applied = "applied"
    NoVisibleContent = "no_visible_content"


@dataclass(frozen=True)
class SetWindowTitle:
    title: str

    def write_ansi(self) -> str:
        return f"\x1b]0;{self.title}\x07"

    def execute_winapi(self) -> None:
        raise OSError("tried to execute SetWindowTitle using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True


def set_terminal_title(title: str, stdout: TextIO | None = None) -> SetTerminalTitleResult:
    """Write a sanitized OSC title when stdout is a terminal."""
    stream = sys.stdout if stdout is None else stdout
    if not _is_terminal(stream):
        return SetTerminalTitleResult.Applied

    sanitized = sanitize_terminal_title(title)
    if sanitized == "":
        return SetTerminalTitleResult.NoVisibleContent

    stream.write(SetWindowTitle(sanitized).write_ansi())
    if hasattr(stream, "flush"):
        stream.flush()
    return SetTerminalTitleResult.Applied


def clear_terminal_title(stdout: TextIO | None = None) -> None:
    """Clear the title Codex manages by writing an empty OSC title payload."""
    stream = sys.stdout if stdout is None else stdout
    if not _is_terminal(stream):
        return
    stream.write(SetWindowTitle("").write_ansi())
    if hasattr(stream, "flush"):
        stream.flush()


def write_ansi(command: SetWindowTitle) -> str:
    return command.write_ansi()


def execute_winapi(command: SetWindowTitle) -> None:
    command.execute_winapi()


def is_ansi_code_supported(command: SetWindowTitle) -> bool:
    return command.is_ansi_code_supported()


def sanitize_terminal_title(title: str) -> str:
    """Normalize untrusted title text into one bounded display line."""
    sanitized: list[str] = []
    chars_written = 0
    pending_space = False

    for ch in title:
        if ch.isspace():
            pending_space = bool(sanitized)
            continue

        if is_disallowed_terminal_title_char(ch):
            continue

        if pending_space:
            remaining = MAX_TERMINAL_TITLE_CHARS - chars_written
            if remaining > 1:
                sanitized.append(" ")
                chars_written += 1
                pending_space = False

        if chars_written >= MAX_TERMINAL_TITLE_CHARS:
            break

        sanitized.append(ch)
        chars_written += 1

    return "".join(sanitized)


def is_disallowed_terminal_title_char(ch: str) -> bool:
    """Return whether ``ch`` should be dropped from terminal title output."""
    if len(ch) != 1:
        raise ValueError("expected a single character")
    code = ord(ch)
    if 0x0000 <= code <= 0x001F or 0x007F <= code <= 0x009F:
        return True
    return (
        code == 0x00AD
        or code == 0x034F
        or code == 0x061C
        or code == 0x180E
        or 0x200B <= code <= 0x200F
        or 0x202A <= code <= 0x202E
        or 0x2060 <= code <= 0x206F
        or 0xFE00 <= code <= 0xFE0F
        or code == 0xFEFF
        or 0xFFF9 <= code <= 0xFFFB
        or 0x1BCA0 <= code <= 0x1BCA3
        or 0xE0100 <= code <= 0xE01EF
    )


def _is_terminal(stream: TextIO) -> bool:
    isatty = getattr(stream, "isatty", None)
    return bool(isatty and isatty())


__all__ = [
    "MAX_TERMINAL_TITLE_CHARS",
    "RUST_MODULE",
    "SetTerminalTitleResult",
    "SetWindowTitle",
    "clear_terminal_title",
    "execute_winapi",
    "is_ansi_code_supported",
    "is_disallowed_terminal_title_char",
    "sanitize_terminal_title",
    "set_terminal_title",
    "write_ansi",
]
