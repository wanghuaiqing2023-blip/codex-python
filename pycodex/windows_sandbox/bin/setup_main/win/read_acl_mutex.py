"""Named mutex used to serialize background read-ACL updates."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


READ_ACL_MUTEX_NAME = r"Local\CodexSandboxReadAcl"
ERROR_ALREADY_EXISTS = 183
ERROR_FILE_NOT_FOUND = 2
MUTEX_ALL_ACCESS = 0x001F0001


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.CreateMutexW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
    _kernel32.OpenMutexW.restype = wintypes.HANDLE
    _kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _kernel32.ReleaseMutex.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


class ReadAclMutexGuard:
    def __init__(self, handle: int) -> None:
        self._handle = handle

    def close(self) -> None:
        handle, self._handle = self._handle, 0
        if handle:
            _kernel32.ReleaseMutex(handle)
            _kernel32.CloseHandle(handle)

    def __enter__(self) -> "ReadAclMutexGuard":
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


def read_acl_mutex_exists() -> bool:
    _require_windows()
    ctypes.set_last_error(0)
    handle = _kernel32.OpenMutexW(MUTEX_ALL_ACCESS, False, READ_ACL_MUTEX_NAME)
    if not handle:
        error = ctypes.get_last_error()
        if error == ERROR_FILE_NOT_FOUND:
            return False
        raise OSError(error, f"OpenMutexW failed: {error}")
    _kernel32.CloseHandle(handle)
    return True


def acquire_read_acl_mutex() -> ReadAclMutexGuard | None:
    _require_windows()
    ctypes.set_last_error(0)
    handle = _kernel32.CreateMutexW(None, True, READ_ACL_MUTEX_NAME)
    if not handle:
        error = ctypes.get_last_error()
        raise OSError(error, f"CreateMutexW failed: {error}")
    if ctypes.get_last_error() == ERROR_ALREADY_EXISTS:
        _kernel32.CloseHandle(handle)
        return None
    return ReadAclMutexGuard(handle)


def _require_windows() -> None:
    if os.name != "nt":
        raise OSError("read ACL mutex requires Windows")


__all__ = [
    "READ_ACL_MUTEX_NAME",
    "ReadAclMutexGuard",
    "acquire_read_acl_mutex",
    "read_acl_mutex_exists",
]
