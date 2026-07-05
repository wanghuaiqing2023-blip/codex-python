"""No-side-effect crossterm compatibility values for ratatui bridge.

The terminal runtime and custom-terminal backend own real terminal mode,
cursor, and screen I/O. These values only keep Rust-facing API boundaries
explicit for ports that mention ratatui/crossterm commands.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Tuple

from .style import Color


class ClearType(str, Enum):
    ALL = "all"
    All = "all"
    PURGE = "purge"
    Purge = "purge"
    FROM_CURSOR_DOWN = "from_cursor_down"
    FromCursorDown = "from_cursor_down"
    FROM_CURSOR_UP = "from_cursor_up"
    FromCursorUp = "from_cursor_up"
    CURRENT_LINE = "current_line"
    CurrentLine = "current_line"
    UNTIL_NEW_LINE = "until_new_line"
    UntilNewLine = "until_new_line"


class Attribute(str, Enum):
    RESET = "reset"
    Reset = "reset"
    NO_UNDERLINE = "no_underline"
    NoUnderline = "no_underline"


@dataclass(frozen=True)
class SetAttribute:
    attribute: Attribute


@dataclass(frozen=True)
class SetForegroundColor:
    color: Color


@dataclass(frozen=True)
class SetBackgroundColor:
    color: Color


def enable_raw_mode() -> None:
    raise NotImplementedError("raw mode is owned by the Python terminal runtime")


def disable_raw_mode() -> None:
    raise NotImplementedError("raw mode is owned by the Python terminal runtime")


def execute(*commands: object) -> Tuple[object, ...]:
    raise NotImplementedError("terminal command execution is owned by the Python terminal runtime")


__all__ = [
    "Attribute",
    "ClearType",
    "SetAttribute",
    "SetBackgroundColor",
    "SetForegroundColor",
    "disable_raw_mode",
    "enable_raw_mode",
    "execute",
]
