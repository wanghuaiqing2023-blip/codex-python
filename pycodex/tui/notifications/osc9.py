"""Behavior port for Rust ``codex-tui::notifications::osc9``."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from typing import Any, Mapping, Optional, TextIO

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="notifications::osc9",
    source="codex/codex-rs/tui/src/notifications/osc9.rs",
    status="complete",
)

ESC = "\x1b"
BEL = "\x07"
ST = "\x1b\\"


@dataclass
class Osc9Backend:
    dcs_passthrough: bool = False
    stream: Optional[TextIO] = None

    @classmethod
    def new(cls, *, dcs_passthrough: Optional[bool] = None, stream: Optional[TextIO] = None) -> "Osc9Backend":
        if dcs_passthrough is None:
            dcs_passthrough = detect_tmux_dcs_passthrough()
        return cls(dcs_passthrough=dcs_passthrough, stream=stream)

    def notify(self, message: str) -> None:
        stream = self.stream if self.stream is not None else sys.stdout
        PostNotification(str(message), self.dcs_passthrough).write_ansi(stream)
        flush = getattr(stream, "flush", None)
        if callable(flush):
            flush()


def default() -> Osc9Backend:
    return Osc9Backend.new()


def detect_tmux_dcs_passthrough(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return whether OSC 9 should be wrapped for tmux DCS passthrough."""

    environment = os.environ if env is None else env
    return bool(environment.get("TMUX"))


@dataclass(frozen=True)
class PostNotification:
    message: str
    dcs_passthrough: bool = False

    def write_ansi(self, f: Any) -> None:
        if self.dcs_passthrough:
            escaped_message = escape_tmux_dcs_passthrough_payload(self.message)
            f.write(f"{ESC}Ptmux;{ESC}{ESC}]9;{escaped_message}{BEL}{ST}")
        else:
            f.write(f"{ESC}]9;{self.message}{BEL}")

    def execute_winapi(self) -> None:
        raise OSError("tried to execute PostNotification using WinAPI; use ANSI instead")

    def is_ansi_code_supported(self) -> bool:
        return True


def write_ansi(command: PostNotification, f: Any) -> None:
    command.write_ansi(f)


def execute_winapi() -> None:
    PostNotification("", False).execute_winapi()


def is_ansi_code_supported() -> bool:
    return PostNotification("", False).is_ansi_code_supported()


def escape_tmux_dcs_passthrough_payload(message: str) -> str:
    return str(message).replace(ESC, ESC + ESC)


def post_notification_writes_plain_osc9_sequence() -> str:
    from io import StringIO

    ansi = StringIO()
    PostNotification("hello", False).write_ansi(ansi)
    return ansi.getvalue()


def post_notification_writes_tmux_dcs_wrapped_osc9_sequence() -> str:
    from io import StringIO

    ansi = StringIO()
    PostNotification("done", True).write_ansi(ansi)
    return ansi.getvalue()


def post_notification_escapes_escape_bytes_inside_tmux_payload() -> str:
    from io import StringIO

    ansi = StringIO()
    PostNotification(f"danger{ESC}[31m", True).write_ansi(ansi)
    return ansi.getvalue()


__all__ = [
    "BEL",
    "ESC",
    "Osc9Backend",
    "PostNotification",
    "RUST_MODULE",
    "ST",
    "default",
    "detect_tmux_dcs_passthrough",
    "escape_tmux_dcs_passthrough_payload",
    "execute_winapi",
    "is_ansi_code_supported",
    "post_notification_escapes_escape_bytes_inside_tmux_payload",
    "post_notification_writes_plain_osc9_sequence",
    "post_notification_writes_tmux_dcs_wrapped_osc9_sequence",
    "write_ansi",
]
