"""Machine-scoped DPAPI helpers for sandbox account credentials.

Rust owner: ``codex-windows-sandbox::dpapi`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


class WindowsSandboxDpapiError(OSError):
    pass


if os.name == "nt":
    _crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    CRYPTPROTECT_UI_FORBIDDEN = 0x1
    CRYPTPROTECT_LOCAL_MACHINE = 0x4

    class DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

    _crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    _crypt32.CryptProtectData.restype = wintypes.BOOL
    _crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    _crypt32.CryptUnprotectData.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def protect(data: bytes) -> bytes:
    return _crypt(data, unprotect=False)


def unprotect(data: bytes) -> bytes:
    return _crypt(data, unprotect=True)


def _crypt(data: bytes, *, unprotect: bool) -> bytes:
    if os.name != "nt":
        raise WindowsSandboxDpapiError("DPAPI is only available on Windows")
    if not isinstance(data, bytes):
        raise TypeError("DPAPI input must be bytes")
    source = (ctypes.c_ubyte * max(1, len(data)))()
    if data:
        ctypes.memmove(source, data, len(data))
    in_blob = DATA_BLOB(len(data), ctypes.cast(source, ctypes.POINTER(ctypes.c_ubyte)))
    out_blob = DATA_BLOB()
    flags = CRYPTPROTECT_UI_FORBIDDEN | CRYPTPROTECT_LOCAL_MACHINE
    if unprotect:
        ok = _crypt32.CryptUnprotectData(
            ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob)
        )
        operation = "CryptUnprotectData"
    else:
        ok = _crypt32.CryptProtectData(
            ctypes.byref(in_blob), None, None, None, None, flags, ctypes.byref(out_blob)
        )
        operation = "CryptProtectData"
    if not ok:
        error = ctypes.get_last_error()
        raise WindowsSandboxDpapiError(error, f"{operation} failed: {error}")
    try:
        return ctypes.string_at(out_blob.pbData, out_blob.cbData)
    finally:
        if out_blob.pbData:
            _kernel32.LocalFree(out_blob.pbData)


__all__ = ["WindowsSandboxDpapiError", "protect", "unprotect"]
