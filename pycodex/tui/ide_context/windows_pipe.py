"""Windows named-pipe transport boundary for IDE context IPC.

Upstream source: ``codex/codex-rs/tui/src/ide_context/windows_pipe.rs``.

Rust implements Win32 overlapped pipe I/O and same-user SID validation here.
The Python port exposes the semantic wrappers and timeout helpers while leaving
native Win32 transport calls as explicit platform boundaries.
"""

from __future__ import annotations

import ctypes
from ctypes import wintypes
from dataclasses import dataclass
import os
import time
from typing import Any, Optional

from .._porting import RustTuiModule

RUST_MODULE = RustTuiModule(
    crate="codex-tui",
    module="ide_context::windows_pipe",
    source="codex/codex-rs/tui/src/ide_context/windows_pipe.rs",
    status="complete",
)

TRUE = 1
FALSE = 0
NULL_HANDLE = 0
U32_MAX = 0xFFFFFFFF
ERROR_IO_PENDING = 997
ERROR_NOT_FOUND = 1168
WAIT_FAILED = 0xFFFFFFFF
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 0x00000102
INVALID_HANDLE_VALUE = -1
GENERIC_READ = 0x80000000
GENERIC_WRITE = 0x40000000
FILE_SHARE_READ = 0x00000001
FILE_SHARE_WRITE = 0x00000002
OPEN_EXISTING = 3
FILE_ATTRIBUTE_NORMAL = 0x00000080
FILE_FLAG_OVERLAPPED = 0x40000000
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
TOKEN_QUERY = 0x0008
TOKEN_USER = 1
ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _OVERLAPPED(ctypes.Structure):
    _fields_ = [
        ("Internal", ULONG_PTR),
        ("InternalHigh", ULONG_PTR),
        ("Offset", wintypes.DWORD),
        ("OffsetHigh", wintypes.DWORD),
        ("hEvent", wintypes.HANDLE),
    ]


@dataclass
class WindowsPipeStream:
    handle: "OwnedHandle"
    deadline: float

    @classmethod
    def connect(cls, pipe_path: Any, deadline: float) -> "WindowsPipeStream":
        _require_windows()
        handle = _kernel32().CreateFileW(
            str(pipe_path),
            GENERIC_READ | GENERIC_WRITE,
            FILE_SHARE_READ | FILE_SHARE_WRITE,
            None,
            OPEN_EXISTING,
            FILE_ATTRIBUTE_NORMAL | FILE_FLAG_OVERLAPPED,
            NULL_HANDLE,
        )
        if handle == INVALID_HANDLE_VALUE:
            raise ctypes.WinError(ctypes.get_last_error())
        owned = OwnedHandle(handle)
        try:
            validate_pipe_server_owner(owned.raw())
        except Exception:
            owned.close()
            raise
        return cls(owned, deadline)

    def set_deadline(self, deadline: float) -> None:
        self.deadline = deadline

    def read(self, buf: Any) -> int:
        if len(buf) == 0:
            return 0
        _require_windows()
        view = memoryview(buf)
        if view.readonly:
            raise TypeError("read buffer must be writable")
        amount = min(len(view), U32_MAX)
        raw = (ctypes.c_ubyte * amount).from_buffer(view)
        operation = OverlappedOperation.new()
        result = _kernel32().ReadFile(
            self.handle.raw(),
            ctypes.byref(raw),
            amount,
            None,
            operation.as_mut_ptr(),
        )
        return operation.complete(self.handle.raw(), result, self.deadline)

    def write(self, buf: Any) -> int:
        if len(buf) == 0:
            return 0
        _require_windows()
        data = memoryview(buf).tobytes()
        amount = min(len(data), U32_MAX)
        raw = ctypes.create_string_buffer(data[:amount])
        operation = OverlappedOperation.new()
        result = _kernel32().WriteFile(
            self.handle.raw(),
            ctypes.byref(raw),
            amount,
            None,
            operation.as_mut_ptr(),
        )
        return operation.complete(self.handle.raw(), result, self.deadline)

    def flush(self) -> None:
        return None


def read(stream: WindowsPipeStream, buf: Any) -> int:
    return stream.read(buf)


