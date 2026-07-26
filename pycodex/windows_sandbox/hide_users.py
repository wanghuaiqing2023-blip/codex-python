"""Best-effort hiding of sandbox accounts and profile directories."""

from __future__ import annotations

import ctypes
import os
import winreg
from ctypes import wintypes
from pathlib import Path
from typing import Sequence

from .logging import log_note
from .winutil import format_last_error


USERLIST_KEY_PATH = (
    r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
    r"\SpecialAccounts\UserList"
)
FILE_ATTRIBUTE_HIDDEN = 0x2
FILE_ATTRIBUTE_SYSTEM = 0x4
INVALID_FILE_ATTRIBUTES = 0xFFFFFFFF


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetFileAttributesW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetFileAttributesW.restype = wintypes.DWORD
    _kernel32.SetFileAttributesW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD]
    _kernel32.SetFileAttributesW.restype = wintypes.BOOL


def hide_newly_created_users(
    usernames: Sequence[str],
    log_base: str | Path,
) -> None:
    if not usernames:
        return
    try:
        _hide_users_in_winlogon(usernames, Path(log_base))
    except OSError as exc:
        log_note(
            f"hide users: failed to update Winlogon UserList: {exc}",
            log_base,
        )


def hide_current_user_profile_dir(log_base: str | Path) -> None:
    profile = os.environ.get("USERPROFILE")
    if not profile:
        return
    profile_dir = Path(profile)
    if not profile_dir.exists():
        return
    try:
        changed = _hide_directory(profile_dir)
    except OSError as exc:
        log_note(
            f"hide users: failed to hide current user profile dir "
            f"({profile_dir}): {exc}",
            log_base,
        )
    else:
        if changed:
            log_note(
                f"hide users: profile dir hidden for current user "
                f"({profile_dir})",
                log_base,
            )


def _hide_users_in_winlogon(
    usernames: Sequence[str],
    log_base: Path,
) -> None:
    with winreg.CreateKeyEx(
        winreg.HKEY_LOCAL_MACHINE,
        USERLIST_KEY_PATH,
        0,
        winreg.KEY_WRITE,
    ) as key:
        for username in usernames:
            try:
                winreg.SetValueEx(key, username, 0, winreg.REG_DWORD, 0)
            except OSError as exc:
                log_note(
                    f"hide users: failed to set UserList value for "
                    f"{username}: {exc}",
                    log_base,
                )


def _hide_directory(path: Path) -> bool:
    if os.name != "nt":
        raise OSError("directory hiding requires Windows")
    ctypes.set_last_error(0)
    attributes = _kernel32.GetFileAttributesW(str(path))
    if attributes == INVALID_FILE_ATTRIBUTES:
        error = ctypes.get_last_error()
        raise OSError(
            error,
            f"GetFileAttributesW failed for {path}: {error} "
            f"({format_last_error(error)})",
        )
    updated = attributes | FILE_ATTRIBUTE_HIDDEN | FILE_ATTRIBUTE_SYSTEM
    if updated == attributes:
        return False
    if not _kernel32.SetFileAttributesW(str(path), updated):
        error = ctypes.get_last_error()
        raise OSError(
            error,
            f"SetFileAttributesW failed for {path}: {error} "
            f"({format_last_error(error)})",
        )
    return True


__all__ = ["hide_current_user_profile_dir", "hide_newly_created_users"]
