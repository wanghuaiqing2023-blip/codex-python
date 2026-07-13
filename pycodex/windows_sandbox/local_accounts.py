"""Local account provisioning for the elevated Windows sandbox helper.

Rust owner: ``setup_main::win::sandbox_users`` at fixed commit
``1c7832ffa37a3ab56f601497c00bfce120370bf9``.
"""

from __future__ import annotations

import ctypes
import os
import secrets
import string
from ctypes import wintypes

from .setup_error import SetupErrorCode, SetupFailure


SANDBOX_USERS_GROUP = "CodexSandboxUsers"
SANDBOX_USERS_GROUP_COMMENT = "Codex sandbox internal group (managed)"


if os.name == "nt":
    _netapi32 = ctypes.WinDLL("netapi32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    DWORD = wintypes.DWORD
    LPBYTE = ctypes.POINTER(ctypes.c_ubyte)
    NERR_SUCCESS = 0
    ERROR_ALIAS_EXISTS = 1379
    NERR_GROUP_EXISTS = 2223
    NERR_USER_EXISTS = 2224
    ERROR_MEMBER_IN_ALIAS = 1378
    ERROR_INSUFFICIENT_BUFFER = 122
    USER_PRIV_USER = 1
    UF_SCRIPT = 0x0001
    UF_DONT_EXPIRE_PASSWD = 0x10000

    class USER_INFO_1(ctypes.Structure):
        _fields_ = [
            ("usri1_name", wintypes.LPWSTR),
            ("usri1_password", wintypes.LPWSTR),
            ("usri1_password_age", DWORD),
            ("usri1_priv", DWORD),
            ("usri1_home_dir", wintypes.LPWSTR),
            ("usri1_comment", wintypes.LPWSTR),
            ("usri1_flags", DWORD),
            ("usri1_script_path", wintypes.LPWSTR),
        ]

    class USER_INFO_1003(ctypes.Structure):
        _fields_ = [("usri1003_password", wintypes.LPWSTR)]

    class LOCALGROUP_INFO_1(ctypes.Structure):
        _fields_ = [("lgrpi1_name", wintypes.LPWSTR), ("lgrpi1_comment", wintypes.LPWSTR)]

    class LOCALGROUP_MEMBERS_INFO_3(ctypes.Structure):
        _fields_ = [("lgrmi3_domainandname", wintypes.LPWSTR)]

    _netapi32.NetUserAdd.argtypes = [wintypes.LPCWSTR, DWORD, LPBYTE, ctypes.POINTER(DWORD)]
    _netapi32.NetUserAdd.restype = DWORD
    _netapi32.NetUserSetInfo.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD, LPBYTE, ctypes.POINTER(DWORD)]
    _netapi32.NetUserSetInfo.restype = DWORD
    _netapi32.NetLocalGroupAdd.argtypes = [wintypes.LPCWSTR, DWORD, LPBYTE, ctypes.POINTER(DWORD)]
    _netapi32.NetLocalGroupAdd.restype = DWORD
    _netapi32.NetLocalGroupAddMembers.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, DWORD, LPBYTE, DWORD]
    _netapi32.NetLocalGroupAddMembers.restype = DWORD
    _advapi32.LookupAccountNameW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(DWORD),
        wintypes.LPWSTR,
        ctypes.POINTER(DWORD),
        ctypes.POINTER(DWORD),
    ]
    _advapi32.LookupAccountNameW.restype = wintypes.BOOL
    _advapi32.ConvertSidToStringSidW.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.LPWSTR)]
    _advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def random_password(length: int = 24) -> str:
    if length < 16:
        raise ValueError("sandbox password must be at least 16 characters")
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*()-_=+"
    while True:
        password = "".join(secrets.choice(alphabet) for _ in range(length))
        if all(any(char in group for char in password) for group in (string.ascii_uppercase, string.ascii_lowercase, string.digits, "!@#$%^&*()-_=+")):
            return password


def ensure_sandbox_users_group() -> None:
    _require_windows()
    name = ctypes.create_unicode_buffer(SANDBOX_USERS_GROUP)
    comment = ctypes.create_unicode_buffer(SANDBOX_USERS_GROUP_COMMENT)
    info = LOCALGROUP_INFO_1(
        ctypes.cast(name, wintypes.LPWSTR),
        ctypes.cast(comment, wintypes.LPWSTR),
    )
    parameter_error = DWORD()
    status = _netapi32.NetLocalGroupAdd(
        None, 1, ctypes.cast(ctypes.byref(info), LPBYTE), ctypes.byref(parameter_error)
    )
    if status not in {NERR_SUCCESS, ERROR_ALIAS_EXISTS, NERR_GROUP_EXISTS}:
        raise SetupFailure(
            SetupErrorCode.HELPER_USERS_GROUP_CREATE_FAILED,
            f"failed to create local group {SANDBOX_USERS_GROUP}, code {status}",
        )


