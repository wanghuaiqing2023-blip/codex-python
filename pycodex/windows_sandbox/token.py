"""Restricted-token primitives for the native Windows sandbox.

Rust owner: ``codex-windows-sandbox::token`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from dataclasses import dataclass
from typing import Iterable


class WindowsSandboxTokenError(OSError):
    pass


if os.name == "nt":
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL

    TOKEN_DUPLICATE = 0x0002
    TOKEN_QUERY = 0x0008
    TOKEN_ASSIGN_PRIMARY = 0x0001
    TOKEN_ADJUST_PRIVILEGES = 0x0020
    TOKEN_ADJUST_DEFAULT = 0x0080
    TOKEN_ADJUST_SESSIONID = 0x0100
    TOKEN_GROUPS_CLASS = 2
    TOKEN_USER_CLASS = 1
    TOKEN_LINKED_TOKEN_CLASS = 19
    TOKEN_DEFAULT_DACL_CLASS = 6
    DISABLE_MAX_PRIVILEGE = 0x01
    LUA_TOKEN = 0x04
    WRITE_RESTRICTED = 0x08
    SE_GROUP_LOGON_ID = 0xC0000000
    SE_PRIVILEGE_ENABLED = 0x00000002
    WIN_WORLD_SID = 1
    LOGON32_LOGON_INTERACTIVE = 2
    LOGON32_PROVIDER_DEFAULT = 0
    GENERIC_ALL = 0x10000000
    GRANT_ACCESS = 1
    TRUSTEE_IS_SID = 0
    TRUSTEE_IS_UNKNOWN = 0

    class SID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Sid", ctypes.c_void_p), ("Attributes", DWORD)]

    class TOKEN_USER(ctypes.Structure):
        _fields_ = [("User", SID_AND_ATTRIBUTES)]

    class LUID(ctypes.Structure):
        _fields_ = [("LowPart", DWORD), ("HighPart", wintypes.LONG)]

    class LUID_AND_ATTRIBUTES(ctypes.Structure):
        _fields_ = [("Luid", LUID), ("Attributes", DWORD)]

    class TOKEN_PRIVILEGES_ONE(ctypes.Structure):
        _fields_ = [("PrivilegeCount", DWORD), ("Privileges", LUID_AND_ATTRIBUTES * 1)]

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

    class TOKEN_DEFAULT_DACL_INFO(ctypes.Structure):
        _fields_ = [("DefaultDacl", ctypes.c_void_p)]

    class TOKEN_LINKED_TOKEN(ctypes.Structure):
        _fields_ = [("LinkedToken", HANDLE)]

    _kernel32.GetCurrentProcess.restype = HANDLE
    _kernel32.CloseHandle.argtypes = [HANDLE]
    _kernel32.CloseHandle.restype = BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p

    _advapi32.OpenProcessToken.argtypes = [HANDLE, DWORD, ctypes.POINTER(HANDLE)]
    _advapi32.OpenProcessToken.restype = BOOL
    _advapi32.GetTokenInformation.argtypes = [
        HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        DWORD,
        ctypes.POINTER(DWORD),
    ]
    _advapi32.GetTokenInformation.restype = BOOL
    _advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    _advapi32.GetLengthSid.restype = DWORD
    _advapi32.CopySid.argtypes = [DWORD, ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.CopySid.restype = BOOL
    _advapi32.CreateWellKnownSid.argtypes = [
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(DWORD),
    ]
    _advapi32.CreateWellKnownSid.restype = BOOL
    _advapi32.ConvertStringSidToSidW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.ConvertStringSidToSidW.restype = BOOL
    _advapi32.CreateRestrictedToken.argtypes = [
        HANDLE,
        DWORD,
        DWORD,
        ctypes.c_void_p,
        DWORD,
        ctypes.c_void_p,
        DWORD,
        ctypes.POINTER(SID_AND_ATTRIBUTES),
        ctypes.POINTER(HANDLE),
    ]
    _advapi32.CreateRestrictedToken.restype = BOOL
    _advapi32.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
    _advapi32.LookupPrivilegeValueW.restype = BOOL
    _advapi32.AdjustTokenPrivileges.argtypes = [
        HANDLE,
        BOOL,
        ctypes.POINTER(TOKEN_PRIVILEGES_ONE),
        DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _advapi32.AdjustTokenPrivileges.restype = BOOL
    _advapi32.SetEntriesInAclW.argtypes = [
        DWORD,
        ctypes.POINTER(EXPLICIT_ACCESS_W),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.SetEntriesInAclW.restype = DWORD
    _advapi32.SetTokenInformation.argtypes = [HANDLE, ctypes.c_int, ctypes.c_void_p, DWORD]
    _advapi32.SetTokenInformation.restype = BOOL
    _advapi32.IsTokenRestricted.argtypes = [HANDLE]
    _advapi32.IsTokenRestricted.restype = BOOL
    _advapi32.LogonUserW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        DWORD,
        DWORD,
        ctypes.POINTER(HANDLE),
    ]
    _advapi32.LogonUserW.restype = BOOL


@dataclass
class WinHandle:
    value: int

    def close(self) -> None:
        if self.value and os.name == "nt":
            _kernel32.CloseHandle(HANDLE(self.value))
            self.value = 0

    def __enter__(self) -> "WinHandle":
        if not self.value:
            raise WindowsSandboxTokenError("Windows handle is closed")
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


class LocalSid:
    def __init__(self, sid: str) -> None:
        _require_windows()
        pointer = ctypes.c_void_p()
        self._pointer = pointer
        if not _advapi32.ConvertStringSidToSidW(sid, ctypes.byref(pointer)):
            _raise_last_error(f"invalid SID string: {sid}")

    @property
    def pointer(self) -> int:
        if not self._pointer.value:
            raise WindowsSandboxTokenError("SID is closed")
        return int(self._pointer.value)

    def close(self) -> None:
        pointer = getattr(self, "_pointer", None)
        if pointer is not None and pointer.value and os.name == "nt":
            _kernel32.LocalFree(self._pointer)
            self._pointer = ctypes.c_void_p()

    def __enter__(self) -> "LocalSid":
        return self

    def __exit__(self, _exc_type: object, _exc: object, _tb: object) -> None:
        self.close()

    def __del__(self) -> None:
        self.close()


def get_current_token_for_restriction() -> WinHandle:
    _require_windows()
    desired = (
        TOKEN_DUPLICATE
        | TOKEN_QUERY
        | TOKEN_ASSIGN_PRIMARY
        | TOKEN_ADJUST_DEFAULT
        | TOKEN_ADJUST_SESSIONID
        | TOKEN_ADJUST_PRIVILEGES
    )
    token = HANDLE()
    if not _advapi32.OpenProcessToken(_kernel32.GetCurrentProcess(), desired, ctypes.byref(token)):
        _raise_last_error("OpenProcessToken failed")
    return WinHandle(_handle_value(token))


def create_readonly_token_with_caps_from(
    base_token: WinHandle | int,
    capability_sids: Iterable[LocalSid | int],
) -> WinHandle:
    return _create_token_with_caps_from(base_token, capability_sids, ())


def create_workspace_write_token_with_caps_from(
    base_token: WinHandle | int,
    capability_sids: Iterable[LocalSid | int],
) -> WinHandle:
    return _create_token_with_caps_from(base_token, capability_sids, ())


def create_readonly_token_with_caps_and_user_from(
    base_token: WinHandle | int,
    capability_sids: Iterable[LocalSid | int],
) -> WinHandle:
    user_sid = _get_user_sid_bytes(_as_handle(base_token))
    return _create_token_with_caps_from(base_token, capability_sids, (ctypes.addressof(user_sid),))


def create_workspace_write_token_with_caps_and_user_from(
    base_token: WinHandle | int,
    capability_sids: Iterable[LocalSid | int],
) -> WinHandle:
    user_sid = _get_user_sid_bytes(_as_handle(base_token))
    return _create_token_with_caps_from(base_token, capability_sids, (ctypes.addressof(user_sid),))


def logon_user(username: str, password: str, domain: str = ".") -> WinHandle:
    _require_windows()
    if not username or not password:
        raise ValueError("username and password are required")
    token = HANDLE()
    if not _advapi32.LogonUserW(
        username,
        domain,
        password,
        LOGON32_LOGON_INTERACTIVE,
        LOGON32_PROVIDER_DEFAULT,
        ctypes.byref(token),
    ):
        _raise_last_error(f"LogonUserW failed for {username}")
    return WinHandle(_handle_value(token))


def is_token_restricted(token: WinHandle | int) -> bool:
    _require_windows()
    return bool(_advapi32.IsTokenRestricted(_as_handle(token)))


def get_logon_sid_bytes(token: WinHandle | int) -> bytes:
    """Copy the token logon SID into Python-owned bytes."""

    buffer = _get_logon_sid_bytes(_as_handle(token))
    return bytes(buffer.raw)


def _create_token_with_caps_from(
    base_token: WinHandle | int,
    capability_sids: Iterable[LocalSid | int],
    extra_restricting_sids: Iterable[LocalSid | int],
) -> WinHandle:
    _require_windows()
    capabilities = tuple(_sid_pointer(sid) for sid in capability_sids)
    extras = tuple(_sid_pointer(sid) for sid in extra_restricting_sids)
    if not capabilities:
        raise WindowsSandboxTokenError("no capability SIDs provided")

    logon_sid = _get_logon_sid_bytes(_as_handle(base_token))
    everyone_sid = _world_sid_bytes()
    logon_pointer = ctypes.addressof(logon_sid)
    everyone_pointer = ctypes.addressof(everyone_sid)
    restricting = capabilities + extras + (logon_pointer, everyone_pointer)
    entries = (SID_AND_ATTRIBUTES * len(restricting))(
        *(SID_AND_ATTRIBUTES(ctypes.c_void_p(pointer), 0) for pointer in restricting)
    )
    new_token = HANDLE()
    flags = DISABLE_MAX_PRIVILEGE | LUA_TOKEN | WRITE_RESTRICTED
    if not _advapi32.CreateRestrictedToken(
        _as_handle(base_token),
        flags,
        0,
        None,
        0,
        None,
        len(entries),
        entries,
        ctypes.byref(new_token),
    ):
        _raise_last_error("CreateRestrictedToken failed")

    owned = WinHandle(_handle_value(new_token))
    try:
        _set_default_dacl(owned, (logon_pointer, everyone_pointer, *capabilities))
        _enable_single_privilege(owned, "SeChangeNotifyPrivilege")
    except BaseException:
        owned.close()
        raise
    return owned


def _get_logon_sid_bytes(token: HANDLE) -> ctypes.Array[ctypes.c_char]:
    buffer = _get_token_information(token, TOKEN_GROUPS_CLASS)
    count = DWORD.from_buffer(buffer).value
    offset = _align_up(ctypes.sizeof(DWORD), ctypes.alignment(SID_AND_ATTRIBUTES))
    entry_size = ctypes.sizeof(SID_AND_ATTRIBUTES)
    for index in range(count):
        entry = SID_AND_ATTRIBUTES.from_buffer(buffer, offset + index * entry_size)
        if entry.Attributes & SE_GROUP_LOGON_ID == SE_GROUP_LOGON_ID:
            return _copy_sid(entry.Sid)

    linked_buffer = _get_token_information(token, TOKEN_LINKED_TOKEN_CLASS, allow_missing=True)
    if linked_buffer is not None:
        linked = TOKEN_LINKED_TOKEN.from_buffer(linked_buffer)
        linked_value = _handle_value(linked.LinkedToken)
        if linked_value:
            with WinHandle(linked_value) as linked_handle:
                return _get_logon_sid_bytes(_as_handle(linked_handle))
    raise WindowsSandboxTokenError("Logon SID not present on token")


def _get_user_sid_bytes(token: HANDLE) -> ctypes.Array[ctypes.c_char]:
    buffer = _get_token_information(token, TOKEN_USER_CLASS)
    if buffer is None:
        raise WindowsSandboxTokenError("TokenUser missing")
    user = TOKEN_USER.from_buffer(buffer)
    return _copy_sid(user.User.Sid)


def _world_sid_bytes() -> ctypes.Array[ctypes.c_char]:
    size = DWORD()
    _advapi32.CreateWellKnownSid(WIN_WORLD_SID, None, None, ctypes.byref(size))
    if not size.value:
        _raise_last_error("CreateWellKnownSid size query failed")
    buffer = ctypes.create_string_buffer(size.value)
    if not _advapi32.CreateWellKnownSid(WIN_WORLD_SID, None, buffer, ctypes.byref(size)):
        _raise_last_error("CreateWellKnownSid failed")
    return buffer


def _copy_sid(pointer: int) -> ctypes.Array[ctypes.c_char]:
    size = _advapi32.GetLengthSid(ctypes.c_void_p(pointer))
    if not size:
        _raise_last_error("GetLengthSid failed")
    buffer = ctypes.create_string_buffer(size)
    if not _advapi32.CopySid(size, buffer, ctypes.c_void_p(pointer)):
        _raise_last_error("CopySid failed")
    return buffer


def _get_token_information(
    token: HANDLE,
    info_class: int,
    *,
    allow_missing: bool = False,
) -> ctypes.Array[ctypes.c_char] | None:
    size = DWORD()
    _advapi32.GetTokenInformation(token, info_class, None, 0, ctypes.byref(size))
    if not size.value:
        if allow_missing:
            return None
        _raise_last_error(f"GetTokenInformation({info_class}) size query failed")
    buffer = ctypes.create_string_buffer(size.value)
    if not _advapi32.GetTokenInformation(token, info_class, buffer, size, ctypes.byref(size)):
        if allow_missing:
            return None
        _raise_last_error(f"GetTokenInformation({info_class}) failed")
    return buffer


def _set_default_dacl(token: WinHandle, sid_pointers: Iterable[int]) -> None:
    pointers = tuple(sid_pointers)
    if not pointers:
        return
    entries = (EXPLICIT_ACCESS_W * len(pointers))()
    for index, pointer in enumerate(pointers):
        entries[index] = EXPLICIT_ACCESS_W(
            GENERIC_ALL,
            GRANT_ACCESS,
            0,
            TRUSTEE_W(None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, ctypes.c_void_p(pointer)),
        )
    acl = ctypes.c_void_p()
    result = _advapi32.SetEntriesInAclW(len(entries), entries, None, ctypes.byref(acl))
    if result != 0:
        raise WindowsSandboxTokenError(result, f"SetEntriesInAclW failed: {result}")
    try:
        info = TOKEN_DEFAULT_DACL_INFO(acl)
        if not _advapi32.SetTokenInformation(
            _as_handle(token),
            TOKEN_DEFAULT_DACL_CLASS,
            ctypes.byref(info),
            ctypes.sizeof(info),
        ):
            _raise_last_error("SetTokenInformation(TokenDefaultDacl) failed")
    finally:
        if acl.value:
            _kernel32.LocalFree(acl)


def _enable_single_privilege(token: WinHandle, name: str) -> None:
    luid = LUID()
    if not _advapi32.LookupPrivilegeValueW(None, name, ctypes.byref(luid)):
        _raise_last_error("LookupPrivilegeValueW failed")
    privileges = TOKEN_PRIVILEGES_ONE(1, (LUID_AND_ATTRIBUTES(luid, SE_PRIVILEGE_ENABLED),))
    ctypes.set_last_error(0)
    if not _advapi32.AdjustTokenPrivileges(
        _as_handle(token),
        False,
        ctypes.byref(privileges),
        0,
        None,
        None,
    ):
        _raise_last_error("AdjustTokenPrivileges failed")
    error = ctypes.get_last_error()
    if error:
        raise WindowsSandboxTokenError(error, f"AdjustTokenPrivileges error {error}")


def _sid_pointer(value: LocalSid | int) -> int:
    if isinstance(value, LocalSid):
        return value.pointer
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypeError("capability SID must be a LocalSid or positive pointer")
    return value


def _as_handle(value: WinHandle | int) -> HANDLE:
    raw = value.value if isinstance(value, WinHandle) else value
    if isinstance(raw, bool) or not isinstance(raw, int) or raw <= 0:
        raise WindowsSandboxTokenError("invalid Windows token handle")
    return HANDLE(raw)


def _handle_value(handle: object) -> int:
    value = getattr(handle, "value", handle)
    return int(value or 0)


def _align_up(value: int, alignment: int) -> int:
    return (value + alignment - 1) & ~(alignment - 1)


def _raise_last_error(message: str) -> None:
    error = ctypes.get_last_error()
    raise WindowsSandboxTokenError(error, f"{message}: {error}")


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsSandboxTokenError("Windows sandbox token APIs are only available on Windows")


__all__ = [
    "LocalSid",
    "WinHandle",
    "WindowsSandboxTokenError",
    "create_readonly_token_with_caps_and_user_from",
    "create_readonly_token_with_caps_from",
    "create_workspace_write_token_with_caps_and_user_from",
    "create_workspace_write_token_with_caps_from",
    "get_current_token_for_restriction",
    "get_logon_sid_bytes",
    "is_token_restricted",
    "logon_user",
]
