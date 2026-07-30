"""Process lifecycle helpers derived from ``process.rs``."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path


async def wait_for_pid_file(path: str | Path, timeout: float = 5.0) -> str:
    target = Path(path)
    deadline = time.monotonic() + timeout
    while True:
        try:
            pid = target.read_text(encoding="utf-8").strip()
        except OSError:
            pid = ""
        if pid:
            return pid
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for pid file {target}")
        await asyncio.sleep(0.02)


def process_is_alive(pid: str) -> bool:
    value = int(pid)
    if value <= 0:
        return False
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, value)
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                return False
            return exit_code.value == 259
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(value, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


async def wait_for_process_exit(pid: str, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while process_is_alive(pid):
        if time.monotonic() >= deadline:
            raise TimeoutError(f"timed out waiting for process {pid} to exit")
        await asyncio.sleep(0.02)


__all__ = ["process_is_alive", "wait_for_pid_file", "wait_for_process_exit"]
