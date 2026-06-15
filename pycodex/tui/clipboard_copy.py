"""Clipboard copy backend parity for Rust ``codex-tui::clipboard_copy``.

The Rust module chooses between native clipboard, WSL PowerShell, tmux
clipboard forwarding, and OSC 52. Python keeps the same decision tree and error
messages while avoiding non-standard clipboard dependencies. Native clipboard
support is therefore an explicit unavailable backend by default, which still
exercises the Rust fallback path instead of silently pretending to copy.
"""

from __future__ import annotations

import base64
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, TextIO, Union

from ._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="clipboard_copy",
    source="codex/codex-rs/tui/src/clipboard_copy.rs",
    status="complete",
)

OSC52_MAX_RAW_BYTES = 100_000
STDERR_SUPPRESSION_MUTEX = None


class ClipboardCopyError(RuntimeError):
    """Error string boundary used by Rust ``Result<_, String>`` paths."""


@dataclass
class ClipboardLease:
    """Lifetime token for native clipboard ownership.

    Rust stores the Linux ``arboard::Clipboard`` here. Python carries an opaque
    owner object only when a real native backend supplies one.
    """

    owner: Any = None

    @classmethod
    def native_linux(cls, clipboard: Any) -> "ClipboardLease":
        return cls(owner=clipboard)

    @classmethod
    def test(cls) -> "ClipboardLease":
        return cls(owner=None)


@dataclass(frozen=True)
class CopyEnvironment:
    ssh_session: bool
    wsl_session: bool
    tmux_session: bool


def copy_to_clipboard(text: str) -> Optional[ClipboardLease]:
    """Copy text using the Rust backend selection order."""

    return copy_to_clipboard_with(
        text,
        CopyEnvironment(
            ssh_session=is_ssh_session(),
            wsl_session=is_wsl_session(),
            tmux_session=is_tmux_session(),
        ),
        tmux_clipboard_copy,
        osc52_copy,
        arboard_copy,
        wsl_clipboard_copy,
    )


def _as_error(err: Union[Exception, str]) -> str:
    return str(err)


def copy_to_clipboard_with(
    text: str,
    environment: CopyEnvironment,
    tmux_copy_fn: Callable[[str], None],
    osc52_copy_fn: Callable[[str], None],
    arboard_copy_fn: Callable[[str], Optional[ClipboardLease]],
    wsl_copy_fn: Callable[[str], None],
) -> Optional[ClipboardLease]:
    """Core Rust copy decision tree with injected backends."""

    if environment.ssh_session:
        try:
            terminal_clipboard_copy_with(text, environment.tmux_session, tmux_copy_fn, osc52_copy_fn)
            return None
        except Exception as exc:
            terminal_err = _as_error(exc)
            if environment.tmux_session:
                raise ClipboardCopyError(f"terminal clipboard copy failed over SSH: {terminal_err}") from None
            raise ClipboardCopyError(f"OSC 52 clipboard copy failed over SSH: {terminal_err}") from None

    try:
        return arboard_copy_fn(text)
    except Exception as exc:
        native_err = _as_error(exc)

    if environment.wsl_session:
        try:
            wsl_copy_fn(text)
            return None
        except Exception as exc:
            wsl_err = _as_error(exc)
        try:
            terminal_clipboard_copy_with(text, environment.tmux_session, tmux_copy_fn, osc52_copy_fn)
            return None
        except Exception as exc:
            terminal_err = _as_error(exc)
            if environment.tmux_session:
                raise ClipboardCopyError(
                    f"native clipboard: {native_err}; WSL fallback: {wsl_err}; terminal fallback: {terminal_err}"
                ) from None
            raise ClipboardCopyError(
                f"native clipboard: {native_err}; WSL fallback: {wsl_err}; OSC 52 fallback: {terminal_err}"
            ) from None

    try:
        terminal_clipboard_copy_with(text, environment.tmux_session, tmux_copy_fn, osc52_copy_fn)
        return None
    except Exception as exc:
        terminal_err = _as_error(exc)
        if environment.tmux_session:
            raise ClipboardCopyError(f"native clipboard: {native_err}; terminal fallback: {terminal_err}") from None
        raise ClipboardCopyError(f"native clipboard: {native_err}; OSC 52 fallback: {terminal_err}") from None


def terminal_clipboard_copy_with(
    text: str,
    tmux_session: bool,
    tmux_copy_fn: Callable[[str], None],
    osc52_copy_fn: Callable[[str], None],
) -> None:
    if tmux_session:
        try:
            tmux_copy_fn(text)
            return
        except Exception as exc:
            tmux_err = _as_error(exc)
        try:
            osc52_copy_fn(text)
            return
        except Exception as exc:
            raise ClipboardCopyError(f"tmux clipboard: {tmux_err}; OSC 52 fallback: {_as_error(exc)}") from None

    osc52_copy_fn(text)


def is_ssh_session() -> bool:
    return "SSH_TTY" in os.environ or "SSH_CONNECTION" in os.environ


def is_tmux_session() -> bool:
    return "TMUX" in os.environ or "TMUX_PANE" in os.environ


def is_wsl_session() -> bool:
    if sys.platform != "linux":
        return False
    try:
        text = ""
        for path in ("/proc/sys/kernel/osrelease", "/proc/version"):
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                    text += handle.read().lower()
            except OSError:
                pass
        return "microsoft" in text or "wsl" in text
    except OSError:
        return False


def arboard_copy(_text: str) -> Optional[ClipboardLease]:
    raise ClipboardCopyError("native clipboard unavailable: arboard backend is not available in Python")


