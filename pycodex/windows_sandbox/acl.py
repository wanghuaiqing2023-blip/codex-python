"""ACL primitives used by the native Windows sandbox.

Rust owner: ``codex-windows-sandbox::acl`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes
from pathlib import Path
from typing import Iterable

from .token import LocalSid


class WindowsSandboxAclError(OSError):
    pass


if os.name == "nt":
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    DWORD = wintypes.DWORD
    SE_FILE_OBJECT = 1
    SE_KERNEL_OBJECT = 6
    DACL_SECURITY_INFORMATION = 0x00000004
    SET_ACCESS = 2
    DENY_ACCESS = 3
    REVOKE_ACCESS = 4
    TRUSTEE_IS_SID = 0
    TRUSTEE_IS_UNKNOWN = 0
    OBJECT_INHERIT_ACE = 0x1
    CONTAINER_INHERIT_ACE = 0x2
    FILE_GENERIC_READ = 0x00120089
    FILE_GENERIC_WRITE = 0x00120116
    FILE_GENERIC_EXECUTE = 0x001200A0
    DELETE = 0x00010000
    FILE_DELETE_CHILD = 0x00000040
    FILE_WRITE_DATA = 0x00000002
    FILE_APPEND_DATA = 0x00000004
    FILE_WRITE_EA = 0x00000010
    FILE_WRITE_ATTRIBUTES = 0x00000100
    GENERIC_READ_MASK = 0x80000000
    GENERIC_WRITE_MASK = 0x40000000
    ACCESS_ALLOWED_ACE_TYPE = 0
    ACCESS_DENIED_ACE_TYPE = 1
    INHERIT_ONLY_ACE = 0x08
    INHERITED_ACE = 0x10
    ACL_REVISION = 2
    MAXDWORD = 0xFFFFFFFF
    ACL_SIZE_INFORMATION_CLASS = 2
    WRITE_ALLOW_MASK = (
        FILE_GENERIC_READ
        | FILE_GENERIC_WRITE
        | FILE_GENERIC_EXECUTE
        | DELETE
        | FILE_DELETE_CHILD
    )
    READ_CONTROL = 0x00020000
    WRITE_DAC = 0x00040000
    FILE_SHARE_READ = 0x00000001
    FILE_SHARE_WRITE = 0x00000002
    OPEN_EXISTING = 3
    FILE_ATTRIBUTE_NORMAL = 0x00000080

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

    class ACL_SIZE_INFORMATION(ctypes.Structure):
        _fields_ = [("AceCount", DWORD), ("AclBytesInUse", DWORD), ("AclBytesFree", DWORD)]

    class ACE_HEADER(ctypes.Structure):
        _fields_ = [("AceType", ctypes.c_ubyte), ("AceFlags", ctypes.c_ubyte), ("AceSize", wintypes.WORD)]

    class ACCESS_ACE(ctypes.Structure):
        _fields_ = [("Header", ACE_HEADER), ("Mask", DWORD), ("SidStart", DWORD)]

    _advapi32.GetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.GetNamedSecurityInfoW.restype = DWORD
    _advapi32.SetEntriesInAclW.argtypes = [
        DWORD,
        ctypes.POINTER(EXPLICIT_ACCESS_W),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.SetEntriesInAclW.restype = DWORD
    _advapi32.SetNamedSecurityInfoW.argtypes = [
        wintypes.LPWSTR,
        ctypes.c_int,
        DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    _advapi32.SetNamedSecurityInfoW.restype = DWORD
    _advapi32.GetSecurityInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        DWORD,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.GetSecurityInfo.restype = DWORD
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
    _advapi32.GetAclInformation.argtypes = [ctypes.c_void_p, ctypes.c_void_p, DWORD, ctypes.c_int]
    _advapi32.GetAclInformation.restype = wintypes.BOOL
    _advapi32.GetAce.argtypes = [ctypes.c_void_p, DWORD, ctypes.POINTER(ctypes.c_void_p)]
    _advapi32.GetAce.restype = wintypes.BOOL
    _advapi32.InitializeAcl.argtypes = [ctypes.c_void_p, DWORD, DWORD]
    _advapi32.InitializeAcl.restype = wintypes.BOOL
    _advapi32.AddAce.argtypes = [ctypes.c_void_p, DWORD, DWORD, ctypes.c_void_p, DWORD]
    _advapi32.AddAce.restype = wintypes.BOOL
    _advapi32.EqualSid.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    _advapi32.EqualSid.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        DWORD,
        DWORD,
        ctypes.c_void_p,
        DWORD,
        DWORD,
        wintypes.HANDLE,
    ]
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


def ensure_allow_write_aces(path: str | Path, sids: Iterable[LocalSid | int]) -> bool:
    return ensure_allow_mask_aces(path, sids, WRITE_ALLOW_MASK)


def path_mask_allows(
    path: str | Path,
    sids: Iterable[LocalSid | int],
    mask: int,
) -> bool:
    """Return whether one listed principal already has the complete mask."""

    _require_windows()
    target = Path(path)
    if not target.exists():
        return False
    path_buffer = ctypes.create_unicode_buffer(str(target))
    security_descriptor = ctypes.c_void_p()
    current_dacl = ctypes.c_void_p()
    result = _advapi32.GetNamedSecurityInfoW(
        path_buffer,
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(current_dacl),
        None,
        ctypes.byref(security_descriptor),
    )
    if result != 0:
        raise WindowsSandboxAclError(result, f"GetNamedSecurityInfoW failed: {result}")
    try:
        return any(
            _dacl_has_ace(current_dacl, _sid_pointer(sid), ACCESS_ALLOWED_ACE_TYPE, mask, require_all_bits=True)
            for sid in sids
        )
    finally:
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)


def ensure_allow_mask_aces(
    path: str | Path,
    sids: Iterable[LocalSid | int],
    allow_mask: int,
    inheritance: int = CONTAINER_INHERIT_ACE | OBJECT_INHERIT_ACE,
) -> bool:
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    pointers = tuple(_sid_pointer(sid) for sid in sids)
    if not pointers:
        return False
    if isinstance(allow_mask, bool) or not isinstance(allow_mask, int) or allow_mask < 0:
        raise ValueError("allow_mask must be a non-negative integer")

    path_buffer = ctypes.create_unicode_buffer(str(target))
    security_descriptor = ctypes.c_void_p()
    current_dacl = ctypes.c_void_p()
    result = _advapi32.GetNamedSecurityInfoW(
        path_buffer,
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(current_dacl),
        None,
        ctypes.byref(security_descriptor),
    )
    if result != 0:
        raise WindowsSandboxAclError(result, f"GetNamedSecurityInfoW failed: {result}")

    missing = tuple(
        pointer
        for pointer in pointers
        if not _dacl_has_ace(current_dacl, pointer, ACCESS_ALLOWED_ACE_TYPE, allow_mask, require_all_bits=True)
    )
    if not missing:
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)
        return False

    new_dacl = ctypes.c_void_p()
    try:
        entries = (EXPLICIT_ACCESS_W * len(missing))(
            *(
                EXPLICIT_ACCESS_W(
                    allow_mask,
                    SET_ACCESS,
                    inheritance,
                    TRUSTEE_W(None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, ctypes.c_void_p(pointer)),
                )
                for pointer in missing
            )
        )
        result = _advapi32.SetEntriesInAclW(
            len(entries),
            entries,
            current_dacl,
            ctypes.byref(new_dacl),
        )
        if result != 0:
            raise WindowsSandboxAclError(result, f"SetEntriesInAclW failed: {result}")
        result = _advapi32.SetNamedSecurityInfoW(
            path_buffer,
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            new_dacl,
            None,
        )
        if result != 0:
            raise WindowsSandboxAclError(result, f"SetNamedSecurityInfoW failed: {result}")
        return True
    finally:
        if new_dacl.value:
            _kernel32.LocalFree(new_dacl)
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)


def add_allow_ace(path: str | Path, sid: LocalSid | int) -> bool:
    return ensure_allow_mask_aces(
        path,
        (sid,),
        FILE_GENERIC_READ | FILE_GENERIC_WRITE | FILE_GENERIC_EXECUTE,
    )


def add_deny_write_ace(path: str | Path, sid: LocalSid | int) -> bool:
    mask = (
        FILE_GENERIC_WRITE
        | FILE_WRITE_DATA
        | FILE_APPEND_DATA
        | FILE_WRITE_EA
        | FILE_WRITE_ATTRIBUTES
        | GENERIC_WRITE_MASK
        | DELETE
        | FILE_DELETE_CHILD
    )
    return _add_deny_ace(path, sid, mask)


def add_deny_read_ace(path: str | Path, sid: LocalSid | int) -> bool:
    return _add_deny_ace(path, sid, FILE_GENERIC_READ | GENERIC_READ_MASK)


def allow_null_device(sid: LocalSid | int) -> bool:
    """Grant the sandbox principal access to ``NUL`` redirection.

    Rust owner: ``codex-windows-sandbox::acl::allow_null_device``.
    """

    _require_windows()
    invalid_handle = ctypes.c_void_p(-1).value
    handle = _kernel32.CreateFileW(
        r"\\.\NUL",
        READ_CONTROL | WRITE_DAC,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_ATTRIBUTE_NORMAL,
        None,
    )
    if not handle or ctypes.cast(handle, ctypes.c_void_p).value == invalid_handle:
        return False
    security_descriptor = ctypes.c_void_p()
    current_dacl = ctypes.c_void_p()
    new_dacl = ctypes.c_void_p()
    try:
        result = _advapi32.GetSecurityInfo(
            handle,
            SE_KERNEL_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(current_dacl),
            None,
            ctypes.byref(security_descriptor),
        )
        if result != 0:
            return False
        entry = EXPLICIT_ACCESS_W(
            FILE_GENERIC_READ | FILE_GENERIC_WRITE | FILE_GENERIC_EXECUTE,
            SET_ACCESS,
            0,
            TRUSTEE_W(None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, ctypes.c_void_p(_sid_pointer(sid))),
        )
        result = _advapi32.SetEntriesInAclW(1, ctypes.byref(entry), current_dacl, ctypes.byref(new_dacl))
        if result != 0:
            return False
        return _advapi32.SetSecurityInfo(
            handle,
            SE_KERNEL_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            new_dacl,
            None,
        ) == 0
    finally:
        if new_dacl.value:
            _kernel32.LocalFree(new_dacl)
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)
        _kernel32.CloseHandle(handle)


def _add_deny_ace(path: str | Path, sid: LocalSid | int, mask: int) -> bool:
    _require_windows()
    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(target)
    pointer = _sid_pointer(sid)
    path_buffer = ctypes.create_unicode_buffer(str(target))
    security_descriptor = ctypes.c_void_p()
    current_dacl = ctypes.c_void_p()
    result = _advapi32.GetNamedSecurityInfoW(
        path_buffer,
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(current_dacl),
        None,
        ctypes.byref(security_descriptor),
    )
    if result != 0:
        raise WindowsSandboxAclError(result, f"GetNamedSecurityInfoW failed: {result}")
    if _dacl_has_ace(current_dacl, pointer, ACCESS_DENIED_ACE_TYPE, mask, require_all_bits=False):
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)
        return False

    new_dacl = ctypes.c_void_p()
    try:
        entry = EXPLICIT_ACCESS_W(
            mask,
            DENY_ACCESS,
            CONTAINER_INHERIT_ACE | OBJECT_INHERIT_ACE,
            TRUSTEE_W(None, 0, TRUSTEE_IS_SID, TRUSTEE_IS_UNKNOWN, ctypes.c_void_p(pointer)),
        )
        result = _advapi32.SetEntriesInAclW(1, ctypes.byref(entry), current_dacl, ctypes.byref(new_dacl))
        if result != 0:
            raise WindowsSandboxAclError(result, f"SetEntriesInAclW failed: {result}")
        result = _advapi32.SetNamedSecurityInfoW(
            path_buffer,
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            new_dacl,
            None,
        )
        if result != 0:
            raise WindowsSandboxAclError(result, f"SetNamedSecurityInfoW failed: {result}")
        return True
    finally:
        if new_dacl.value:
            _kernel32.LocalFree(new_dacl)
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)


def revoke_ace(path: str | Path, sid: LocalSid | int) -> bool:
    """Remove explicit ACEs for ``sid`` from an existing path."""

    _require_windows()
    target = Path(path)
    if not target.exists():
        return False
    path_buffer = ctypes.create_unicode_buffer(str(target))
    security_descriptor = ctypes.c_void_p()
    current_dacl = ctypes.c_void_p()
    result = _advapi32.GetNamedSecurityInfoW(
        path_buffer,
        SE_FILE_OBJECT,
        DACL_SECURITY_INFORMATION,
        None,
        None,
        ctypes.byref(current_dacl),
        None,
        ctypes.byref(security_descriptor),
    )
    if result != 0:
        return False
    try:
        sid_pointer = _sid_pointer(sid)
        new_dacl, removed = _dacl_without_explicit_sid(current_dacl, sid_pointer)
        if not removed:
            return False
        result = _advapi32.SetNamedSecurityInfoW(
            path_buffer,
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.cast(new_dacl, ctypes.c_void_p),
            None,
        )
        if result != 0:
            raise WindowsSandboxAclError(result, f"SetNamedSecurityInfoW failed: {result}")
        verify_descriptor = ctypes.c_void_p()
        verify_dacl = ctypes.c_void_p()
        verify_result = _advapi32.GetNamedSecurityInfoW(
            path_buffer,
            SE_FILE_OBJECT,
            DACL_SECURITY_INFORMATION,
            None,
            None,
            ctypes.byref(verify_dacl),
            None,
            ctypes.byref(verify_descriptor),
        )
        try:
            if verify_result != 0:
                raise WindowsSandboxAclError(verify_result, f"verify GetNamedSecurityInfoW failed: {verify_result}")
            if _dacl_has_explicit_sid_ace(verify_dacl, sid_pointer):
                raise WindowsSandboxAclError("explicit ACL entry remained after revoke")
        finally:
            if verify_descriptor.value:
                _kernel32.LocalFree(verify_descriptor)
        return True
    finally:
        if security_descriptor.value:
            _kernel32.LocalFree(security_descriptor)


def _dacl_without_explicit_sid(dacl: ctypes.c_void_p, sid_pointer: int) -> tuple[ctypes.Array[ctypes.c_char], bool]:
    info = ACL_SIZE_INFORMATION()
    if not dacl.value or not _advapi32.GetAclInformation(
        dacl, ctypes.byref(info), ctypes.sizeof(info), ACL_SIZE_INFORMATION_CLASS
    ):
        raise WindowsSandboxAclError("GetAclInformation failed while revoking ACL entry")
    buffer = ctypes.create_string_buffer(max(int(info.AclBytesInUse), ctypes.sizeof(DWORD) * 2))
    if not _advapi32.InitializeAcl(buffer, len(buffer), ACL_REVISION):
        raise WindowsSandboxAclError(ctypes.get_last_error(), "InitializeAcl failed")
    removed = False
    for index in range(info.AceCount):
        ace_pointer = ctypes.c_void_p()
        if not _advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)) or not ace_pointer.value:
            raise WindowsSandboxAclError(ctypes.get_last_error(), f"GetAce({index}) failed")
        header = ACE_HEADER.from_address(ace_pointer.value)
        matches = False
        if header.AceType in {ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE} and not (
            header.AceFlags & INHERITED_ACE
        ):
            stored_sid = ace_pointer.value + ctypes.sizeof(ACE_HEADER) + ctypes.sizeof(DWORD)
            matches = bool(_advapi32.EqualSid(ctypes.c_void_p(stored_sid), ctypes.c_void_p(sid_pointer)))
        if matches:
            removed = True
            continue
        if not _advapi32.AddAce(buffer, ACL_REVISION, MAXDWORD, ace_pointer, header.AceSize):
            raise WindowsSandboxAclError(ctypes.get_last_error(), f"AddAce({index}) failed")
    return buffer, removed


def _dacl_has_explicit_sid_ace(dacl: ctypes.c_void_p, sid_pointer: int) -> bool:
    info = ACL_SIZE_INFORMATION()
    if not dacl.value or not _advapi32.GetAclInformation(
        dacl, ctypes.byref(info), ctypes.sizeof(info), ACL_SIZE_INFORMATION_CLASS
    ):
        return False
    for index in range(info.AceCount):
        ace_pointer = ctypes.c_void_p()
        if not _advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)) or not ace_pointer.value:
            continue
        header = ACE_HEADER.from_address(ace_pointer.value)
        if header.AceType not in {ACCESS_ALLOWED_ACE_TYPE, ACCESS_DENIED_ACE_TYPE} or header.AceFlags & INHERITED_ACE:
            continue
        stored_sid = ace_pointer.value + ctypes.sizeof(ACE_HEADER) + ctypes.sizeof(DWORD)
        if _advapi32.EqualSid(ctypes.c_void_p(stored_sid), ctypes.c_void_p(sid_pointer)):
            return True
    return False


def _sid_pointer(value: LocalSid | int) -> int:
    if isinstance(value, LocalSid):
        return value.pointer
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise TypeError("SID must be a LocalSid or positive pointer")
    return value


def _dacl_has_ace(
    dacl: ctypes.c_void_p,
    sid_pointer: int,
    ace_type: int,
    desired_mask: int,
    *,
    require_all_bits: bool,
) -> bool:
    if not dacl.value:
        return False
    info = ACL_SIZE_INFORMATION()
    if not _advapi32.GetAclInformation(
        dacl,
        ctypes.byref(info),
        ctypes.sizeof(info),
        ACL_SIZE_INFORMATION_CLASS,
    ):
        return False
    for index in range(info.AceCount):
        ace_pointer = ctypes.c_void_p()
        if not _advapi32.GetAce(dacl, index, ctypes.byref(ace_pointer)) or not ace_pointer.value:
            continue
        ace = ACCESS_ACE.from_address(ace_pointer.value)
        if ace.Header.AceType != ace_type or ace.Header.AceFlags & INHERIT_ONLY_ACE:
            continue
        stored_sid = ace_pointer.value + ctypes.sizeof(ACE_HEADER) + ctypes.sizeof(DWORD)
        if not _advapi32.EqualSid(ctypes.c_void_p(stored_sid), ctypes.c_void_p(sid_pointer)):
            continue
        if require_all_bits:
            if ace.Mask & desired_mask == desired_mask:
                return True
        elif ace.Mask & desired_mask:
            return True
    return False


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsSandboxAclError("Windows sandbox ACL APIs are only available on Windows")


__all__ = [
    "WRITE_ALLOW_MASK",
    "WindowsSandboxAclError",
    "add_allow_ace",
    "add_deny_read_ace",
    "add_deny_write_ace",
    "allow_null_device",
    "ensure_allow_mask_aces",
    "ensure_allow_write_aces",
    "path_mask_allows",
    "revoke_ace",
]
