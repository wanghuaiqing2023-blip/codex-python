"""Private desktop lifecycle for restricted Windows processes.

Rust owner: ``codex-windows-sandbox::desktop`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
import secrets
from ctypes import wintypes
from dataclasses import dataclass

from .token import get_current_token_for_restriction, get_logon_sid_bytes


class WindowsSandboxDesktopError(OSError):
    pass


if os.name == "nt":
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _user32 = ctypes.WinDLL("user32", use_last_error=True)

    DWORD = wintypes.DWORD
    DESKTOP_READOBJECTS = 0x0001
    DESKTOP_CREATEWINDOW = 0x0002
    DESKTOP_CREATEMENU = 0x0004
    DESKTOP_HOOKCONTROL = 0x0008
    DESKTOP_JOURNALRECORD = 0x0010
    DESKTOP_JOURNALPLAYBACK = 0x0020
    DESKTOP_ENUMERATE = 0x0040
    DESKTOP_WRITEOBJECTS = 0x0080
    DESKTOP_SWITCHDESKTOP = 0x0100
    DELETE = 0x00010000
    READ_CONTROL = 0x00020000
    WRITE_DAC = 0x00040000
    WRITE_OWNER = 0x00080000
    DESKTOP_ALL_ACCESS = (
        DESKTOP_READOBJECTS
        | DESKTOP_CREATEWINDOW
        | DESKTOP_CREATEMENU
        | DESKTOP_HOOKCONTROL
        | DESKTOP_JOURNALRECORD
        | DESKTOP_JOURNALPLAYBACK
        | DESKTOP_ENUMERATE
        | DESKTOP_WRITEOBJECTS
        | DESKTOP_SWITCHDESKTOP
        | DELETE
        | READ_CONTROL
        | WRITE_DAC
        | WRITE_OWNER
    )
    GRANT_ACCESS = 1
    TRUSTEE_IS_SID = 0
    TRUSTEE_IS_UNKNOWN = 0
    SE_WINDOW_OBJECT = 7
    DACL_SECURITY_INFORMATION = 0x00000004

    class TRUSTEE_W(ctypes.Structure):
        _fields_ = [
            ("pMultipleTrustee", ctypes.c_void_p),
            ("MultipleTrusteeOperation", ctypes.c_int),
            ("TrusteeForm", ctypes.c_int),
            ("TrusteeType", ctypes.c_int),
            ("ptstrName", ctypes.c_void_p),
        ]

    class EXPLICIT_ACCESS_W(ctypes.Structure):
        _fields_ = [
            ("grfAccessPermissions", DWORD),
            ("grfAccessMode", ctypes.c_int),
            ("grfInheritance", DWORD),
            ("Trustee", TRUSTEE_W),
        ]

    _user32.CreateDesktopW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        DWORD,
        DWORD,
        ctypes.c_void_p,
    ]
    _user32.CreateDesktopW.restype = wintypes.HANDLE
    _user32.CloseDesktop.argtypes = [wintypes.HANDLE]
    _user32.CloseDesktop.restype = wintypes.BOOL
    _advapi32.SetEntriesInAclW.argtypes = [
        DWORD,
        ctypes.POINTER(EXPLICIT_ACCESS_W),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.SetEntriesInAclW.restype = DWORD
    _advapi32.SetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _advapi32.SetSecurityInfo.restype = DWORD
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


@dataclass
class LaunchDesktop:
    startup_name: str
    _handle: int = 0

    @classmethod
    def prepare(cls, use_private_desktop: bool) -> "LaunchDesktop":
        _require_windows()
        if not use_private_desktop:
            return cls("Winsta0\\Default")
        name = f"CodexSandboxDesktop-{secrets.token_hex(16)}"
        handle = _user32.CreateDesktopW(name, None, None, 0, DESKTOP_ALL_ACCESS, None)
        value = int(getattr(handle, "value", handle) or 0)
        if not value:
            _raise_last_error("CreateDesktopW failed")
        desktop = cls(f"Winsta0\\{name}", value)
        try:
            _grant_desktop_access(value)
        except BaseException:
            desktop.close()
            raise
        return desktop

    def close(self) -> None:
        if self._handle and os.name == "nt":
            _user32.CloseDesktop(wintypes.HANDLE(self._handle))
            self._handle = 0

    def __enter__(self) -> "LaunchDesktop":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


def _grant_desktop_access(handle: int) -> None:
    with get_current_token_for_restriction() as token:
        sid_bytes = get_logon_sid_bytes(token)
    sid = ctypes.create_string_buffer(sid_bytes, len(sid_bytes))
    entry = EXPLICIT_ACCESS_W(
        DESKTOP_ALL_ACCESS,
        GRANT_ACCESS,
        0,
        TRUSTEE_W(None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, ctypes.cast(sid, ctypes.c_void_p)),
    )
    acl = ctypes.c_void_p()
    result = _advapi32.SetEntriesInAclW(1, ctypes.byref(entry), None, ctypes.byref(acl))
    if result != 0:
        raise WindowsSandboxDesktopError(result, f"SetEntriesInAclW failed for private desktop: {result}")
    try:
        result = _advapi32.SetSecurityInfo(
            wintypes.HANDLE(handle),
            SE_WINDOW_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            acl,
            None,
        )
        if result != 0:
            raise WindowsSandboxDesktopError(result, f"SetSecurityInfo failed for private desktop: {result}")
    finally:
        if acl.value:
            _kernel32.LocalFree(acl)


def _raise_last_error(message: str) -> None:
    error = ctypes.get_last_error()
    raise WindowsSandboxDesktopError(error, f"{message}: {error}")


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsSandboxDesktopError("Windows sandbox desktop APIs are only available on Windows")


__all__ = ["LaunchDesktop", "WindowsSandboxDesktopError"]