def ensure_sandbox_user(username: str, password: str) -> None:
    _require_windows()
    if not username or not password:
        raise ValueError("username and password are required")
    name = ctypes.create_unicode_buffer(username)
    pwd = ctypes.create_unicode_buffer(password)
    info = USER_INFO_1(
        ctypes.cast(name, wintypes.LPWSTR),
        ctypes.cast(pwd, wintypes.LPWSTR),
        0,
        USER_PRIV_USER,
        None,
        None,
        UF_SCRIPT | UF_DONT_EXPIRE_PASSWD,
        None,
    )
    parameter_error = DWORD()
    status = _netapi32.NetUserAdd(
        None, 1, ctypes.cast(ctypes.byref(info), LPBYTE), ctypes.byref(parameter_error)
    )
    if status != NERR_SUCCESS:
        update = USER_INFO_1003(ctypes.cast(pwd, wintypes.LPWSTR))
        update_status = _netapi32.NetUserSetInfo(
            None,
            name,
            1003,
            ctypes.cast(ctypes.byref(update), LPBYTE),
            ctypes.byref(parameter_error),
        )
        if update_status != NERR_SUCCESS:
            raise SetupFailure(
                SetupErrorCode.HELPER_USER_CREATE_OR_UPDATE_FAILED,
                f"failed to create/update user {username}, code {status}/{update_status}",
            )
    member = LOCALGROUP_MEMBERS_INFO_3(ctypes.cast(name, wintypes.LPWSTR))
    member_status = _netapi32.NetLocalGroupAddMembers(
        None,
        SANDBOX_USERS_GROUP,
        3,
        ctypes.cast(ctypes.byref(member), LPBYTE),
        1,
    )
    if member_status not in {NERR_SUCCESS, ERROR_MEMBER_IN_ALIAS}:
        raise SetupFailure(
            SetupErrorCode.HELPER_USER_CREATE_OR_UPDATE_FAILED,
            f"failed to add user {username} to {SANDBOX_USERS_GROUP}, code {member_status}",
        )


def provision_sandbox_users(offline_username: str, online_username: str) -> tuple[str, str]:
    ensure_sandbox_users_group()
    offline_password = random_password()
    online_password = random_password()
    ensure_sandbox_user(offline_username, offline_password)
    ensure_sandbox_user(online_username, online_password)
    return offline_password, online_password


def resolve_account_sid_string(account: str) -> str:
    _require_windows()
    sid_size = DWORD()
    domain_size = DWORD()
    sid_use = DWORD()
    ctypes.set_last_error(0)
    _advapi32.LookupAccountNameW(
        None, account, None, ctypes.byref(sid_size), None, ctypes.byref(domain_size), ctypes.byref(sid_use)
    )
    error = ctypes.get_last_error()
    if error != ERROR_INSUFFICIENT_BUFFER or not sid_size.value:
        raise SetupFailure(
            SetupErrorCode.HELPER_SID_RESOLVE_FAILED,
            f"LookupAccountNameW size query failed for {account}: {error}",
        )
    sid = ctypes.create_string_buffer(sid_size.value)
    domain = ctypes.create_unicode_buffer(max(1, domain_size.value))
    if not _advapi32.LookupAccountNameW(
        None,
        account,
        sid,
        ctypes.byref(sid_size),
        domain,
        ctypes.byref(domain_size),
        ctypes.byref(sid_use),
    ):
        error = ctypes.get_last_error()
        raise SetupFailure(
            SetupErrorCode.HELPER_SID_RESOLVE_FAILED,
            f"LookupAccountNameW failed for {account}: {error}",
        )
    text = wintypes.LPWSTR()
    if not _advapi32.ConvertSidToStringSidW(sid, ctypes.byref(text)):
        error = ctypes.get_last_error()
        raise SetupFailure(
            SetupErrorCode.HELPER_SID_RESOLVE_FAILED,
            f"ConvertSidToStringSidW failed for {account}: {error}",
        )
    try:
        return text.value
    finally:
        _kernel32.LocalFree(text)


def _require_windows() -> None:
    if os.name != "nt":
        raise SetupFailure(SetupErrorCode.HELPER_USER_PROVISION_FAILED, "local accounts require Windows")


__all__ = [
    "SANDBOX_USERS_GROUP",
    "ensure_sandbox_user",
    "ensure_sandbox_users_group",
    "provision_sandbox_users",
    "random_password",
    "resolve_account_sid_string",
]
