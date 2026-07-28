"""Windows pseudo-console owner from codex-utils-pty/src/win/psuedocon.rs."""

from __future__ import annotations

import ctypes
import os
import subprocess
from collections.abc import Mapping, Sequence
from ctypes import wintypes
from pathlib import Path

from .procthreadattr import ProcThreadAttributeList

HPCON = wintypes.HANDLE
PSEUDOCONSOLE_RESIZE_QUIRK = 0x2
PSEUDOCONSOLE_PASSTHROUGH_MODE = 0x8
MIN_CONPTY_BUILD = 17_763
EXTENDED_STARTUPINFO_PRESENT = 0x00080000
CREATE_UNICODE_ENVIRONMENT = 0x00000400
STARTF_USESTDHANDLES = 0x00000100
INFINITE = 0xFFFFFFFF
STILL_ACTIVE = 259


class COORD(ctypes.Structure):
    _fields_ = [("X", ctypes.c_short), ("Y", ctypes.c_short)]


class STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(ctypes.c_byte)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [("StartupInfo", STARTUPINFOW), ("lpAttributeList", ctypes.c_void_p)]


class PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _kernel32() -> ctypes.WinDLL:
    if os.name != "nt":
        raise OSError("ConPTY is only available on Windows")
    return ctypes.WinDLL("kernel32", use_last_error=True)


def windows_build_number() -> int | None:
    if os.name != "nt":
        return None
    try:
        return int(os.sys.getwindowsversion().build)
    except (AttributeError, OSError):
        return None


def conpty_supported() -> bool:
    build = windows_build_number()
    return build is not None and build >= MIN_CONPTY_BUILD


def _environment_block(env: Mapping[str, str]) -> ctypes.Array[ctypes.c_wchar]:
    entries = [f"{key}={value}" for key, value in sorted(env.items(), key=lambda item: item[0].upper())]
    return ctypes.create_unicode_buffer("\0".join(entries) + "\0\0")


class PsuedoCon:
    def __init__(self, con: int, input_handle: int, output_handle: int) -> None:
        self._con = int(con)
        self._input_handle = int(input_handle)
        self._output_handle = int(output_handle)
        self._closed = False

    @classmethod
    def new(cls, size: COORD, input_handle: int, output_handle: int) -> "PsuedoCon":
        con = wintypes.HANDLE()
        result = _kernel32().CreatePseudoConsole(
            size,
            wintypes.HANDLE(input_handle),
            wintypes.HANDLE(output_handle),
            PSEUDOCONSOLE_RESIZE_QUIRK,
            ctypes.byref(con),
        )
        if int(result) != 0:
            raise OSError(f"failed to create psuedo console: HRESULT {int(result)}")
        return cls(int(con.value), input_handle, output_handle)

    def raw_handle(self) -> int:
        return self._con

    def resize(self, size: COORD) -> None:
        result = _kernel32().ResizePseudoConsole(wintypes.HANDLE(self._con), size)
        if int(result) != 0:
            raise OSError(f"failed to resize console to {size.X}x{size.Y}: HRESULT: {int(result)}")

    def spawn_command(
        self,
        program: str,
        args: Sequence[str],
        cwd: str | os.PathLike[str],
        env: Mapping[str, str],
    ) -> "WinChild":
        from . import WinChild

        attrs = ProcThreadAttributeList.with_capacity(1)
        attrs.set_pty(self._con)
        startup = STARTUPINFOEXW()
        startup.StartupInfo.cb = ctypes.sizeof(STARTUPINFOEXW)
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES
        startup.StartupInfo.hStdInput = wintypes.HANDLE(-1)
        startup.StartupInfo.hStdOutput = wintypes.HANDLE(-1)
        startup.StartupInfo.hStdError = wintypes.HANDLE(-1)
        startup.lpAttributeList = attrs.as_mut_ptr()
        info = PROCESS_INFORMATION()
        command = ctypes.create_unicode_buffer(subprocess.list2cmdline([program, *args]))
        environment = _environment_block(env)
        executable = str(Path(program))
        created = _kernel32().CreateProcessW(
            executable,
            command,
            None,
            None,
            False,
            EXTENDED_STARTUPINFO_PRESENT | CREATE_UNICODE_ENVIRONMENT,
            ctypes.cast(environment, ctypes.c_void_p),
            str(Path(cwd)),
            ctypes.byref(startup),
            ctypes.byref(info),
        )
        attrs.close()
        if not created:
            raise ctypes.WinError(ctypes.get_last_error())
        _kernel32().CloseHandle(info.hThread)
        return WinChild(int(info.hProcess), int(info.dwProcessId))

    def close(self) -> None:
        if self._closed:
            return
        kernel32 = _kernel32()
        kernel32.ClosePseudoConsole(wintypes.HANDLE(self._con))
        kernel32.CloseHandle(wintypes.HANDLE(self._input_handle))
        kernel32.CloseHandle(wintypes.HANDLE(self._output_handle))
        self._closed = True

    def __del__(self) -> None:
        if os.name == "nt":
            self.close()


__all__ = [
    "COORD",
    "HPCON",
    "PSEUDOCONSOLE_PASSTHROUGH_MODE",
    "PSEUDOCONSOLE_RESIZE_QUIRK",
    "PsuedoCon",
    "conpty_supported",
    "windows_build_number",
]