def wsl_clipboard_copy(text: str) -> None:
    if sys.platform != "linux":
        raise ClipboardCopyError("WSL clipboard fallback unavailable on this platform")

    command = [
        "powershell.exe",
        "-NoProfile",
        "-Command",
        "[Console]::InputEncoding = [System.Text.Encoding]::UTF8; "
        "$ErrorActionPreference = 'Stop'; "
        "$text = [Console]::In.ReadToEnd(); Set-Clipboard -Value $text",
    ]
    try:
        completed = subprocess.run(command, input=text, text=True, capture_output=True, check=False)
    except OSError as exc:
        raise ClipboardCopyError(f"failed to spawn powershell.exe: {exc}") from None

    if completed.returncode == 0:
        return

    stderr = completed.stderr.strip()
    if stderr:
        raise ClipboardCopyError(f"powershell.exe failed: {stderr}") from None
    raise ClipboardCopyError(f"powershell.exe exited with status {completed.returncode}") from None


def tmux_clipboard_copy(text: str) -> None:
    tmux_clipboard_copy_ready(
        lambda: tmux_command_output(["show-options", "-gv", "set-clipboard"]),
        lambda: tmux_command_output(["info"]),
    )
    try:
        completed = subprocess.run(
            ["tmux", "load-buffer", "-w", "-"],
            input=text,
            text=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            check=False,
        )
    except OSError as exc:
        raise ClipboardCopyError(f"failed to spawn tmux: {exc}") from None

    if completed.returncode == 0:
        return
    stderr = (completed.stderr or "").strip()
    if stderr:
        raise ClipboardCopyError(f"tmux failed: {stderr}") from None
    raise ClipboardCopyError(f"tmux exited with status {completed.returncode}") from None


def tmux_clipboard_copy_ready(
    set_clipboard_fn: Callable[[], str],
    tmux_info_fn: Callable[[], str],
) -> None:
    set_clipboard = set_clipboard_fn()
    if set_clipboard.strip() == "off":
        raise ClipboardCopyError("tmux clipboard forwarding is disabled")

    tmux_info = tmux_info_fn()
    if any("Ms: [missing]" in line for line in tmux_info.splitlines()):
        raise ClipboardCopyError("tmux clipboard forwarding is unavailable: missing Ms capability")


def tmux_command_output(args: Sequence[str]) -> str:
    try:
        completed = subprocess.run(["tmux", *args], stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    except OSError as exc:
        raise ClipboardCopyError(f"failed to spawn tmux: {exc}") from None

    if completed.returncode == 0:
        try:
            return completed.stdout.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ClipboardCopyError(f"tmux output was not UTF-8: {exc}") from None

    stderr = completed.stderr.decode("utf-8", errors="replace").strip()
    if stderr:
        raise ClipboardCopyError(f"tmux failed: {stderr}") from None
    raise ClipboardCopyError(f"tmux exited with status {completed.returncode}") from None


@dataclass
class SuppressStderr:
    """No-op context boundary for Rust stderr suppression guard."""

    @classmethod
    def new(cls) -> "SuppressStderr":
        return cls()

    def __enter__(self) -> "SuppressStderr":
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> bool:
        return False


def drop(_value: Any) -> None:
    return None


def osc52_copy(text: str) -> None:
    sequence = osc52_sequence(text, is_tmux_session())
    write_osc52_to_writer(sys.stdout, sequence)


def write_osc52_to_writer(writer: Union[TextIO, Any], sequence: str) -> None:
    try:
        writer.write(sequence)
    except Exception as exc:
        raise ClipboardCopyError(f"failed to write OSC 52: {exc}") from None
    try:
        writer.flush()
    except Exception as exc:
        raise ClipboardCopyError(f"failed to flush OSC 52: {exc}") from None


def osc52_sequence(text: str, tmux: bool) -> str:
    raw_bytes = len(text.encode("utf-8"))
    if raw_bytes > OSC52_MAX_RAW_BYTES:
        raise ClipboardCopyError(f"OSC 52 payload too large ({raw_bytes} bytes; max {OSC52_MAX_RAW_BYTES})")

    encoded = base64.b64encode(text.encode("utf-8")).decode("ascii")
    if tmux:
        return f"\x1bPtmux;\x1b\x1b]52;c;{encoded}\x07\x1b\\"
    return f"\x1b]52;c;{encoded}\x07"


def remote_environment() -> CopyEnvironment:
    return CopyEnvironment(ssh_session=True, wsl_session=True, tmux_session=False)


def remote_tmux_environment() -> CopyEnvironment:
    return CopyEnvironment(ssh_session=True, wsl_session=True, tmux_session=True)


def local_environment() -> CopyEnvironment:
    return CopyEnvironment(ssh_session=False, wsl_session=False, tmux_session=False)


def local_wsl_environment() -> CopyEnvironment:
    return CopyEnvironment(ssh_session=False, wsl_session=True, tmux_session=False)


def local_tmux_environment() -> CopyEnvironment:
    return CopyEnvironment(ssh_session=False, wsl_session=False, tmux_session=True)


__all__ = [
    "ClipboardCopyError",
    "ClipboardLease",
    "CopyEnvironment",
    "OSC52_MAX_RAW_BYTES",
    "RUST_MODULE",
    "STDERR_SUPPRESSION_MUTEX",
    "SuppressStderr",
    "arboard_copy",
    "copy_to_clipboard",
    "copy_to_clipboard_with",
    "drop",
    "is_ssh_session",
    "is_tmux_session",
    "is_wsl_session",
    "local_environment",
    "local_tmux_environment",
    "local_wsl_environment",
    "osc52_copy",
    "osc52_sequence",
    "remote_environment",
    "remote_tmux_environment",
    "terminal_clipboard_copy_with",
    "tmux_clipboard_copy",
    "tmux_clipboard_copy_ready",
    "tmux_command_output",
    "write_osc52_to_writer",
    "wsl_clipboard_copy",
]
