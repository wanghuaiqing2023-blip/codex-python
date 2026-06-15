"""Behavior port for Rust ``codex-tui::notifications::bel``."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Any, Optional, TextIO

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(crate="codex-tui", module="notifications::bel", source="codex/codex-rs/tui/src/notifications/bel.rs", status="complete")

BEL = "\x07"


@dataclass
class BelBackend:
    """Notification backend that emits the terminal BEL character."""

    stream: Optional[TextIO] = None

    def notify(self, _message: str) -> None:
        stream = self.stream if self.stream is not None else sys.stdout
        PostNotification().write_ansi(stream)
        flush = getattr(stream, "flush", None)
        if callable(flush):
            flush()


@dataclass(frozen=True)
class PostNotification:
    """Command that emits a BEL desktop notification."""

    def write_ansi(self, f: Any) -> None:
        f.write(BEL)

    def execute_winapi(self) -> None:
        raise OSError("tried to execute PostNotification using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True


def write_ansi(f: Any) -> None:
    PostNotification().write_ansi(f)


def execute_winapi() -> None:
    PostNotification().execute_winapi()


def is_ansi_code_supported() -> bool:
    return PostNotification().is_ansi_code_supported()


__all__ = [
    "BEL",
    "BelBackend",
    "PostNotification",
    "RUST_MODULE",
    "execute_winapi",
    "is_ansi_code_supported",
    "write_ansi",
]

