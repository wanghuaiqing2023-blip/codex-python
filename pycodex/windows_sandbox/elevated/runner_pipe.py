"""Named-pipe helpers for the elevated Windows sandbox runner.

Rust owner: ``codex-windows-sandbox::elevated::runner_pipe``.
"""

from __future__ import annotations

import ctypes
import io
import os
import sys
import uuid
from ctypes import wintypes
from pathlib import Path

from ..local_accounts import resolve_account_sid_string
from ..process import WindowsSandboxProcessError


PIPE_ACCESS_INBOUND = 0x00000001
PIPE_ACCESS_OUTBOUND = 0x00000002
_PIPE_TYPE_BYTE = 0x00000000
_PIPE_READMODE_BYTE = 0x00000000
_PIPE_WAIT = 0x00000000
_ERROR_PIPE_CONNECTED = 535
_INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value


if os.name == "nt":
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _advapi32 = ctypes.WinDLL("advapi32", use_last_error=True)

    HANDLE = wintypes.HANDLE
    DWORD = wintypes.DWORD
    BOOL = wintypes.BOOL

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [
            ("nLength", DWORD),
            ("lpSecurityDescriptor", ctypes.c_void_p),
            ("bInheritHandle", BOOL),
        ]

    _kernel32.CreateNamedPipeW.argtypes = [
        wintypes.LPCWSTR,
        DWORD,
        DWORD,
        DWORD,
        DWORD,
        DWORD,
        DWORD,
        ctypes.POINTER(_SecurityAttributes),
    ]
    _kernel32.CreateNamedPipeW.restype = HANDLE
    _kernel32.ConnectNamedPipe.argtypes = [HANDLE, ctypes.c_void_p]
    _kernel32.ConnectNamedPipe.restype = BOOL
    _kernel32.GetNamedPipeClientProcessId.argtypes = [HANDLE, ctypes.POINTER(DWORD)]
    _kernel32.GetNamedPipeClientProcessId.restype = BOOL
    _kernel32.CloseHandle.argtypes = [HANDLE]
    _kernel32.CloseHandle.restype = BOOL
    _kernel32.ReadFile.argtypes = [
        HANDLE,
        ctypes.c_void_p,
        DWORD,
        ctypes.POINTER(DWORD),
        ctypes.c_void_p,
    ]
    _kernel32.ReadFile.restype = BOOL
    _kernel32.WriteFile.argtypes = [
        HANDLE,
        ctypes.c_void_p,
        DWORD,
        ctypes.POINTER(DWORD),
        ctypes.c_void_p,
    ]
    _kernel32.WriteFile.restype = BOOL
    _kernel32.LocalFree.argtypes = [ctypes.c_void_p]
    _kernel32.LocalFree.restype = ctypes.c_void_p
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.argtypes = [
        wintypes.LPCWSTR,
        DWORD,
        ctypes.POINTER(ctypes.c_void_p),
        ctypes.POINTER(DWORD),
    ]
    _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW.restype = BOOL
else:
    HANDLE = ctypes.c_void_p
    DWORD = ctypes.c_uint32


class _PipeStream(io.RawIOBase):
    def __init__(self, handle: object) -> None:
        super().__init__()
        self.handle = handle

    def readable(self) -> bool:
        return True

    def writable(self) -> bool:
        return True

    def read(self, size: int = -1) -> bytes:
        if self.closed:
            return b""
        _require_windows()
        size = 65536 if size is None or size < 0 else size
        if size == 0:
            return b""
        buffer = ctypes.create_string_buffer(size)
        read = DWORD()
        if not _kernel32.ReadFile(self.handle, buffer, size, ctypes.byref(read), None):
            error = ctypes.get_last_error()
            if error in {109, 232, 233}:
                return b""
            raise OSError(error, f"ReadFile runner pipe failed: {error}")
        return buffer.raw[: read.value]

    def write(self, data: bytes | bytearray | memoryview) -> int:
        if self.closed:
            raise BrokenPipeError("runner pipe is closed")
        _require_windows()
        source = bytes(data)
        offset = 0
        while offset < len(source):
            chunk = source[offset:]
            written = DWORD()
            buffer = ctypes.create_string_buffer(chunk, len(chunk))
            if not _kernel32.WriteFile(
                self.handle,
                buffer,
                len(chunk),
                ctypes.byref(written),
                None,
            ):
                error = ctypes.get_last_error()
                raise OSError(error, f"WriteFile runner pipe failed: {error}")
            if not written.value:
                raise BrokenPipeError("runner pipe wrote zero bytes")
            offset += written.value
        return len(source)

    def flush(self) -> None:
        return None

    def close(self) -> None:
        if not self.closed:
            value = getattr(self.handle, "value", self.handle)
            if value and os.name == "nt":
                _kernel32.CloseHandle(HANDLE(value))
            self.handle = HANDLE()
        super().close()


