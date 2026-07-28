"""Windows PTY backend from codex-utils-pty/src/win/mod.rs."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

from .psuedocon import INFINITE, STILL_ACTIVE, PsuedoCon, conpty_supported


def _kernel32() -> ctypes.WinDLL:
    if os.name != "nt":
        raise OSError("Windows child handles are only available on Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


class WinChild:
    def __init__(self, process_handle: int, process_id: int) -> None:
        self._process_handle = int(process_handle)
        self.pid = int(process_id)
        self.returncode: int | None = None
        self._closed = False

    def wait(self) -> int:
        kernel32 = _kernel32()
        kernel32.WaitForSingleObject(wintypes.HANDLE(self._process_handle), INFINITE)
        code = wintypes.DWORD(STILL_ACTIVE)
        if not kernel32.GetExitCodeProcess(wintypes.HANDLE(self._process_handle), ctypes.byref(code)):
            raise ctypes.WinError(ctypes.get_last_error())
        self.returncode = int(code.value)
        return self.returncode

    def kill(self) -> None:
        if self.returncode is None and not _kernel32().TerminateProcess(wintypes.HANDLE(self._process_handle), 1):
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self) -> None:
        if not self._closed:
            _kernel32().CloseHandle(wintypes.HANDLE(self._process_handle))
            self._closed = True

    def __del__(self) -> None:
        if os.name == "nt":
            self.close()


class WinChildKiller:
    def __init__(self, child: WinChild) -> None:
        self._child = child

    def kill(self) -> None:
        self._child.kill()


from .conpty import ConPtySystem, RawConPty

__all__ = [
    "ConPtySystem",
    "PsuedoCon",
    "RawConPty",
    "WinChild",
    "WinChildKiller",
    "conpty_supported",
]