def write(stream: WindowsPipeStream, buf: Any) -> int:
    return stream.write(buf)


def flush(stream: WindowsPipeStream) -> None:
    stream.flush()


@dataclass
class OverlappedOperation:
    event: "OwnedHandle"
    overlapped: _OVERLAPPED

    @classmethod
    def new(cls) -> "OverlappedOperation":
        _require_windows()
        event = _kernel32().CreateEventW(None, TRUE, FALSE, None)
        if event == NULL_HANDLE:
            raise ctypes.WinError(ctypes.get_last_error())
        overlapped = _OVERLAPPED()
        overlapped.hEvent = event
        return cls(OwnedHandle(event), overlapped)

    def as_mut_ptr(self) -> Any:
        return ctypes.byref(self.overlapped)

    def complete(self, handle: Any, initial_result: int, deadline: float) -> int:
        _require_windows()
        if initial_result == 0:
            error_code = ctypes.get_last_error()
            if error_code != ERROR_IO_PENDING:
                raise ctypes.WinError(error_code)
            wait_result = _kernel32().WaitForSingleObject(
                self.event.raw(),
                remaining_timeout_ms(deadline),
            )
            if wait_result == WAIT_OBJECT_0:
                pass
            elif wait_result == WAIT_TIMEOUT:
                raise self.cancel_and_timeout(handle)
            elif wait_result == WAIT_FAILED:
                raise ctypes.WinError(ctypes.get_last_error())
            else:
                raise OSError("unexpected WaitForSingleObject result: {0}".format(wait_result))

        transferred = wintypes.DWORD(0)
        result = _kernel32().GetOverlappedResult(
            handle,
            self.as_mut_ptr(),
            ctypes.byref(transferred),
            FALSE,
        )
        if result == 0:
            raise ctypes.WinError(ctypes.get_last_error())
        return int(transferred.value)

    def cancel_and_timeout(self, handle: Any) -> TimeoutError:
        _require_windows()
        cancel_result = _kernel32().CancelIoEx(handle, self.as_mut_ptr())
        if cancel_result == 0:
            cancel_error = ctypes.get_last_error()
            if cancel_error != ERROR_NOT_FOUND:
                return ctypes.WinError(cancel_error)
            transferred = wintypes.DWORD(0)
            _kernel32().GetOverlappedResult(
                handle,
                self.as_mut_ptr(),
                ctypes.byref(transferred),
                FALSE,
            )
            return timeout_io_error()

        transferred = wintypes.DWORD(0)
        _kernel32().GetOverlappedResult(
            handle,
            self.as_mut_ptr(),
            ctypes.byref(transferred),
            TRUE,
        )
        return timeout_io_error()


@dataclass(frozen=True)
class OwnedHandle:
    handle: Any

    def raw(self) -> Any:
        return self.handle

    def close(self) -> None:
        if self.handle not in (NULL_HANDLE, INVALID_HANDLE_VALUE, None):
            _kernel32().CloseHandle(self.handle)
            object.__setattr__(self, "handle", NULL_HANDLE)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass


def drop(_handle: OwnedHandle) -> None:
    _handle.close()


@dataclass(frozen=True)
class TokenUserBuffer:
    buffer: bytes
    sid_value: Optional[Any] = None

    def sid(self) -> Any:
        if len(self.buffer) < _token_user_header_size():
            raise ValueError("token user buffer is too small")
        if self.sid_value is not None:
            return self.sid_value
        token_user = _TOKEN_USER.from_buffer_copy(self.buffer)
        return token_user.User.Sid


def validate_pipe_server_owner(pipe_handle: Any) -> None:
    _require_windows()
    server_process_id = wintypes.ULONG(0)
    result = _kernel32().GetNamedPipeServerProcessId(
        pipe_handle,
        ctypes.byref(server_process_id),
    )
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())

    server_process = _kernel32().OpenProcess(
        PROCESS_QUERY_LIMITED_INFORMATION,
        FALSE,
        server_process_id.value,
    )
    if server_process == NULL_HANDLE:
        raise ctypes.WinError(ctypes.get_last_error())
    server_process_handle = OwnedHandle(server_process)
    server_token = open_process_token(server_process_handle.raw())
    current_token = open_process_token(_kernel32().GetCurrentProcess())
    server_user = token_user(server_token.raw())
    current_user = token_user(current_token.raw())
    if _advapi32().EqualSid(server_user.sid(), current_user.sid()) == 0:
        raise PermissionError("IDE context provider is not owned by the current user")


