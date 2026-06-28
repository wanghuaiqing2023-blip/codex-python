"""Windows VT-input Textual driver for the PyCodex product TUI.

Rust ownership:
- ``codex-tui::tui`` enables raw/VT keyboard input before entering the app.
- ``codex-tui::tui::event_stream`` consumes crossterm's byte/VT event stream.

Vendored Textual's default Windows driver reads ``ReadConsoleInputW`` records.
That is a reasonable Textual default, but it does not match Rust Codex's
ConPTY/VT byte-stream behavior closely enough for control-key automation.  This
adapter keeps Textual's Windows display path and swaps only the input monitor to
feed Textual's own XTerm parser from ``stdin`` bytes after application mode has
enabled ``ENABLE_VIRTUAL_TERMINAL_INPUT``.
"""

from __future__ import annotations

import os
import sys
import time
import json
import locale
from codecs import getincrementaldecoder
from threading import Event, Thread
from typing import Any

from .textual_compat import load_textual_module

_xterm_parser = load_textual_module("textual._xterm_parser")
_windows_driver = load_textual_module("textual.drivers.windows_driver")
_win32 = load_textual_module("textual.drivers.win32")
_writer_thread = load_textual_module("textual.drivers._writer_thread")

XTermParser = _xterm_parser.XTermParser
WindowsDriver = _windows_driver.WindowsDriver
WriterThread = _writer_thread.WriterThread


def _trace(event: str, **fields: Any) -> None:
    path = os.environ.get("PYCODEX_TUI_TIMING_LOG")
    if not path:
        return
    record = {"t": time.monotonic(), "event": event, **fields}
    try:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True, default=str) + "\n")
    except OSError:
        pass


def _input_encoding_candidates() -> tuple[str, ...]:
    """Return Rust-shaped Windows input decoding candidates.

    Rust/crossterm receives decoded key events from the terminal backend.  This
    Textual adapter reads bytes, so it must tolerate both UTF-8 VT streams and
    Windows console-codepage bytes produced by IME input in PowerShell.
    """

    local_encodings = [
        str(value)
        for value in (getattr(sys.stdin, "encoding", None), locale.getpreferredencoding(False))
        if value
    ]
    if os.name == "nt":
        candidates = [encoding for encoding in local_encodings if encoding.lower() != "utf-8"]
        candidates.append("utf-8")
    else:
        candidates = ["utf-8"]
        candidates.extend(encoding for encoding in local_encodings if encoding.lower() != "utf-8")
    deduped: list[str] = []
    for encoding in candidates:
        if encoding.lower() not in {candidate.lower() for candidate in deduped}:
            deduped.append(encoding)
    return tuple(deduped)


class _VtInputDecoder:
    def __init__(self, encodings: tuple[str, ...] | None = None) -> None:
        self.encodings = encodings or _input_encoding_candidates()
        self._primary_encoding = self.encodings[0] if self.encodings else "utf-8"
        self._primary_decoder = getincrementaldecoder(self._primary_encoding)()

    def decode(self, data: bytes) -> str:
        try:
            return self._primary_decoder.decode(data)
        except UnicodeDecodeError as error:
            _trace(
                "textual_windows_vt_input_decode_fallback",
                error=str(error),
                encodings=self.encodings,
            )
            self._primary_decoder.reset()
            for encoding in self.encodings:
                if encoding.lower() == self._primary_encoding.lower():
                    continue
                try:
                    return data.decode(encoding)
                except UnicodeDecodeError:
                    continue
                except LookupError:
                    continue
            return data.decode(self.encodings[-1] if self.encodings else "utf-8", errors="replace")


class _WindowsVtInputMonitor(Thread):
    """Read VT bytes from stdin and pass parsed Textual events to the driver."""

    def __init__(self, app: Any, exit_event: Event, process_event: Any, *, debug: bool = False) -> None:
        super().__init__(name="pycodex-textual-windows-vt-input", daemon=True)
        self.app = app
        self.exit_event = exit_event
        self.process_event = process_event
        self.debug = bool(debug)

    def run(self) -> None:
        parser = XTermParser(lambda: False, self.debug)
        decoder = _VtInputDecoder()
        fileno = sys.stdin.fileno()
        try:
            while not self.exit_event.is_set():
                data = os.read(fileno, 1024)
                if not data:
                    continue
                _trace("textual_windows_vt_input_bytes", data=repr(data))
                for event in parser.feed(decoder.decode(data)):
                    _trace(
                        "textual_windows_vt_input_event",
                        event_type=type(event).__name__,
                        key=getattr(event, "key", None),
                        character=repr(getattr(event, "character", None)),
                    )
                    self.process_event(event)
        except OSError as error:
            self.app.log.error("PYCODEX WINDOWS VT INPUT ERROR", error)
        except BaseException as error:
            self.app.log.error("PYCODEX WINDOWS VT INPUT ERROR", error)


class PyCodexWindowsVtDriver(WindowsDriver):
    """Textual Windows driver with Rust-shaped VT byte input semantics."""

    def start_application_mode(self) -> None:
        self._restore_console = _win32.enable_application_mode()

        self._writer_thread = WriterThread(self._file)
        self._writer_thread.start()

        self.write("\x1b[?1049h")
        self._enable_mouse_support()
        self.write("\x1b[?25l")
        self.write("\033[?1003h\n")
        self._enable_bracketed_paste()

        self._event_thread = _WindowsVtInputMonitor(
            self._app,
            self.exit_event,
            self.process_event,
            debug=self._debug,
        )
        self._event_thread.start()

    def disable_input(self) -> None:
        try:
            if not self.exit_event.is_set():
                self._disable_mouse_support()
                self.exit_event.set()
                if self._event_thread is not None:
                    self._event_thread.join(timeout=0.2)
                    self._event_thread = None
                self.exit_event.clear()
        except Exception:
            pass
