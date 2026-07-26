"""Low-level Win32 string, command-line, error, and SID utilities."""

from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


WELL_KNOWN_SIDS = {
    "Administrators": "S-1-5-32-544",
    "Users": "S-1-5-32-545",
    "Authenticated Users": "S-1-5-11",
    "Everyone": "S-1-1-0",
    "SYSTEM": "S-1-5-18",
}


if os.name == "nt":
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32.ConvertStringSidToSidW.argtypes = [
        wintypes.LPCWSTR,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _advapi32.ConvertStringSidToSidW.restype = wintypes.BOOL
    _advapi32.ConvertSidToStringSidW.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.LPWSTR),
    ]
    _advapi32.ConvertSidToStringSidW.restype = wintypes.BOOL
    _advapi32.GetLengthSid.argtypes = [ctypes.c_void_p]
    _advapi32.GetLengthSid.restype = wintypes.DWORD
    _advapi32.LookupAccountNameW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
        ctypes.POINTER(wintypes.DWORD),
    ]
    _advapi32.LookupAccountNameW.restype = wintypes.BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p


def to_wide(value: object) -> list[int]:
    encoded = str(value).encode("utf-16-le")
    return [
        int.from_bytes(encoded[index : index + 2], "little")
        for index in range(0, len(encoded), 2)
    ] + [0]


def quote_windows_arg(arg: str) -> str:
    needs_quotes = not arg or any(
        char in {" ", "\t", "\n", "\r", '"'} for char in arg
    )
    if not needs_quotes:
        return arg
    output = ['"']
    backslashes = 0
    for char in arg:
        if char == "\\":
            backslashes += 1
        elif char == '"':
            output.append("\\" * (backslashes * 2 + 1))
            output.append('"')
            backslashes = 0
        else:
            if backslashes:
                output.append("\\" * backslashes)
                backslashes = 0
            output.append(char)
    if backslashes:
        output.append("\\" * (backslashes * 2))
    output.append('"')
    return "".join(output)


def argv_to_command_line(argv: list[str] | tuple[str, ...]) -> str:
    return " ".join(quote_windows_arg(arg) for arg in argv)


def format_last_error(error: int) -> str:
    if os.name != "nt":
        return f"Win32 error {error}"
    try:
        return ctypes.FormatError(error).strip()
    except OSError:
        return f"Win32 error {error}"


def string_from_sid_bytes(sid: bytes | bytearray | memoryview) -> str:
    _require_windows()
    buffer = ctypes.create_string_buffer(bytes(sid))
    output = wintypes.LPWSTR()
    if not _advapi32.ConvertSidToStringSidW(buffer, ctypes.byref(output)):
        error = ctypes.get_last_error()
        raise OSError(error, f"ConvertSidToStringSidW failed: {error}")
    try:
        return output.value
    finally:
        _kernel32.LocalFree(output)


def resolve_sid(name: str) -> bytes:
    _require_windows()
    sid_text = WELL_KNOWN_SIDS.get(name)
    if sid_text is not None:
        return _sid_bytes_from_string(sid_text)

    sid_length = wintypes.DWORD(0)
    domain_length = wintypes.DWORD(0)
    sid_type = wintypes.DWORD()
    _advapi32.LookupAccountNameW(
        None,
        name,
        None,
        ctypes.byref(sid_length),
        None,
        ctypes.byref(domain_length),
        ctypes.byref(sid_type),
    )
    if not sid_length.value:
        error = ctypes.get_last_error()
        raise OSError(error, f"LookupAccountNameW failed for {name}: {error}")
    sid = ctypes.create_string_buffer(sid_length.value)
    domain = ctypes.create_unicode_buffer(domain_length.value)
    if not _advapi32.LookupAccountNameW(
        None,
        name,
        sid,
        ctypes.byref(sid_length),
        domain,
        ctypes.byref(domain_length),
        ctypes.byref(sid_type),
    ):
        error = ctypes.get_last_error()
        raise OSError(error, f"LookupAccountNameW failed for {name}: {error}")
    return bytes(sid.raw[: sid_length.value])


def _sid_bytes_from_string(sid_text: str) -> bytes:
    pointer = ctypes.c_void_p()
    if not _advapi32.ConvertStringSidToSidW(
        sid_text,
        ctypes.byref(pointer),
    ):
        error = ctypes.get_last_error()
        raise OSError(error, f"ConvertStringSidToSidW failed for {sid_text}: {error}")
    try:
        length = _advapi32.GetLengthSid(pointer)
        if not length:
            error = ctypes.get_last_error()
            raise OSError(error, f"GetLengthSid failed for {sid_text}: {error}")
        return ctypes.string_at(pointer, length)
    finally:
        _kernel32.LocalFree(pointer)


def _require_windows() -> None:
    if os.name != "nt":
        raise OSError("Win32 SID operations require Windows")


__all__ = [
    "argv_to_command_line",
    "format_last_error",
    "quote_windows_arg",
    "resolve_sid",
    "string_from_sid_bytes",
    "to_wide",
]