def find_runner_exe(codex_home: str | Path, log_dir: str | Path | None = None) -> Path:
    """Resolve the executable hosting the Python command-runner module."""

    del codex_home, log_dir
    configured = os.environ.get("PYCODEX_SANDBOX_RUNNER_PYTHON")
    candidates = (
        Path(configured) if configured else None,
        Path.home()
        / ".cache"
        / "codex-runtimes"
        / "codex-primary-runtime"
        / "dependencies"
        / "python"
        / "python.exe",
        Path(sys.executable),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise WindowsSandboxProcessError(
        "no readable Python runtime is available for the sandbox command runner"
    )


def pipe_pair() -> tuple[str, str]:
    nonce = uuid.uuid4().hex
    base = rf"\\.\pipe\codex-runner-{nonce}"
    return f"{base}-in", f"{base}-out"


def create_named_pipe(name: str, access: int, sandbox_username: str) -> object:
    _require_windows()
    sandbox_sid = resolve_account_sid_string(sandbox_username)
    descriptor = ctypes.c_void_p()
    sddl = f"D:(A;;GA;;;{sandbox_sid})"
    if not _advapi32.ConvertStringSecurityDescriptorToSecurityDescriptorW(
        sddl,
        1,
        ctypes.byref(descriptor),
        None,
    ):
        error = ctypes.get_last_error()
        raise WindowsSandboxProcessError(
            error,
            f"build runner pipe security descriptor failed: {error}",
        )
    try:
        attrs = _SecurityAttributes(
            ctypes.sizeof(_SecurityAttributes),
            descriptor,
            False,
        )
        handle = _kernel32.CreateNamedPipeW(
            name,
            access,
            _PIPE_TYPE_BYTE | _PIPE_READMODE_BYTE | _PIPE_WAIT,
            1,
            65536,
            65536,
            0,
            ctypes.byref(attrs),
        )
        value = getattr(handle, "value", handle)
        if not value or value == _INVALID_HANDLE_VALUE:
            error = ctypes.get_last_error()
            raise WindowsSandboxProcessError(
                error,
                f"CreateNamedPipeW failed: {error}",
            )
        return handle
    finally:
        if descriptor.value:
            _kernel32.LocalFree(descriptor)


def connect_pipe(handle: object, expected_runner_pid: int) -> None:
    _require_windows()
    _connect_named_pipe(handle)
    client_pid = _named_pipe_client_pid(handle)
    if client_pid != expected_runner_pid:
        raise PermissionError(
            f"named pipe client pid {client_pid} did not match runner pid "
            f"{expected_runner_pid}"
        )


def pipe_stream(handle: object) -> io.RawIOBase:
    return _PipeStream(handle)


def close_handle(handle: object) -> None:
    value = getattr(handle, "value", handle)
    if value and os.name == "nt":
        _kernel32.CloseHandle(HANDLE(value))


def _connect_named_pipe(handle: object) -> None:
    if _kernel32.ConnectNamedPipe(handle, None):
        return
    error = ctypes.get_last_error()
    if error != _ERROR_PIPE_CONNECTED:
        raise WindowsSandboxProcessError(
            error,
            f"ConnectNamedPipe failed: {error}",
        )


def _named_pipe_client_pid(handle: object) -> int:
    pid = DWORD()
    if not _kernel32.GetNamedPipeClientProcessId(handle, ctypes.byref(pid)):
        error = ctypes.get_last_error()
        raise WindowsSandboxProcessError(
            error,
            f"GetNamedPipeClientProcessId failed: {error}",
        )
    return int(pid.value)


def _require_windows() -> None:
    if os.name != "nt":
        raise WindowsSandboxProcessError(
            "elevated sandbox runner pipes are only available on Windows"
        )


__all__ = [
    "PIPE_ACCESS_INBOUND",
    "PIPE_ACCESS_OUTBOUND",
    "connect_pipe",
    "create_named_pipe",
    "find_runner_exe",
    "pipe_pair",
]