def open_process_token(process: Any) -> OwnedHandle:
    _require_windows()
    token = wintypes.HANDLE(0)
    result = _advapi32().OpenProcessToken(process, TOKEN_QUERY, ctypes.byref(token))
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    return OwnedHandle(token.value)


def token_user(token: Any) -> TokenUserBuffer:
    _require_windows()
    return_length = wintypes.DWORD(0)
    _advapi32().GetTokenInformation(token, TOKEN_USER, None, 0, ctypes.byref(return_length))
    if return_length.value == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    buffer = ctypes.create_string_buffer(return_length.value)
    result = _advapi32().GetTokenInformation(
        token,
        TOKEN_USER,
        buffer,
        return_length,
        ctypes.byref(return_length),
    )
    if result == 0:
        raise ctypes.WinError(ctypes.get_last_error())
    token_user_header = _TOKEN_USER.from_buffer_copy(buffer.raw)
    return TokenUserBuffer(buffer.raw, token_user_header.User.Sid)


def remaining_timeout_ms(deadline: float) -> int:
    now = time.monotonic()
    if now >= deadline:
        return 0
    millis = max(1, int((deadline - now) * 1000))
    return min(U32_MAX, millis)


def timeout_io_error() -> TimeoutError:
    return TimeoutError("timed out waiting for IDE context")


class _SID_AND_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("Sid", wintypes.LPVOID),
        ("Attributes", wintypes.DWORD),
    ]


class _TOKEN_USER(ctypes.Structure):
    _fields_ = [("User", _SID_AND_ATTRIBUTES)]


def _token_user_header_size() -> int:
    return ctypes.sizeof(_TOKEN_USER)


def _require_windows() -> None:
    if os.name != "nt":
        raise OSError("Windows named-pipe IDE context transport is only available on Windows")


def _kernel32() -> Any:
    _require_windows()
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    kernel32.CreateFileW.restype = wintypes.HANDLE
    kernel32.ReadFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    kernel32.ReadFile.restype = wintypes.BOOL
    kernel32.WriteFile.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.LPVOID,
    ]
    kernel32.WriteFile.restype = wintypes.BOOL
    kernel32.CreateEventW.argtypes = [
        wintypes.LPVOID,
        wintypes.BOOL,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    kernel32.CreateEventW.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.GetOverlappedResult.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.POINTER(wintypes.DWORD),
        wintypes.BOOL,
    ]
    kernel32.GetOverlappedResult.restype = wintypes.BOOL
    kernel32.CancelIoEx.argtypes = [wintypes.HANDLE, wintypes.LPVOID]
    kernel32.CancelIoEx.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.GetNamedPipeServerProcessId.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.ULONG),
    ]
    kernel32.GetNamedPipeServerProcessId.restype = wintypes.BOOL
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    return kernel32


def _advapi32() -> Any:
    _require_windows()
    advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)
    advapi32.OpenProcessToken.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.HANDLE),
    ]
    advapi32.OpenProcessToken.restype = wintypes.BOOL
    advapi32.GetTokenInformation.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPVOID,
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    advapi32.GetTokenInformation.restype = wintypes.BOOL
    advapi32.EqualSid.argtypes = [wintypes.LPVOID, wintypes.LPVOID]
    advapi32.EqualSid.restype = wintypes.BOOL
    return advapi32


__all__ = [
    "FALSE",
    "NULL_HANDLE",
    "OverlappedOperation",
    "OwnedHandle",
    "RUST_MODULE",
    "TRUE",
    "TokenUserBuffer",
    "WindowsPipeStream",
    "drop",
    "flush",
    "open_process_token",
    "read",
    "remaining_timeout_ms",
    "timeout_io_error",
    "token_user",
    "validate_pipe_server_owner",
    "write",
]
